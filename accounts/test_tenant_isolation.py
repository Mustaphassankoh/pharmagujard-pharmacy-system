from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from clinical.governance import record_rule_audit
from clinical.models import Allergen, DrugInteractionRule
from dispensing.models import Consultation, DispensingTransaction, TransactionStatusChoices, TransactionTypeChoices
from inventory.models import MedicineBatch, StockTransaction, TransactionTypeChoices as StockType
from medicines.models import Medicine, MedicineCategory

from .models import Pharmacy

User = get_user_model()


class TenantIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pharmacy_a = Pharmacy.objects.create(name='Isolation Pharmacy A')
        cls.pharmacy_b = Pharmacy.objects.create(name='Isolation Pharmacy B')
        cls.admin_a = User.objects.create_user(username='isolation-admin-a', password='pw', full_name='Admin A', role='ADMIN', pharmacy=cls.pharmacy_a)
        cls.staff_a = User.objects.create_user(username='isolation-staff-a', password='pw', full_name='Staff A', pharmacy=cls.pharmacy_a)
        cls.admin_b = User.objects.create_user(username='isolation-admin-b', password='pw', full_name='Admin B', role='ADMIN', pharmacy=cls.pharmacy_b)
        cls.staff_b = User.objects.create_user(username='isolation-staff-b', password='pw', full_name='Staff B', pharmacy=cls.pharmacy_b)
        cls.superuser = User.objects.create_superuser(username='isolation-root', password='pw', full_name='Root')

        cls.category_a = MedicineCategory.objects.create(pharmacy=cls.pharmacy_a, name='Tenant A Category')
        cls.category_b = MedicineCategory.objects.create(pharmacy=cls.pharmacy_b, name='Tenant B Category')
        cls.medicine_a1 = Medicine.objects.create(pharmacy=cls.pharmacy_a, category=cls.category_a, generic_name='Tenant A Medicine One', strength='10mg', dosage_form='TABLET', unit='tablet')
        cls.medicine_a2 = Medicine.objects.create(pharmacy=cls.pharmacy_a, category=cls.category_a, generic_name='Tenant A Medicine Two', strength='20mg', dosage_form='TABLET', unit='tablet')
        cls.medicine_b1 = Medicine.objects.create(pharmacy=cls.pharmacy_b, category=cls.category_b, generic_name='Tenant B Medicine One', strength='10mg', dosage_form='TABLET', unit='tablet')
        cls.medicine_b2 = Medicine.objects.create(pharmacy=cls.pharmacy_b, category=cls.category_b, generic_name='Tenant B Medicine Two', strength='20mg', dosage_form='TABLET', unit='tablet')

        batch_values = dict(quantity_received=20, quantity_remaining=20, cost_price='1.00', selling_price='2.00', date_received=date.today(), expiry_date=date.today() + timedelta(days=90))
        cls.batch_a = MedicineBatch.objects.create(medicine=cls.medicine_a1, batch_number='TENANT-A-BATCH', **batch_values)
        cls.batch_b = MedicineBatch.objects.create(medicine=cls.medicine_b1, batch_number='TENANT-B-BATCH', **batch_values)
        cls.stock_a = StockTransaction.objects.create(batch=cls.batch_a, user=cls.admin_a, transaction_type=StockType.STOCK_IN, quantity=20, previous_quantity=0, new_quantity=20)
        cls.stock_b = StockTransaction.objects.create(batch=cls.batch_b, user=cls.admin_b, transaction_type=StockType.STOCK_IN, quantity=20, previous_quantity=0, new_quantity=20)

        cls.transaction_a = DispensingTransaction.objects.create(user=cls.staff_a, transaction_type=TransactionTypeChoices.CONSULTATION, status=TransactionStatusChoices.DRAFT)
        cls.transaction_b = DispensingTransaction.objects.create(user=cls.staff_b, transaction_type=TransactionTypeChoices.CONSULTATION, status=TransactionStatusChoices.DRAFT)
        Consultation.objects.create(transaction=cls.transaction_a, symptoms='Tenant A consultation')
        Consultation.objects.create(transaction=cls.transaction_b, symptoms='Tenant B consultation')

        cls.allergen_a = Allergen.objects.create(pharmacy=cls.pharmacy_a, name='Tenant A Allergen')
        cls.allergen_b = Allergen.objects.create(pharmacy=cls.pharmacy_b, name='Tenant B Allergen')
        cls.rule_a = DrugInteractionRule.objects.create(pharmacy=cls.pharmacy_a, medicine_a=cls.medicine_a1, medicine_b=cls.medicine_a2, severity='HIGH', description='Tenant A Rule', explanation='A', recommendation='A', source_reference='A-SOURCE', created_by=cls.admin_a)
        cls.rule_b = DrugInteractionRule.objects.create(pharmacy=cls.pharmacy_b, medicine_a=cls.medicine_b1, medicine_b=cls.medicine_b2, severity='HIGH', description='Tenant B Rule', explanation='B', recommendation='B', source_reference='B-SOURCE', created_by=cls.admin_b)
        cls.audit_a = record_rule_audit(cls.rule_a, 'CREATED', cls.admin_a)
        cls.audit_b = record_rule_audit(cls.rule_b, 'CREATED', cls.admin_b)

    def login(self, user):
        self.client.force_login(user)

    def test_medicine_list_detail_and_staff_isolation(self):
        for user in (self.admin_a, self.staff_a):
            with self.subTest(user=user.username):
                self.login(user)
                response = self.client.get(reverse('medicines:medicine_list'))
                self.assertContains(response, self.medicine_a1.generic_name)
                self.assertNotContains(response, self.medicine_b1.generic_name)
                self.assertEqual(self.client.get(reverse('medicines:medicine_detail', args=[self.medicine_b1.pk])).status_code, 404)

    def test_inventory_batch_and_stock_transaction_isolation(self):
        self.login(self.admin_a)
        inventory = self.client.get(reverse('inventory:inventory_list'))
        self.assertContains(inventory, self.medicine_a1.generic_name)
        self.assertNotContains(inventory, self.medicine_b1.generic_name)
        batches = self.client.get(reverse('inventory:batch_list'))
        self.assertContains(batches, self.batch_a.batch_number)
        self.assertNotContains(batches, self.batch_b.batch_number)
        self.assertEqual(self.client.get(reverse('inventory:batch_detail', args=[self.batch_b.pk])).status_code, 404)
        stock = self.client.get(reverse('inventory:transaction_list'))
        self.assertContains(stock, self.batch_a.batch_number)
        self.assertNotContains(stock, self.batch_b.batch_number)

    def test_transaction_lists_details_and_consultation_urls_are_isolated(self):
        self.login(self.admin_a)
        response = self.client.get(reverse('dispensing:transaction_list'))
        self.assertContains(response, self.transaction_a.transaction_number)
        self.assertNotContains(response, self.transaction_b.transaction_number)
        self.assertEqual(self.client.get(reverse('dispensing:transaction_detail', args=[self.transaction_b.pk])).status_code, 404)
        self.login(self.staff_a)
        self.assertEqual(self.client.get(reverse('dispensing:consultation_cart', args=[self.transaction_b.pk])).status_code, 404)

    def test_governance_reports_audits_and_csv_are_isolated(self):
        self.login(self.admin_a)
        for url_name in ('clinical:governance_dashboard', 'clinical:rule_report'):
            response = self.client.get(reverse(url_name))
            self.assertContains(response, self.medicine_a1.generic_name)
            self.assertNotContains(response, self.medicine_b1.generic_name)
        self.assertEqual(self.client.get(reverse('clinical:rule_history', args=['interaction', self.rule_b.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('clinical:audit_detail', args=[self.audit_b.pk])).status_code, 404)
        rules_csv = self.client.get(reverse('clinical:export_rules_csv')).content.decode()
        audits_csv = self.client.get(reverse('clinical:export_audits_csv')).content.decode()
        self.assertIn('Tenant A Medicine One', rules_csv)
        self.assertNotIn('Tenant B Medicine One', rules_csv)
        self.assertIn(str(self.audit_a.pk), audits_csv)
        self.assertNotIn(f'\r\n{self.audit_b.pk},', audits_csv)

    def test_form_dropdowns_are_isolated(self):
        self.login(self.admin_a)
        medicine_form = self.client.get(reverse('medicines:medicine_create'))
        self.assertContains(medicine_form, self.category_a.name)
        self.assertNotContains(medicine_form, self.category_b.name)
        batch_form = self.client.get(reverse('inventory:batch_create'))
        self.assertContains(batch_form, self.medicine_a1.generic_name)
        self.assertNotContains(batch_form, self.medicine_b1.generic_name)
        self.login(self.staff_a)
        consultation = self.client.get(reverse('dispensing:consultation_cart', args=[self.transaction_a.pk]))
        self.assertContains(consultation, self.allergen_a.name)
        self.assertNotContains(consultation, self.allergen_b.name)

    def test_cross_tenant_relationships_and_cart_submission_are_rejected(self):
        with self.assertRaises(ValidationError):
            DrugInteractionRule.objects.create(pharmacy=self.pharmacy_a, medicine_a=self.medicine_a1, medicine_b=self.medicine_b1, severity='HIGH', description='Invalid', explanation='Invalid', recommendation='Invalid', source_reference='INVALID')
        self.login(self.staff_a)
        response = self.client.post(reverse('dispensing:add_to_cart', args=[self.transaction_a.pk]), {'medicine_id': self.medicine_b1.pk, 'quantity': 1})
        self.assertRedirects(response, reverse('dispensing:consultation_cart', args=[self.transaction_a.pk]))
        self.assertNotIn(str(self.medicine_b1.pk), self.client.session.get(f'cart_{self.transaction_a.pk}', {}))

    def test_pharmacy_b_cannot_see_pharmacy_a(self):
        self.login(self.admin_b)
        medicines = self.client.get(reverse('medicines:medicine_list'))
        self.assertContains(medicines, self.medicine_b1.generic_name)
        self.assertNotContains(medicines, self.medicine_a1.generic_name)
        self.assertEqual(self.client.get(reverse('inventory:batch_detail', args=[self.batch_a.pk])).status_code, 404)

    def test_superuser_retains_cross_tenant_visibility(self):
        self.login(self.superuser)
        medicines = self.client.get(reverse('medicines:medicine_list'))
        self.assertContains(medicines, self.medicine_a1.generic_name)
        self.assertContains(medicines, self.medicine_b1.generic_name)
        governance = self.client.get(reverse('clinical:rule_report'))
        self.assertContains(governance, self.medicine_a1.generic_name)
        self.assertContains(governance, self.medicine_b1.generic_name)
