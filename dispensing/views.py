"""
Dispensing views — Direct Sale workflow.

Session cart structure:
    session['cart_<txn_pk>'] = {
        '<medicine_id>': {
            'medicine_id': int,
            'medicine_name': str,
            'quantity': int,
        },
        ...
    }

Medicine IDs are the stable cart keys — no duplicate rows per medicine.
"""
import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from medicines.models import Medicine
from .forms import AddToCartForm, ExternalPrescriptionForm, PrescriptionItemForm
from .models import DispensingTransaction, TransactionStatusChoices, TransactionTypeChoices, ExternalPrescription
from .services import check_stock_availability, confirm_transaction
from clinical.models import AlertTypeChoices, ClinicalCheckStatus, ClinicalCheckType
from clinical.services import (
    acknowledge_alerts, current_review, invalidate_clinical_review,
    run_clinical_review as execute_clinical_review,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cart_key(txn_pk):
    return f"cart_{txn_pk}"


def _get_cart(request, txn_pk):
    return request.session.get(_cart_key(txn_pk), {})


def _save_cart(request, txn_pk, cart):
    request.session[_cart_key(txn_pk)] = cart
    request.session.modified = True


def _clear_cart(request, txn_pk):
    key = _cart_key(txn_pk)
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def _compute_preview_total(cart):
    """
    Compute a display-only total from cart lines using the current FEFO batch price.
    This is NOT used for billing — the service recomputes from actual batches.
    """
    from .services import get_valid_batches_fefo
    from medicines.models import Medicine as Med
    total = Decimal('0.00')
    for med_id_str, line in cart.items():
        try:
            med = Med.objects.get(pk=int(med_id_str))
            first_batch = get_valid_batches_fefo(med).first()
            price = first_batch.selling_price if first_batch else Decimal('0.00')
        except Med.DoesNotExist:
            price = Decimal('0.00')
        total += price * Decimal(str(line['quantity']))
    return total


def _clinical_context(txn, cart):
    review = current_review(txn, cart)
    results = {
        result.check_type: result
        for result in txn.clinical_check_results.all()
    } if review else {}
    alerts = list(txn.clinical_alerts.select_related('medicine_a', 'medicine_b', 'allergen')) if review else []
    return {
        'clinical_review': review,
        'interaction_result': results.get(ClinicalCheckType.DRUG_INTERACTION),
        'allergy_result': results.get(ClinicalCheckType.ALLERGY),
        'dosage_result': results.get(ClinicalCheckType.DOSAGE),
        'interaction_alerts': [alert for alert in alerts if alert.alert_type == AlertTypeChoices.DRUG_INTERACTION],
        'allergy_alerts': [alert for alert in alerts if alert.alert_type == AlertTypeChoices.ALLERGY],
        'dosage_alerts': [alert for alert in alerts if alert.alert_type == AlertTypeChoices.DOSAGE],
        'clinical_alerts': alerts,
        'risk_assessment': getattr(txn, 'risk_assessment', None) if review else None,
    }


def _cart_redirect(txn):
    if txn.transaction_type == TransactionTypeChoices.EXTERNAL_PRESCRIPTION:
        return redirect('dispensing:external_prescription_cart', pk=txn.pk)
    if txn.transaction_type == TransactionTypeChoices.CONSULTATION:
        return redirect('dispensing:consultation_cart', pk=txn.pk)
    return redirect('dispensing:sale_cart', pk=txn.pk)


def _confirm_after_clinical_review(request, txn, cart, success_label):
    result = execute_clinical_review(txn, cart)
    if result['status'] == ClinicalCheckStatus.NOT_CHECKED:
        messages.error(request, 'The clinical review could not be completed. No stock was deducted.')
        return _cart_redirect(txn)
    if result['status'] == ClinicalCheckStatus.WARNING:
        if request.POST.get('acknowledge_clinical_warnings') != 'on':
            messages.error(request, 'Review and acknowledge all clinical warnings before dispensing.')
            return _cart_redirect(txn)
        acknowledge_alerts(txn, request.user, request.POST.get('acknowledgement_note', ''))

    try:
        completed_txn = confirm_transaction(txn, cart, request.user)
        _clear_cart(request, txn.pk)
        messages.success(request, f'{success_label} {completed_txn.transaction_number} completed successfully.')
        return redirect('dispensing:transaction_detail', pk=completed_txn.pk)
    except ValidationError as exc:
        messages.error(request, exc.message)
        return _cart_redirect(txn)


# ---------------------------------------------------------------------------
# New Direct Sale
# ---------------------------------------------------------------------------

@login_required
def new_direct_sale(request):
    """
    Creates a new DRAFT DispensingTransaction and redirects to the cart view.
    """
    txn = DispensingTransaction.objects.create(
        user=request.user,
        transaction_type=TransactionTypeChoices.DIRECT_SALE,
        status=TransactionStatusChoices.DRAFT,
    )
    _save_cart(request, txn.pk, {})
    return redirect('dispensing:sale_cart', pk=txn.pk)


# ---------------------------------------------------------------------------
# Cart View
# ---------------------------------------------------------------------------

@login_required
def sale_cart(request, pk):
    """
    Displays the current DRAFT cart for the given transaction.
    Accepts the medicine search + add form via POST (delegated to add_to_cart).
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
    )

    cart = _get_cart(request, txn.pk)

    # Build enriched cart lines for display (preview prices)
    from .services import get_valid_batches_fefo
    cart_display = []
    preview_total = Decimal('0.00')
    for med_id_str, line in cart.items():
        try:
            med = Medicine.objects.get(pk=int(med_id_str))
            first_batch = get_valid_batches_fefo(med).first()
            price = first_batch.selling_price if first_batch else Decimal('0.00')
            avail = med.total_available_stock
        except Medicine.DoesNotExist:
            price = Decimal('0.00')
            avail = 0
            med = None
        qty = line['quantity']
        line_total = price * Decimal(str(qty))
        preview_total += line_total
        cart_display.append({
            'medicine_id': int(med_id_str),
            'medicine_name': line['medicine_name'],
            'quantity': qty,
            'unit_price': price,
            'line_total': line_total,
            'available': avail,
        })

    form = AddToCartForm()

    context = {
        'txn': txn,
        'cart_display': cart_display,
        'preview_total': preview_total,
        'form': form,
        'title': f"New Direct Sale — {txn.transaction_number}",
    }
    context.update(_clinical_context(txn, cart))
    return render(request, 'dispensing/sale_cart.html', context)


# ---------------------------------------------------------------------------
# Add to Cart
# ---------------------------------------------------------------------------

@login_required
def add_to_cart(request, pk):
    """
    POST: validates medicine + quantity, runs a preview stock check, then
    adds/merges into the session cart using medicine_id as the stable key.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
    )

    if request.method != 'POST':
        if txn.transaction_type == TransactionTypeChoices.CONSULTATION:
            return redirect('dispensing:consultation_cart', pk=txn.pk)
        return redirect('dispensing:sale_cart', pk=txn.pk)

    form = PrescriptionItemForm(request.POST) if txn.transaction_type == TransactionTypeChoices.CONSULTATION else AddToCartForm(request.POST)
    if not form.is_valid():
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
        if txn.transaction_type == TransactionTypeChoices.CONSULTATION:
            return redirect('dispensing:consultation_cart', pk=txn.pk)
        return redirect('dispensing:sale_cart', pk=txn.pk)

    medicine_id = form.cleaned_data['medicine_id']
    quantity = form.cleaned_data['quantity']

    # Validate medicine
    try:
        medicine = Medicine.objects.get(pk=medicine_id, is_active=True)
    except Medicine.DoesNotExist:
        messages.error(request, "Selected medicine is not available.")
        if txn.transaction_type == TransactionTypeChoices.CONSULTATION:
            return redirect('dispensing:consultation_cart', pk=txn.pk)
        return redirect('dispensing:sale_cart', pk=txn.pk)

    cart = _get_cart(request, txn.pk)
    key = str(medicine_id)

    # Merge quantity if medicine already in cart
    existing_qty = cart[key]['quantity'] if key in cart else 0
    new_total_qty = existing_qty + quantity

    # Preview stock check against requested total qty
    try:
        check_stock_availability(medicine, new_total_qty)
    except ValidationError as e:
        messages.error(request, e.message)
        if txn.transaction_type == TransactionTypeChoices.CONSULTATION:
            return redirect('dispensing:consultation_cart', pk=txn.pk)
        return redirect('dispensing:sale_cart', pk=txn.pk)

    cart[key] = {
        'medicine_id': medicine.pk,
        'medicine_name': str(medicine),
        'quantity': new_total_qty,
    }
    if txn.transaction_type == TransactionTypeChoices.CONSULTATION:
        cart[key].update({
            'dose': form.cleaned_data.get('dose', ''),
            'frequency': form.cleaned_data.get('frequency', ''),
            'duration': form.cleaned_data.get('duration', ''),
            'instructions': form.cleaned_data.get('instructions', ''),
            'dose_amount': str(form.cleaned_data['dose_amount']) if form.cleaned_data.get('dose_amount') is not None else '',
            'dose_unit': form.cleaned_data.get('dose_unit', ''),
            'frequency_per_day': str(form.cleaned_data['frequency_per_day']) if form.cleaned_data.get('frequency_per_day') is not None else '',
            'duration_days': form.cleaned_data.get('duration_days'),
        })
    _save_cart(request, txn.pk, cart)
    invalidate_clinical_review(txn)
    messages.success(request, f"'{medicine.generic_name}' updated in cart (qty: {new_total_qty}).")
    if txn.transaction_type == TransactionTypeChoices.CONSULTATION:
        return redirect('dispensing:consultation_cart', pk=txn.pk)
    return redirect('dispensing:sale_cart', pk=txn.pk)


