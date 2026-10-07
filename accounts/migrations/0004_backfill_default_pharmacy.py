from django.db import migrations


DEFAULT_PHARMACY_NAME = 'PharmaGuard Demo Pharmacy'


def assign_default_pharmacy(apps, schema_editor):
    Pharmacy = apps.get_model('accounts', 'Pharmacy')
    User = apps.get_model('accounts', 'User')
    MedicineCategory = apps.get_model('medicines', 'MedicineCategory')
    Medicine = apps.get_model('medicines', 'Medicine')
    DispensingTransaction = apps.get_model('dispensing', 'DispensingTransaction')
    Allergen = apps.get_model('clinical', 'Allergen')
    AllergyRule = apps.get_model('clinical', 'AllergyRule')
    DosageRule = apps.get_model('clinical', 'DosageRule')
    DrugInteractionRule = apps.get_model('clinical', 'DrugInteractionRule')

    pharmacy, _ = Pharmacy.objects.get_or_create(name=DEFAULT_PHARMACY_NAME)
    User.objects.filter(pharmacy__isnull=True, is_superuser=False).update(pharmacy=pharmacy)
    MedicineCategory.objects.filter(pharmacy__isnull=True).update(pharmacy=pharmacy)
    Medicine.objects.filter(pharmacy__isnull=True).update(pharmacy=pharmacy)
    DispensingTransaction.objects.filter(pharmacy__isnull=True).update(pharmacy=pharmacy)
    Allergen.objects.filter(pharmacy__isnull=True).update(pharmacy=pharmacy)
    AllergyRule.objects.filter(pharmacy__isnull=True).update(pharmacy=pharmacy)
    DosageRule.objects.filter(pharmacy__isnull=True).update(pharmacy=pharmacy)
    DrugInteractionRule.objects.filter(pharmacy__isnull=True).update(pharmacy=pharmacy)


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_pharmacy_user_pharmacy'),
        ('medicines', '0002_remove_medicine_unique_medicine_formulation_and_more'),
        ('dispensing', '0007_dispensingtransaction_pharmacy'),
        ('clinical', '0006_remove_allergyrule_unique_versioned_medicine_allergen_rule_and_more'),
    ]

    operations = [migrations.RunPython(assign_default_pharmacy, migrations.RunPython.noop)]
