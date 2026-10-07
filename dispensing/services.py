"""
Dispensing services — FEFO allocation and atomic transaction confirmation.
"""
from decimal import Decimal
from datetime import date

from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from inventory.models import MedicineBatch, StockTransaction, TransactionTypeChoices
from .models import DispensingTransaction, DispensingItem, TransactionStatusChoices


def get_valid_batches_fefo(medicine):
    """
    Returns a queryset of active, non-expired, in-stock batches for a medicine,
    ordered by expiry_date ASC (FEFO — First Expire, First Out),
    with date_received as a tiebreaker.
    """
    return MedicineBatch.objects.filter(
        medicine=medicine,
        is_active=True,
        expiry_date__gt=date.today(),
        quantity_remaining__gt=0,
    ).order_by('expiry_date', 'date_received')


def check_stock_availability(medicine, quantity):
    """
    Preview-only FEFO allocation check.
    Returns list of (batch, allocated_qty) tuples.
    Does NOT lock rows or modify stock.
    Raises ValidationError if insufficient.
    """
    if quantity <= 0:
        raise ValidationError("Quantity must be greater than 0.")

    batches = list(get_valid_batches_fefo(medicine))
    allocation = []
    remaining = quantity

    for batch in batches:
        if remaining <= 0:
            break
        take = min(batch.quantity_remaining, remaining)
        allocation.append((batch, take))
        remaining -= take

    if remaining > 0:
        total_available = sum(b.quantity_remaining for b in batches)
        raise ValidationError(
            f"Insufficient stock for {medicine.generic_name}. "
            f"Requested: {quantity}, Available: {total_available}."
        )

    return allocation


@db_transaction.atomic
def confirm_transaction(dispensing_transaction, cart, user):
    """
    Atomically confirms a DRAFT dispensing transaction from session cart data.

    cart: dict keyed by str(medicine_id):
        {
            'medicine_id': int,
            'medicine_name': str,  # display only
            'quantity': int,
        }

    Steps:
    1. Lock the DispensingTransaction row.
    2. Validate status is DRAFT.
    3. For each cart line, re-acquire valid batches with select_for_update().
    4. Run FEFO allocation; raise if insufficient.
    5. Create DispensingItem rows (one per batch allocation).
    6. Deduct stock from each batch.
    7. Create StockTransaction(DISPENSED) per batch deduction.
    8. Set transaction totals, mark COMPLETED.

    On any failure the entire atomic block is rolled back.
    Raises ValidationError with a descriptive message.
    """
    from medicines.models import Medicine

    # Lock the dispensing transaction row
    txn = DispensingTransaction.objects.select_for_update().get(
        pk=dispensing_transaction.pk
    )

    if not user.is_superuser and txn.pharmacy_id != user.pharmacy_id:
        raise ValidationError("This transaction does not belong to your pharmacy.")

    if txn.status != TransactionStatusChoices.DRAFT:
        raise ValidationError("Only DRAFT transactions can be confirmed.")

    if not cart:
        raise ValidationError("Cart is empty. Add at least one medicine before confirming.")

    total_amount = Decimal('0.00')

    for medicine_id_str, cart_line in cart.items():
        medicine_id = int(medicine_id_str)
        requested_qty = int(cart_line['quantity'])

        if requested_qty <= 0:
            raise ValidationError(f"Invalid quantity for medicine ID {medicine_id}.")

        try:
            medicine = Medicine.objects.get(
                pk=medicine_id, is_active=True, pharmacy_id=txn.pharmacy_id
            )
        except Medicine.DoesNotExist:
            raise ValidationError(
                f"Medicine ID {medicine_id} not found or is no longer active."
            )

        # Re-acquire valid batches with row-level locking
        batches = list(
            MedicineBatch.objects.select_for_update().filter(
                medicine=medicine,
                is_active=True,
                expiry_date__gt=date.today(),
                quantity_remaining__gt=0,
            ).order_by('expiry_date', 'date_received')
        )

        # FEFO allocation
        allocation = []
        remaining = requested_qty
        for batch in batches:
            if remaining <= 0:
                break
            take = min(batch.quantity_remaining, remaining)
            allocation.append((batch, take))
            remaining -= take

        if remaining > 0:
            total_available = sum(b.quantity_remaining for b in batches)
            raise ValidationError(
                f"Insufficient stock for '{medicine.generic_name}'. "
                f"Requested: {requested_qty}, Available: {total_available}."
            )

        # Commit each batch allocation
        for batch, qty in allocation:
            unit_price = batch.selling_price
            line_total = Decimal(str(qty)) * unit_price

            # Create DispensingItem record
            DispensingItem.objects.create(
                transaction=txn,
                medicine=medicine,
                batch=batch,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
                dose=cart_line.get('dose'),
                frequency=cart_line.get('frequency'),
                duration=cart_line.get('duration'),
                instructions=cart_line.get('instructions'),
                dose_amount=cart_line.get('dose_amount'),
                dose_unit=cart_line.get('dose_unit') or None,
                frequency_per_day=cart_line.get('frequency_per_day'),
                duration_days=cart_line.get('duration_days'),
            )

            # Deduct stock
            previous_qty = batch.quantity_remaining
            new_qty = previous_qty - qty
            batch.quantity_remaining = new_qty
            batch.save(update_fields=['quantity_remaining', 'updated_at'])

            # Record DISPENSED StockTransaction
            StockTransaction.objects.create(
                batch=batch,
                user=user,
                transaction_type=TransactionTypeChoices.DISPENSED,
                quantity=qty,
                previous_quantity=previous_qty,
                new_quantity=new_qty,
                reference_number=txn.transaction_number,
                notes=f"Dispensed via {txn.transaction_number}.",
            )

            total_amount += line_total

    # Finalise the dispensing transaction
    txn.subtotal = total_amount
    txn.total_amount = total_amount
    txn.status = TransactionStatusChoices.COMPLETED
    txn.completed_at = timezone.now()
    txn.save(update_fields=['subtotal', 'total_amount', 'status', 'completed_at'])

    return txn