# ---------------------------------------------------------------------------
# Remove from Cart
# ---------------------------------------------------------------------------

@login_required
def remove_from_cart(request, pk, medicine_id):
    """
    POST: removes a medicine (by medicine_id) from the session cart.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
    )

    if request.method != 'POST':
        if txn.transaction_type == TransactionTypeChoices.EXTERNAL_PRESCRIPTION:
            return redirect('dispensing:external_prescription_cart', pk=txn.pk)
        elif txn.transaction_type == TransactionTypeChoices.CONSULTATION:
            return redirect('dispensing:consultation_cart', pk=txn.pk)
        return redirect('dispensing:sale_cart', pk=txn.pk)

    cart = _get_cart(request, txn.pk)
    key = str(medicine_id)
    if key in cart:
        removed_name = cart[key]['medicine_name']
        del cart[key]
        _save_cart(request, txn.pk, cart)
        invalidate_clinical_review(txn)
        messages.success(request, f"'{removed_name}' removed from cart.")
    else:
        messages.warning(request, "Item not found in cart.")

    if txn.transaction_type == TransactionTypeChoices.EXTERNAL_PRESCRIPTION:
        return redirect('dispensing:external_prescription_cart', pk=txn.pk)
    elif txn.transaction_type == TransactionTypeChoices.CONSULTATION:
        return redirect('dispensing:consultation_cart', pk=txn.pk)
    return redirect('dispensing:sale_cart', pk=txn.pk)


# ---------------------------------------------------------------------------
# Confirm Sale
# ---------------------------------------------------------------------------

@login_required
def confirm_sale(request, pk):
    """
    POST: calls confirm_dispensing_from_cart atomically.
    On success: clears session cart, redirects to detail.
    On failure: shows errors in cart view.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
    )

    if request.method != 'POST':
        return redirect('dispensing:sale_cart', pk=txn.pk)

    cart = _get_cart(request, txn.pk)

    return _confirm_after_clinical_review(request, txn, cart, 'Transaction')


