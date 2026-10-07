from django import forms
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError

from .models import Pharmacy, User


class PharmacyRegistrationForm(forms.Form):
    pharmacy_name = forms.CharField(label='Pharmacy Name', max_length=255)
    pharmacy_address = forms.CharField(label='Address', widget=forms.Textarea(attrs={'rows': 3}))
    pharmacy_phone = forms.CharField(label='Phone', max_length=50)
    pharmacy_email = forms.EmailField(label='Email')
    license_number = forms.CharField(label='License Number', max_length=100, required=False)
    admin_full_name = forms.CharField(label='Full Name', max_length=255)
    admin_username = forms.CharField(label='Username', max_length=150)
    admin_email = forms.EmailField(label='Email')
    password1 = forms.CharField(label='Password', strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', strip=False, widget=forms.PasswordInput)

    def clean_pharmacy_name(self):
        name = self.cleaned_data['pharmacy_name'].strip()
        if Pharmacy.objects.filter(name__iexact=name).exists():
            raise ValidationError('A pharmacy with this name is already registered.')
        return name

    def clean_admin_username(self):
        username = self.cleaned_data['admin_username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('This username is already in use.')
        return username

    def clean_admin_email(self):
        email = self.cleaned_data['admin_email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The two password fields did not match.')
        if password1:
            candidate = User(
                username=cleaned_data.get('admin_username', ''),
                email=cleaned_data.get('admin_email', ''),
                full_name=cleaned_data.get('admin_full_name', ''),
            )
            try:
                password_validation.validate_password(password1, candidate)
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned_data


class StaffCreateForm(forms.Form):
    full_name = forms.CharField(label='Full Name', max_length=255)
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password1 = forms.CharField(label='Password', strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm Password', strip=False, widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('This username is already in use.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get('password1'), cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The two password fields did not match.')
        if password1:
            candidate = User(username=cleaned.get('username', ''), email=cleaned.get('email', ''), full_name=cleaned.get('full_name', ''))
            try:
                password_validation.validate_password(password1, candidate)
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned


class StaffUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('full_name', 'username', 'email')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise ValidationError('This username is already in use.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('An account with this email already exists.')
        return email


class StaffPasswordForm(forms.Form):
    password1 = forms.CharField(label='New Password', strip=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm New Password', strip=False, widget=forms.PasswordInput)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned = super().clean()
        password1, password2 = cleaned.get('password1'), cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The two password fields did not match.')
        if password1:
            try:
                password_validation.validate_password(password1, self.user)
            except ValidationError as exc:
                self.add_error('password1', exc)
        return cleaned


class PharmacyProfileForm(forms.ModelForm):
    class Meta:
        model = Pharmacy
        fields = ('name', 'address', 'phone', 'email', 'license_number')
        widgets = {'address': forms.Textarea(attrs={'rows': 3})}

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if Pharmacy.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise ValidationError('A pharmacy with this name is already registered.')
        return name
