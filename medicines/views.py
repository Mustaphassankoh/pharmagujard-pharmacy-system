from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_POST

from .models import MedicineCategory, Medicine, DosageFormChoices
from .forms import MedicineCategoryForm, MedicineForm
from .permissions import admin_required, is_admin


# ==========================================
# Category Management Views (Admin Only)
# ==========================================

@admin_required
def category_list(request):
    """List all medicine categories with associated medicine counts."""
    categories = MedicineCategory.objects.annotate(medicine_count=Count('medicines')).order_by('name')
    return render(request, 'medicines/category_list.html', {
        'categories': categories,
        'is_admin': is_admin(request.user),
    })


@admin_required
def category_create(request):
    """Add a new medicine category."""
    if request.method == 'POST':
        form = MedicineCategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f"Category '{category.name}' created successfully.")
            return redirect('medicines:category_list')
    else:
        form = MedicineCategoryForm()

    return render(request, 'medicines/category_form.html', {
        'form': form,
        'title': 'Add Medicine Category',
        'button_text': 'Create Category',
        'is_admin': is_admin(request.user),
    })


@admin_required
def category_update(request, pk):
    """Edit an existing medicine category."""
    category = get_object_or_404(MedicineCategory, pk=pk)
    if request.method == 'POST':
        form = MedicineCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(request, f"Category '{category.name}' updated successfully.")
            return redirect('medicines:category_list')
    else:
        form = MedicineCategoryForm(instance=category)

    return render(request, 'medicines/category_form.html', {
        'form': form,
        'category': category,
        'title': f'Edit Category: {category.name}',
        'button_text': 'Update Category',
        'is_admin': is_admin(request.user),
    })


@admin_required
@require_POST
def category_toggle_status(request, pk):
    """Soft toggle category active status."""
    category = get_object_or_404(MedicineCategory, pk=pk)
    category.is_active = not category.is_active
    category.save()
    status_str = "activated" if category.is_active else "deactivated"
    messages.success(request, f"Category '{category.name}' {status_str} successfully.")
    return redirect('medicines:category_list')


# ==========================================
# Medicine Management Views
# ==========================================

@login_required
def medicine_list(request):
    """List medicines with search, filtering, and pagination."""
    queryset = Medicine.objects.select_related('category').all()

    # Search (generic_name or brand_name)
    query = request.GET.get('q', '').strip()
    if query:
        queryset = queryset.filter(
            Q(generic_name__icontains=query) | Q(brand_name__icontains=query)
        )

    # Category filter
    category_id = request.GET.get('category', '').strip()
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    # Dosage Form filter
    dosage_form = request.GET.get('dosage_form', '').strip()
    if dosage_form:
        queryset = queryset.filter(dosage_form=dosage_form)

    # Status filter
    status = request.GET.get('status', '').strip()
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    # Ordering
    queryset = queryset.order_by('generic_name', 'brand_name')

    # Pagination
    paginator = Paginator(queryset, 15)  # 15 per page
    page = request.GET.get('page', 1)
    try:
        medicines = paginator.page(page)
    except PageNotAnInteger:
        medicines = paginator.page(1)
    except EmptyPage:
        medicines = paginator.page(paginator.num_pages)

    # Build querystring without 'page' for pagination links
    query_params = request.GET.copy()
    if 'page' in query_params:
        query_params.pop('page')
    querystring = query_params.urlencode()

    categories = MedicineCategory.objects.all().order_by('name')

    return render(request, 'medicines/medicine_list.html', {
        'medicines': medicines,
        'categories': categories,
        'dosage_forms': DosageFormChoices.choices,
        'search_query': query,
        'selected_category': category_id,
        'selected_dosage_form': dosage_form,
        'selected_status': status,
        'querystring': querystring,
        'total_count': paginator.count,
        'is_admin': is_admin(request.user),
    })


@login_required
def medicine_detail(request, pk):
    """Display detailed information about a medicine."""
    medicine = get_object_or_404(Medicine.objects.select_related('category'), pk=pk)
    return render(request, 'medicines/medicine_detail.html', {
        'medicine': medicine,
        'is_admin': is_admin(request.user),
    })


@admin_required
def medicine_create(request):
    """Add a new medicine to the formulary."""
    if request.method == 'POST':
        form = MedicineForm(request.POST)
        if form.is_valid():
            medicine = form.save()
            messages.success(request, f"Medicine '{medicine.generic_name}' created successfully.")
            return redirect('medicines:medicine_detail', pk=medicine.pk)
    else:
        form = MedicineForm()

    return render(request, 'medicines/medicine_form.html', {
        'form': form,
        'title': 'Add New Medicine',
        'button_text': 'Save Medicine',
        'is_admin': is_admin(request.user),
    })


@admin_required
def medicine_update(request, pk):
    """Edit an existing medicine."""
    medicine = get_object_or_404(Medicine, pk=pk)
    if request.method == 'POST':
        form = MedicineForm(request.POST, instance=medicine)
        if form.is_valid():
            medicine = form.save()
            messages.success(request, f"Medicine '{medicine.generic_name}' updated successfully.")
            return redirect('medicines:medicine_detail', pk=medicine.pk)
    else:
        form = MedicineForm(instance=medicine)

    return render(request, 'medicines/medicine_form.html', {
        'form': form,
        'medicine': medicine,
        'title': f'Edit Medicine: {medicine.generic_name}',
        'button_text': 'Update Medicine',
        'is_admin': is_admin(request.user),
    })


@admin_required
@require_POST
def medicine_toggle_status(request, pk):
    """Soft toggle medicine active status."""
    medicine = get_object_or_404(Medicine, pk=pk)
    medicine.is_active = not medicine.is_active
    medicine.save()
    status_str = "activated" if medicine.is_active else "deactivated"
    messages.success(request, f"Medicine '{medicine.generic_name}' {status_str} successfully.")
    
    # Redirect back to referring page or detail
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('medicines:medicine_detail', pk=medicine.pk)
