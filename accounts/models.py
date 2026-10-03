from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('ADMIN', 'Administrator'),
        ('PHARMACY_STAFF', 'Pharmacy Staff'),
    )
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='PHARMACY_STAFF')
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
