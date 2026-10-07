from django.contrib import messages
from django.contrib.auth import login
from django.db import IntegrityError
from django.db.models import Count, DecimalField, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST

from datetime import timedelta
from decimal import Decimal

from medicines.permissions import admin_required
from .forms import (
    PharmacyProfileForm, PharmacyRegistrationForm, StaffCreateForm,
    StaffPasswordForm, StaffUpdateForm,
)
from .models import Pharmacy, User
from .services import register_pharmacy_with_admin

@login_required
def dashboard_view(request):
    from medicines.models import Medicine
    from dispensing.models import (
        DispensingItem, DispensingTransaction, TransactionStatusChoices, TransactionTypeChoices,
    )
    from .tenancy import scope_queryset

    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    medicines = scope_queryset(Medicine.objects.all(), request.user)
    transactions = scope_queryset(DispensingTransaction.objects.all(), request.user)
    completed_today = transactions.filter(
        status=TransactionStatusChoices.COMPLETED,
        completed_at__date=today,
    )

    stock_totals = medicines.annotate(
        available_stock=Coalesce(
            Sum(
                'batches__quantity_remaining',
                filter=Q(
                    batches__is_active=True,
                    batches__expiry_date__gt=today,
                    batches__quantity_remaining__gt=0,
                ),
            ),
            Value(0),
            output_field=IntegerField(),
        )
    )
    low_stock_alerts = stock_totals.filter(
        available_stock__lte=F('minimum_stock_level')
    ).count()

    today_summary = completed_today.aggregate(
        sales=Coalesce(
            Sum('total_amount'), Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
    )
    medicines_dispensed_today = DispensingItem.objects.filter(
        transaction__in=completed_today,
    ).aggregate(
        total=Coalesce(Sum('quantity'), Value(0), output_field=IntegerField()),
    )['total']
    activity_counts = {
        row['transaction_type']: row['count']
        for row in completed_today.order_by().values('transaction_type').annotate(count=Count('id'))
    }

    daily_rows = {
        row['day']: row['count']
        for row in transactions.filter(
            status=TransactionStatusChoices.COMPLETED,
            completed_at__date__range=(start_date, today),
        ).order_by().annotate(day=TruncDate('completed_at')).values('day').annotate(count=Count('id'))
    }
    chart_days = [
        {'date': start_date + timedelta(days=offset),
         'count': daily_rows.get(start_date + timedelta(days=offset), 0)}
        for offset in range(7)
    ]
    chart_max = max((day['count'] for day in chart_days), default=0)
    for day in chart_days:
        day['height'] = round((day['count'] / chart_max) * 100) if chart_max else 0

    context = {
        'total_medicines': medicines.count(),
        'low_stock_alerts': low_stock_alerts,
        'today_sales': today_summary['sales'],
        'pending_prescriptions': transactions.filter(
            transaction_type=TransactionTypeChoices.EXTERNAL_PRESCRIPTION,
            status=TransactionStatusChoices.DRAFT,
        ).count(),
        'direct_sales_today': activity_counts.get(TransactionTypeChoices.DIRECT_SALE, 0),
        'consultations_today': activity_counts.get(TransactionTypeChoices.CONSULTATION, 0),
        'external_prescriptions_today': activity_counts.get(TransactionTypeChoices.EXTERNAL_PRESCRIPTION, 0),
        'medicines_dispensed_today': medicines_dispensed_today,
        'transactions_today': completed_today.count(),
        'chart_days': chart_days,
        'chart_total': sum(day['count'] for day in chart_days),
    }
    return render(request, 'dashboard.html', context)

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'public/landing.html')


def features_view(request):
    return render(request, 'public/features.html')


def about_view(request):
    return render(request, 'public/about.html')


def how_it_works_view(request):
    return render(request, 'public/how_it_works.html')


def register_pharmacy_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = PharmacyRegistrationForm(request.POST)
        if form.is_valid():
            try:
                pharmacy, user = register_pharmacy_with_admin(form.cleaned_data)
            except IntegrityError:
                form.add_error(None, 'Registration could not be completed. Please review the details and try again.')
            else:
                login(request, user)
                messages.success(request, f'{pharmacy.name} is ready. Welcome to PharmaGuard.')
                return redirect('dashboard')
    else:
        form = PharmacyRegistrationForm()
    return render(request, 'public/register.html', {'form': form})


def _staff_for_admin(request, pk=None):
    queryset = User.objects.filter(
        pharmacy_id=request.user.pharmacy_id,
        role='PHARMACY_STAFF',
        is_superuser=False,
    )
    return get_object_or_404(queryset, pk=pk) if pk is not None else queryset


@admin_required
def staff_list(request):
    staff = _staff_for_admin(request).order_by('full_name', 'username')
    return render(request, 'accounts/staff_list.html', {'staff': staff})


@admin_required
def staff_create(request):
    form = StaffCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        staff = User.objects.create_user(
            username=form.cleaned_data['username'],
            email=form.cleaned_data['email'],
            password=form.cleaned_data['password1'],
            full_name=form.cleaned_data['full_name'].strip(),
            role='PHARMACY_STAFF',
            pharmacy=request.user.pharmacy,
        )
        messages.success(request, f'{staff.full_name} can now sign in to this pharmacy.')
        return redirect('staff_list')
    return render(request, 'accounts/staff_form.html', {'form': form, 'title': 'Add Pharmacy Staff', 'button_text': 'Create Staff Account'})


@admin_required
def staff_update(request, pk):
    staff = _staff_for_admin(request, pk)
    form = StaffUpdateForm(request.POST or None, instance=staff)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Staff information updated.')
        return redirect('staff_list')
    return render(request, 'accounts/staff_form.html', {'form': form, 'staff_member': staff, 'title': 'Edit Staff', 'button_text': 'Save Changes'})


@admin_required
@require_POST
def staff_deactivate(request, pk):
    staff = _staff_for_admin(request, pk)
    staff.is_active = False
    staff.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, f'{staff.full_name} has been deactivated.')
    return redirect('staff_list')


@admin_required
def staff_password(request, pk):
    staff = _staff_for_admin(request, pk)
    form = StaffPasswordForm(request.POST or None, user=staff)
    if request.method == 'POST' and form.is_valid():
        staff.set_password(form.cleaned_data['password1'])
        staff.save(update_fields=['password', 'updated_at'])
        messages.success(request, f'Password updated for {staff.full_name}.')
        return redirect('staff_list')
    return render(request, 'accounts/staff_password.html', {'form': form, 'staff_member': staff})


@admin_required
def pharmacy_profile(request):
    pharmacy = get_object_or_404(Pharmacy, pk=request.user.pharmacy_id)
    form = PharmacyProfileForm(request.POST or None, instance=pharmacy)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Pharmacy profile updated.')
        return redirect('pharmacy_profile')
    return render(request, 'accounts/pharmacy_profile.html', {'form': form, 'pharmacy': pharmacy})
