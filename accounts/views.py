from django.contrib import messages
from django.contrib.auth import login
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

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
    from .tenancy import scope_queryset
    total_medicines = scope_queryset(Medicine.objects.all(), request.user).count()
    return render(request, 'dashboard.html', {'total_medicines': total_medicines})

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
