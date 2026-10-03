from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q

from medicines.permissions import admin_required
from medicines.models import Medicine, MedicineCategory
from .models import MedicineBatch, StockTransaction
from .forms import MedicineBatchCreateForm, MedicineBatchUpdateForm, StockAdjustmentForm
from .services import create_medicine_batch, adjust_batch_stock
from django.core.exceptions import ValidationError
from datetime import date
from django.utils import timezone


def _inventory_medicines():
    valid_batches = MedicineBatch.objects.filter(
        is_active=True,
        expiry_date__gt=date.today(),
        quantity_remaining__gt=0,
    ).order_by('expiry_date')
    return Medicine.objects.select_related('category').prefetch_related(
        Prefetch('batches', queryset=valid_batches, to_attr='_valid_batches_cache')
    )


@login_required
def inventory_list(request):
    """
    Main inventory overview. Displays medicines and their aggregated stock info.
    """
    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    
    medicines = _inventory_medicines()
    
    if query:
        medicines = medicines.filter(
            Q(generic_name__icontains=query) |
            Q(brand_name__icontains=query)
        )
        
    if category_id:
        medicines = medicines.filter(category_id=category_id)
        
    # We sort by generic name by default (from model Meta)
    
    paginator = Paginator(medicines, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    categories = MedicineCategory.objects.all()
    
    return render(request, 'inventory/inventory_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'query': query,
        'category_id': category_id,
        'title': "Inventory Overview"
    })


@login_required
def low_stock_list(request):
    """
    Displays medicines where total_available_stock <= minimum_stock_level.
    """
    # Note: Because total_available_stock is a property and not a DB field, 
    # we have to compute it in Python for the full list, or use a complex 
    # subquery/annotation. For simplicity and correctness with the existing
    # property, we can filter in Python, but that prevents DB-level pagination.
    # Given the requirements, let's filter in python.
    
    medicines = _inventory_medicines()
    
    low_stock_medicines = [m for m in medicines if m.total_available_stock <= m.minimum_stock_level]
    
    paginator = Paginator(low_stock_medicines, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/low_stock_list.html', {
        'page_obj': page_obj,
        'title': "Low Stock Alerts"
    })


@login_required
def expiry_list(request):
    """
    Displays batches that are expired or expiring soon.
    """
    thirty_days_from_now = date.today() + timezone.timedelta(days=30)
    
    # Get active batches that are expired or expiring within 30 days
    batches = MedicineBatch.objects.select_related('medicine').filter(
        is_active=True,
        expiry_date__lte=thirty_days_from_now
    ).order_by('expiry_date')
    
    paginator = Paginator(batches, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/expiry_list.html', {
        'page_obj': page_obj,
        'title': "Expiry Alerts"
    })


@login_required
def batch_list(request):
    """
    Lists all batches, optionally filtered by a specific medicine.
    """
    medicine_id = request.GET.get('medicine')
    query = request.GET.get('q', '')
    
    batches = MedicineBatch.objects.select_related('medicine')
    
    if medicine_id:
        batches = batches.filter(medicine_id=medicine_id)
        
    if query:
        batches = batches.filter(batch_number__icontains=query)
        
    paginator = Paginator(batches, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/batch_list.html', {
        'page_obj': page_obj,
        'query': query,
        'medicine_id': medicine_id,
        'title': "Medicine Batches"
    })


@login_required
def batch_detail(request, pk):
    batch = get_object_or_404(MedicineBatch.objects.select_related('medicine'), pk=pk)
    transactions = batch.transactions.select_related('user').order_by('-created_at')
    
    return render(request, 'inventory/batch_detail.html', {
        'batch': batch,
        'transactions': transactions
    })


@login_required
@admin_required
def batch_create(request):
    if request.method == 'POST':
        form = MedicineBatchCreateForm(request.POST)
        if form.is_valid():
            try:
                batch = create_medicine_batch(form.cleaned_data, request.user)
                messages.success(request, f"Batch {batch.batch_number} added successfully.")
                return redirect('inventory:batch_detail', pk=batch.pk)
            except ValidationError as e:
                form.add_error(None, e)
    else:
        # Pre-select medicine if passed in URL
        initial = {}
        if 'medicine' in request.GET:
            initial['medicine'] = request.GET.get('medicine')
        form = MedicineBatchCreateForm(initial=initial)
        
    return render(request, 'inventory/batch_form.html', {
        'form': form,
        'title': "Add Medicine Batch"
    })


@login_required
@admin_required
def batch_update(request, pk):
    batch = get_object_or_404(MedicineBatch, pk=pk)
    
    if request.method == 'POST':
        form = MedicineBatchUpdateForm(request.POST, instance=batch)
        if form.is_valid():
            form.save()
            messages.success(request, f"Batch {batch.batch_number} updated successfully.")
            return redirect('inventory:batch_detail', pk=batch.pk)
    else:
        form = MedicineBatchUpdateForm(instance=batch)
        
    return render(request, 'inventory/batch_form.html', {
        'form': form,
        'title': f"Edit Batch: {batch.batch_number}",
        'batch': batch
    })


@login_required
@admin_required
def batch_adjust(request, pk):
    batch = get_object_or_404(MedicineBatch, pk=pk)
    
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            try:
                adjust_batch_stock(
                    batch=batch,
                    user=request.user,
                    adjustment_type=form.cleaned_data['adjustment_type'],
                    quantity=form.cleaned_data['quantity'],
                    notes=form.cleaned_data['notes']
                )
                if form.cleaned_data['adjustment_type'] == 'INCREASE':
                    messages.success(request, "Stock increased successfully.")
                else:
                    messages.success(request, "Stock reduced successfully.")
                    
                return redirect('inventory:batch_detail', pk=batch.pk)
            except ValidationError as e:
                form.add_error(None, e.messages)
            except ValueError as e:
                form.add_error(None, str(e))
    else:
        form = StockAdjustmentForm()
        
    return render(request, 'inventory/stock_adjustment_form.html', {
        'form': form,
        'batch': batch
    })


@login_required
@admin_required
def transaction_list(request):
    transactions = StockTransaction.objects.select_related('batch__medicine', 'user').order_by('-created_at')
    
    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/transaction_list.html', {
        'page_obj': page_obj,
        'title': "Stock Transactions"
    })
