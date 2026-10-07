from django.contrib.auth.models import AbstractUser
from django.db import models


class Pharmacy(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    license_number = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Pharmacies'
        ordering = ['name']

    def __str__(self):
        return self.name


class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Administrator'),
        ('PHARMACY_STAFF', 'Pharmacy Staff'),
    )
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='PHARMACY_STAFF')
    pharmacy = models.ForeignKey(
        Pharmacy, null=True, blank=True, on_delete=models.PROTECT, related_name='users'
    )
    updated_at = models.DateTimeField(auto_now=True)
    # created_at is handled by AbstractUser's date_joined

    def save(self, *args, **kwargs):
        # The ADMIN role is the application's authorization source for the
        # Django Admin-based clinical governance and ML management surfaces.
        if not self.is_superuser:
            self.is_staff = self.role == 'ADMIN'
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = set(kwargs['update_fields']) | {'is_staff'}
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
