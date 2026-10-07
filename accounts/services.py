from django.db import transaction

from .models import Pharmacy, User


@transaction.atomic
def register_pharmacy_with_admin(data):
    """Create one pharmacy and its first administrator as one database unit."""
    pharmacy = Pharmacy.objects.create(
        name=data['pharmacy_name'],
        address=data['pharmacy_address'],
        phone=data['pharmacy_phone'],
        email=data['pharmacy_email'].strip().lower(),
        license_number=data.get('license_number', '').strip(),
    )
    user = User.objects.create_user(
        username=data['admin_username'],
        email=data['admin_email'],
        password=data['password1'],
        full_name=data['admin_full_name'].strip(),
        role='ADMIN',
        pharmacy=pharmacy,
    )
    return pharmacy, user