# ---------------------------------------------------------------------------
# Cancel Transaction
# ---------------------------------------------------------------------------

@login_required
def cancel_transaction(request, pk):
    """
    POST: marks a DRAFT transaction as CANCELLED. No stock is modified.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
    )

    if request.method != 'POST':
        if txn.transaction_type == TransactionTypeChoices.EXTERNAL_PRESCRIPTION:
            return redirect('dispensing:external_prescription_cart', pk=txn.pk)
        elif txn.transaction_type == TransactionTypeChoices.CONSULTATION:
            return redirect('dispensing:consultation_cart', pk=txn.pk)
        return redirect('dispensing:sale_cart', pk=txn.pk)

    txn.status = TransactionStatusChoices.CANCELLED
    txn.save(update_fields=['status'])
    _clear_cart(request, txn.pk)
    messages.info(request, f"Transaction {txn.transaction_number} has been cancelled.")
    return redirect('dispensing:transaction_list')


# ---------------------------------------------------------------------------
# Transaction History
# ---------------------------------------------------------------------------

@login_required
def transaction_list(request):
    """
    Paginated list of all dispensing transactions with search and filter.
    Both ADMIN and PHARMACY_STAFF can view.
    """
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    transactions = DispensingTransaction.objects.select_related('user').order_by('-created_at')

    if query:
        transactions = transactions.filter(
            Q(transaction_number__icontains=query) |
            Q(user__username__icontains=query) |
            Q(user__full_name__icontains=query)
        )
    if status_filter:
        transactions = transactions.filter(status=status_filter)
    if type_filter:
        transactions = transactions.filter(transaction_type=type_filter)

    paginator = Paginator(transactions, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'dispensing/transaction_list.html', {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'status_choices': TransactionStatusChoices.choices,
        'type_choices': TransactionTypeChoices.choices,
        'title': "Dispensing Transactions",
    })


# ---------------------------------------------------------------------------
# Transaction Detail
# ---------------------------------------------------------------------------

@login_required
def transaction_detail(request, pk):
    """
    Full detail view of a dispensing transaction and its items.
    Both ADMIN and PHARMACY_STAFF can view.
    """
    txn = get_object_or_404(
        DispensingTransaction.objects.select_related('user', 'external_prescription', 'clinical_review').prefetch_related(
            'items__medicine', 'items__batch', 'clinical_alerts__medicine_a',
            'clinical_alerts__medicine_b', 'clinical_alerts__allergen',
            'clinical_alerts__acknowledged_by', 'clinical_check_results',
            'consultation__structured_allergies',
        ),
        pk=pk,
    )

    results = {result.check_type: result for result in txn.clinical_check_results.all()}
    alerts = list(txn.clinical_alerts.all())
    return render(request, 'dispensing/transaction_detail.html', {
        'txn': txn,
        'historical_interaction_result': results.get(ClinicalCheckType.DRUG_INTERACTION),
        'historical_allergy_result': results.get(ClinicalCheckType.ALLERGY),
        'historical_dosage_result': results.get(ClinicalCheckType.DOSAGE),
        'historical_interaction_alerts': [alert for alert in alerts if alert.alert_type == AlertTypeChoices.DRUG_INTERACTION],
        'historical_allergy_alerts': [alert for alert in alerts if alert.alert_type == AlertTypeChoices.ALLERGY],
        'historical_dosage_alerts': [alert for alert in alerts if alert.alert_type == AlertTypeChoices.DOSAGE],
        'title': f"Transaction {txn.transaction_number}",
        'historical_risk_assessment': getattr(txn, 'risk_assessment', None),
    })


# ---------------------------------------------------------------------------
# Medicine Search JSON API
# ---------------------------------------------------------------------------

@login_required
def medicine_search_json(request):
    """
    Returns JSON list of active medicines matching the ?q= query.
    Used by the cart search widget (JS fetch).
    """
    query = request.GET.get('q', '').strip()
    results = []

    if len(query) >= 2:
        medicines = Medicine.objects.filter(
            is_active=True,
        ).filter(
            Q(generic_name__icontains=query) |
            Q(brand_name__icontains=query)
        ).order_by('generic_name')[:15]

        for med in medicines:
            stock = med.total_available_stock
            results.append({
                'id': med.pk,
                'name': str(med),
                'available_stock': stock,
                'has_stock': stock > 0,
                'unit': med.get_unit_display() if hasattr(med, 'get_unit_display') else '',
            })

    return JsonResponse({'results': results})

# ---------------------------------------------------------------------------
# External Prescription Workflow
# ---------------------------------------------------------------------------

@login_required
def new_external_prescription(request):
    """
    Creates a new DRAFT DispensingTransaction for an external prescription.
    """
    txn = DispensingTransaction.objects.create(
        user=request.user,
        transaction_type=TransactionTypeChoices.EXTERNAL_PRESCRIPTION,
        status=TransactionStatusChoices.DRAFT,
    )
    _save_cart(request, txn.pk, {})
    return redirect('dispensing:external_prescription_cart', pk=txn.pk)


@login_required
def external_prescription_cart(request, pk):
    """
    Displays the prescription metadata form and the cart for medicines.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
        transaction_type=TransactionTypeChoices.EXTERNAL_PRESCRIPTION
    )

    cart = _get_cart(request, txn.pk)
    from .services import get_valid_batches_fefo
    cart_display = []
    preview_total = Decimal('0.00')
    for med_id_str, line in cart.items():
        try:
            med = Medicine.objects.get(pk=int(med_id_str))
            first_batch = get_valid_batches_fefo(med).first()
            price = first_batch.selling_price if first_batch else Decimal('0.00')
            avail = med.total_available_stock
        except Medicine.DoesNotExist:
            price = Decimal('0.00')
            avail = 0
            med = None
        qty = line['quantity']
        line_total = price * Decimal(str(qty))
        preview_total += line_total
        cart_display.append({
            'medicine_id': int(med_id_str),
            'medicine_name': line['medicine_name'],
            'quantity': qty,
            'unit_price': price,
            'line_total': line_total,
            'available': avail,
            'dose': line.get('dose', ''),
            'frequency': line.get('frequency', ''),
            'duration': line.get('duration', ''),
            'instructions': line.get('instructions', ''),
            'dose_amount': line.get('dose_amount', ''),
            'dose_unit': line.get('dose_unit', ''),
            'frequency_per_day': line.get('frequency_per_day', ''),
            'duration_days': line.get('duration_days', ''),
        })

    item_form = PrescriptionItemForm()

    # Try to load existing metadata
    metadata = getattr(txn, 'external_prescription', None)
    meta_form = ExternalPrescriptionForm(instance=metadata)

    context = {
        'txn': txn,
        'cart_display': cart_display,
        'preview_total': preview_total,
        'item_form': item_form,
        'meta_form': meta_form,
        'title': f"External Prescription — {txn.transaction_number}",
    }
    context.update(_clinical_context(txn, cart))
    return render(request, 'dispensing/external_prescription_cart.html', context)


