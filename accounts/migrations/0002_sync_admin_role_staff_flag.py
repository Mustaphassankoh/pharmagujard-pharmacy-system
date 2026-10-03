from django.db import migrations


def sync_admin_staff_flags(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role='ADMIN').update(is_staff=True)
    User.objects.filter(role='PHARMACY_STAFF', is_superuser=False).update(is_staff=False)


def reverse_sync(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role='ADMIN', is_superuser=False).update(is_staff=False)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_initial')]
    operations = [migrations.RunPython(sync_admin_staff_flags, reverse_sync)]
