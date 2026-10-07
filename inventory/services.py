from django.db import transaction
from django.core.exceptions import ValidationError
from .models import MedicineBatch, StockTransaction, TransactionTypeChoices

@transaction.atomic
def create_medicine_batch(batch_data, user):
    """
    Creates a new MedicineBatch and a corresponding STOCK_IN transaction.
    """
    batch = MedicineBatch(**batch_data)
    if not user.is_superuser and batch.medicine.pharmacy_id != user.pharmacy_id:
        raise ValidationError("The selected medicine belongs to another pharmacy.")
    # Ensure quantity_remaining starts as quantity_received
    batch.quantity_remaining = batch.quantity_received
    batch.full_clean()
    batch.save()

    StockTransaction.objects.create(
        batch=batch,
        user=user,
        transaction_type=TransactionTypeChoices.STOCK_IN,
        quantity=batch.quantity_received,
        previous_quantity=0,
        new_quantity=batch.quantity_received,
        notes="Initial stock in."
    )
    return batch


@transaction.atomic
def adjust_batch_stock(batch, user, adjustment_type, quantity, notes=""):
    """
    Adjusts the stock for a batch and creates the corresponding transaction.
    adjustment_type should be INCREASE or DECREASE.
    """
    if quantity <= 0:
        raise ValidationError("Adjustment quantity must be greater than 0.")
    if not user.is_superuser and batch.medicine.pharmacy_id != user.pharmacy_id:
        raise ValidationError("This batch belongs to another pharmacy.")

    batch = MedicineBatch.objects.select_for_update().get(pk=batch.pk)
    
    previous_quantity = batch.quantity_remaining
    new_quantity = previous_quantity

    if adjustment_type == 'INCREASE':
        new_quantity += quantity
        txn_type = TransactionTypeChoices.ADJUSTMENT_INCREASE
    elif adjustment_type == 'DECREASE':
        if quantity > previous_quantity:
            raise ValidationError("Cannot decrease stock below zero.")
        new_quantity -= quantity
        txn_type = TransactionTypeChoices.ADJUSTMENT_DECREASE
    else:
        raise ValueError("Invalid adjustment type.")

    # Apply changes
    batch.quantity_remaining = new_quantity
    batch.full_clean()
    batch.save()

    # Record transaction
    StockTransaction.objects.create(
        batch=batch,
        user=user,
        transaction_type=txn_type,
        quantity=quantity,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        notes=notes
    )
    
    return batch