@login_required
def external_prescription_add_to_cart(request, pk):
    """
    POST: Adds a medicine with optional clinical dosage fields to the cart.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
        transaction_type=TransactionTypeChoices.EXTERNAL_PRESCRIPTION
    )

    if request.method != 'POST':
        return redirect('dispensing:external_prescription_cart', pk=txn.pk)

    form = PrescriptionItemForm(request.POST)
    if not form.is_valid():
        for field_errors in form.errors.values():
            for err in field_errors:
                messages.error(request, err)
        return redirect('dispensing:external_prescription_cart', pk=txn.pk)

    medicine_id = form.cleaned_data['medicine_id']
    quantity = form.cleaned_data['quantity']

    try:
        medicine = Medicine.objects.get(pk=medicine_id, is_active=True)
    except Medicine.DoesNotExist:
        messages.error(request, "Selected medicine is not available.")
        return redirect('dispensing:external_prescription_cart', pk=txn.pk)

    cart = _get_cart(request, txn.pk)
    key = str(medicine_id)

    # Merge quantity if medicine already in cart
    existing_qty = cart[key]['quantity'] if key in cart else 0
    new_total_qty = existing_qty + quantity

    try:
        check_stock_availability(medicine, new_total_qty)
    except ValidationError as e:
        messages.error(request, e.message)
        return redirect('dispensing:external_prescription_cart', pk=txn.pk)

    # Note: If adding same med multiple times, this overwrites instructions with the latest ones.
    cart[key] = {
        'medicine_id': medicine.pk,
        'medicine_name': str(medicine),
        'quantity': new_total_qty,
        'dose': form.cleaned_data.get('dose', ''),
        'frequency': form.cleaned_data.get('frequency', ''),
        'duration': form.cleaned_data.get('duration', ''),
        'instructions': form.cleaned_data.get('instructions', ''),
        'dose_amount': str(form.cleaned_data['dose_amount']) if form.cleaned_data.get('dose_amount') is not None else '',
        'dose_unit': form.cleaned_data.get('dose_unit', ''),
        'frequency_per_day': str(form.cleaned_data['frequency_per_day']) if form.cleaned_data.get('frequency_per_day') is not None else '',
        'duration_days': form.cleaned_data.get('duration_days'),
    }
    _save_cart(request, txn.pk, cart)
    invalidate_clinical_review(txn)
    messages.success(request, f"'{medicine.generic_name}' updated in prescription.")
    return redirect('dispensing:external_prescription_cart', pk=txn.pk)


@login_required
def external_prescription_save_metadata(request, pk):
    """
    POST: Saves or updates the ExternalPrescription metadata record.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
        transaction_type=TransactionTypeChoices.EXTERNAL_PRESCRIPTION
    )

    if request.method == 'POST':
        metadata = getattr(txn, 'external_prescription', None)
        form = ExternalPrescriptionForm(request.POST, instance=metadata)
        if form.is_valid():
            prescription = form.save(commit=False)
            prescription.transaction = txn
            prescription.save()
            messages.success(request, "Prescription metadata saved.")
        else:
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)

    return redirect('dispensing:external_prescription_cart', pk=txn.pk)


@login_required
def confirm_external_prescription(request, pk):
    """
    POST: Confirms the external prescription transaction.
    """
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
        transaction_type=TransactionTypeChoices.EXTERNAL_PRESCRIPTION
    )

    if request.method != 'POST':
        return redirect('dispensing:external_prescription_cart', pk=txn.pk)

    cart = _get_cart(request, txn.pk)

    return _confirm_after_clinical_review(request, txn, cart, 'External Prescription')


# ---------------------------------------------------------------------------
# Consultation Workflow
# ---------------------------------------------------------------------------

@login_required
def new_consultation(request):
    txn = DispensingTransaction.objects.create(
        user=request.user,
        transaction_type=TransactionTypeChoices.CONSULTATION,
        status=TransactionStatusChoices.DRAFT,
    )
    _save_cart(request, txn.pk, {})
    return redirect('dispensing:consultation_cart', pk=txn.pk)


@login_required
def consultation_cart(request, pk):
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
        transaction_type=TransactionTypeChoices.CONSULTATION
    )

    cart = _get_cart(request, txn.pk)

    from .services import get_valid_batches_fefo
    cart_display = []
    preview_total = Decimal('0.00')
    for med_id_str, line in cart.items():
        try:
            med = Medicine.objects.get(pk=int(med_id_str))
            first_batch = get_valid_batches_fefo(med).first()
            price = first_batch.selling_price if first_batch else Decimal('0.00')
            avail = med.total_available_stock
        except Medicine.DoesNotExist:
            price = Decimal('0.00')
            avail = 0
            med = None
        qty = line['quantity']
        line_total = price * Decimal(str(qty))
        preview_total += line_total
        cart_display.append({
            'medicine_id': int(med_id_str),
            'medicine_name': line['medicine_name'],
            'quantity': qty,
            'unit_price': price,
            'line_total': line_total,
            'available': avail,
            'dose': line.get('dose', ''),
            'frequency': line.get('frequency', ''),
            'duration': line.get('duration', ''),
            'instructions': line.get('instructions', ''),
            'dose_amount': line.get('dose_amount', ''),
            'dose_unit': line.get('dose_unit', ''),
            'frequency_per_day': line.get('frequency_per_day', ''),
            'duration_days': line.get('duration_days', ''),
        })

    item_form = PrescriptionItemForm()

    from .forms import ConsultationForm
    metadata = getattr(txn, 'consultation', None)
    meta_form = ConsultationForm(instance=metadata)

    context = {
        'txn': txn,
        'cart_display': cart_display,
        'preview_total': preview_total,
        'item_form': item_form,
        'meta_form': meta_form,
        'title': f"Consultation \u2014 {txn.transaction_number}",
    }
    context.update(_clinical_context(txn, cart))
    return render(request, 'dispensing/consultation_cart.html', context)


@login_required
def consultation_save_metadata(request, pk):
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
        transaction_type=TransactionTypeChoices.CONSULTATION
    )

    if request.method == 'POST':
        from .forms import ConsultationForm
        metadata = getattr(txn, 'consultation', None)
        form = ConsultationForm(request.POST, instance=metadata)
        if form.is_valid():
            previous_allergen_ids = set(metadata.structured_allergies.values_list('pk', flat=True)) if metadata else set()
            previous_context = (metadata.age, metadata.weight) if metadata else (None, None)
            consultation = form.save(commit=False)
            consultation.transaction = txn
            consultation.save()
            form.save_m2m()
            current_allergen_ids = set(consultation.structured_allergies.values_list('pk', flat=True))
            if previous_allergen_ids != current_allergen_ids or previous_context != (consultation.age, consultation.weight):
                invalidate_clinical_review(txn)
            messages.success(request, "Consultation metadata saved.")
        else:
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)

    return redirect('dispensing:consultation_cart', pk=txn.pk)


@login_required
def confirm_consultation(request, pk):
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
        transaction_type=TransactionTypeChoices.CONSULTATION
    )

    if request.method != 'POST':
        return redirect('dispensing:consultation_cart', pk=txn.pk)

    cart = _get_cart(request, txn.pk)

    return _confirm_after_clinical_review(request, txn, cart, 'Consultation')


@login_required
def run_clinical_review(request, pk):
    txn = get_object_or_404(
        DispensingTransaction,
        pk=pk,
        user=request.user,
        status=TransactionStatusChoices.DRAFT,
    )
    if request.method == 'POST':
        result = execute_clinical_review(txn, _get_cart(request, txn.pk))
        if result['status'] == ClinicalCheckStatus.WARNING:
            messages.warning(request, f"Clinical review found {len(result['alerts'])} warning(s).")
        elif result['status'] == ClinicalCheckStatus.PASSED:
            messages.success(request, 'Clinical review completed with no matching active rules in applicable checks.')
        elif result['status'] == ClinicalCheckStatus.NOT_APPLICABLE:
            messages.info(request, 'Drug interaction checking is not applicable with fewer than two medicines.')
        else:
            messages.error(request, 'The clinical review could not be completed.')
    return _cart_redirect(txn)
