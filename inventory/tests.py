from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from datetime import date
from decimal import Decimal
from django.utils import timezone

from medicines.models import Medicine, MedicineCategory
from .models import MedicineBatch, StockTransaction, TransactionTypeChoices
from .services import create_medicine_batch, adjust_batch_stock
from pharmacy_system.currency import format_currency

User = get_user_model()


class CurrencyFormattingTests(TestCase):
    def test_currency_formatter_uses_sle_and_two_decimal_places(self):
        self.assertEqual(format_currency(0), 'SLE 0.00')
        self.assertEqual(format_currency(Decimal('25')), 'SLE 25.00')
        self.assertEqual(format_currency(Decimal('1250.5')), 'SLE 1,250.50')

    def test_formatter_does_not_change_decimal_value(self):
        amount = Decimal('12.345')
        format_currency(amount)
        self.assertEqual(amount, Decimal('12.345'))


class InventoryModelTests(TestCase):
    def setUp(self):
        self.category = MedicineCategory.objects.create(name="Painkillers")
        self.medicine = Medicine.objects.create(
            category=self.category,
            generic_name="Paracetamol",
            strength="500mg",
            dosage_form="TABLET",
            minimum_stock_level=100
        )
        self.user = User.objects.create_user(username="admin", password="pw", role="ADMIN")

    def test_create_batch_and_transaction(self):
        batch_data = {
            'medicine': self.medicine,
            'batch_number': 'B001',
            'quantity_received': 200,
            'cost_price': 5.00,
            'selling_price': 10.00,
            'date_received': date.today(),
            'expiry_date': date.today() + timezone.timedelta(days=365)
        }
        
        batch = create_medicine_batch(batch_data, self.user)
        
        self.assertEqual(batch.quantity_remaining, 200)
        self.assertEqual(batch.transactions.count(), 1)
        
        txn = batch.transactions.first()
        self.assertEqual(txn.transaction_type, TransactionTypeChoices.STOCK_IN)
        self.assertEqual(txn.quantity, 200)
        self.assertEqual(txn.new_quantity, 200)
        self.assertEqual(txn.user, self.user)

    def test_stock_aggregation(self):
        # Create active valid batch
        create_medicine_batch({
            'medicine': self.medicine,
            'batch_number': 'B001',
            'quantity_received': 50,
            'cost_price': 5,
            'selling_price': 10,
            'expiry_date': date.today() + timezone.timedelta(days=100)
        }, self.user)
        
        # Create expired batch
        batch2 = create_medicine_batch({
            'medicine': self.medicine,
            'batch_number': 'B002',
            'quantity_received': 50,
            'cost_price': 5,
            'selling_price': 10,
            'expiry_date': date.today() + timezone.timedelta(days=100)
        }, self.user)
        # Manually force expiration
        batch2.expiry_date = date.today() - timezone.timedelta(days=10)
        batch2.save()

        # Create inactive batch
        batch3 = create_medicine_batch({
            'medicine': self.medicine,
            'batch_number': 'B003',
            'quantity_received': 50,
            'cost_price': 5,
            'selling_price': 10,
            'expiry_date': date.today() + timezone.timedelta(days=100)
        }, self.user)
        batch3.is_active = False
        batch3.save()

        self.medicine.refresh_from_db()
        # Only B001 should count
        self.assertEqual(self.medicine.total_available_stock, 50)
        self.assertEqual(self.medicine.stock_status, "Low Stock") # min_stock is 100

    def test_adjust_stock_increase(self):
        batch = create_medicine_batch({
            'medicine': self.medicine,
            'batch_number': 'B001',
            'quantity_received': 100,
            'cost_price': 5,
            'selling_price': 10,
            'expiry_date': date.today() + timezone.timedelta(days=100)
        }, self.user)
        
        adjust_batch_stock(batch, self.user, 'INCREASE', 20, "Correction")
        
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining, 120)
        
        txn = batch.transactions.order_by('-created_at').first()
        self.assertEqual(txn.transaction_type, TransactionTypeChoices.ADJUSTMENT_INCREASE)
        self.assertEqual(txn.previous_quantity, 100)
        self.assertEqual(txn.new_quantity, 120)

    def test_adjust_stock_decrease(self):
        batch = create_medicine_batch({
            'medicine': self.medicine,
            'batch_number': 'B001',
            'quantity_received': 100,
            'cost_price': 5,
            'selling_price': 10,
            'expiry_date': date.today() + timezone.timedelta(days=100)
        }, self.user)
        
        adjust_batch_stock(batch, self.user, 'DECREASE', 30, "Damaged")
        
        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining, 70)
        
    def test_negative_decrease_fails(self):
        batch = create_medicine_batch({
            'medicine': self.medicine,
            'batch_number': 'B001',
            'quantity_received': 10,
            'cost_price': 5,
            'selling_price': 10,
            'expiry_date': date.today() + timezone.timedelta(days=100)
        }, self.user)
        
        with self.assertRaises(ValidationError):
            adjust_batch_stock(batch, self.user, 'DECREASE', 15)

    def test_validation_rules(self):
        # Expiry before received date
        batch = MedicineBatch(
            medicine=self.medicine,
            batch_number="TEST",
            quantity_received=10,
            quantity_remaining=10,
            cost_price=5,
            selling_price=10,
            date_received=date.today(),
            expiry_date=date.today() - timezone.timedelta(days=1)
        )
        with self.assertRaises(ValidationError):
            batch.clean()


class InventoryViewTests(TestCase):
    def setUp(self):
        self.category = MedicineCategory.objects.create(name="Painkillers")
        self.medicine = Medicine.objects.create(
            category=self.category,
            generic_name="Paracetamol",
            strength="500mg",
            dosage_form="TABLET",
            minimum_stock_level=100
        )
        self.admin = User.objects.create_user(username="admin", password="pw", role="ADMIN")
        self.staff = User.objects.create_user(username="staff", password="pw", role="PHARMACY_STAFF")

    def test_staff_permissions(self):
        self.client.login(username="staff", password="pw")
        
        # Staff can view inventory list
        response = self.client.get(reverse('inventory:inventory_list'))
        self.assertEqual(response.status_code, 200)
        
        # Staff CANNOT add batches
        response = self.client.get(reverse('inventory:batch_create'))
        self.assertEqual(response.status_code, 403)
        
    def test_admin_permissions(self):
        self.client.login(username="admin", password="pw")
        
        # Admin CAN add batches
        response = self.client.get(reverse('inventory:batch_create'))
        self.assertEqual(response.status_code, 200)

    def test_batch_prices_display_in_sle(self):
        batch = MedicineBatch.objects.create(
            medicine=self.medicine, batch_number='SLE-DISPLAY',
            quantity_received=10, quantity_remaining=10,
            cost_price=Decimal('1250.50'), selling_price=Decimal('1500.00'),
            date_received=date.today(),
            expiry_date=date.today() + timezone.timedelta(days=365),
        )
        self.client.login(username='staff', password='pw')
        list_response = self.client.get(reverse('inventory:batch_list'))
        detail_response = self.client.get(reverse('inventory:batch_detail', args=[batch.pk]))
        self.assertContains(list_response, 'SLE 1,250.50')
        self.assertContains(list_response, 'SLE 1,500.00')
        self.assertContains(detail_response, 'SLE 1,250.50')
        self.assertContains(detail_response, 'SLE 1,500.00')

    def test_admin_can_create_valid_batch(self):
        self.client.login(username="admin", password="pw")
        post_data = {
            'medicine': self.medicine.id,
            'batch_number': 'NEWBATCH123',
            'quantity_received': 500,
            'cost_price': '10.00',
            'selling_price': '15.00',
            'date_received': date.today(),
            'expiry_date': date.today() + timezone.timedelta(days=365)
        }
        
        response = self.client.post(reverse('inventory:batch_create'), data=post_data)
        
        batch = MedicineBatch.objects.filter(batch_number='NEWBATCH123').first()
        self.assertIsNotNone(batch)
        self.assertEqual(batch.quantity_remaining, 500)
        
        txn = StockTransaction.objects.filter(batch=batch).first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.transaction_type, TransactionTypeChoices.STOCK_IN)
        
        # Should redirect to batch detail
        self.assertRedirects(response, reverse('inventory:batch_detail', args=[batch.pk]))

    def test_invalid_form_returns_validation_errors(self):
        self.client.login(username="admin", password="pw")
        post_data = {
            'medicine': self.medicine.id,
            'batch_number': '', # missing batch number
            'quantity_received': -10, # invalid quantity
        }
        
        response = self.client.post(reverse('inventory:batch_create'), data=post_data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'batch_number', 'This field is required.')
        self.assertFormError(response.context['form'], 'quantity_received', 'Ensure this value is greater than or equal to 0.')
        
    def test_invalid_expiry_date_produces_error(self):
        self.client.login(username="admin", password="pw")
        post_data = {
            'medicine': self.medicine.id,
            'batch_number': 'BADEXPIRY',
            'quantity_received': 500,
            'cost_price': '10.00',
            'selling_price': '15.00',
            'date_received': date.today(),
            'expiry_date': date.today() - timezone.timedelta(days=10) # expired
        }
        
        response = self.client.post(reverse('inventory:batch_create'), data=post_data)
        self.assertEqual(response.status_code, 200)
        # We test that the form or non_field_errors contains the validation error
        # Since MedicineBatch.clean() raises ValidationError without a specific field sometimes, or __all__
        self.assertTrue(response.context['form'].errors)

    def test_duplicate_batch_produces_error(self):
        # Create an existing batch
        MedicineBatch.objects.create(
            medicine=self.medicine,
            batch_number='DUPBATCH',
            quantity_received=100,
            quantity_remaining=100,
            cost_price=5,
            selling_price=10,
            date_received=date.today(),
            expiry_date=date.today() + timezone.timedelta(days=100)
        )
        
        self.client.login(username="admin", password="pw")
        post_data = {
            'medicine': self.medicine.id,
            'batch_number': 'DUPBATCH',
            'quantity_received': 500,
            'cost_price': '10.00',
            'selling_price': '15.00',
            'date_received': date.today(),
            'expiry_date': date.today() + timezone.timedelta(days=365)
        }
        
        response = self.client.post(reverse('inventory:batch_create'), data=post_data)
        self.assertEqual(response.status_code, 200)
        # Error should be on batch_number or non_field_errors due to unique_together constraints
        self.assertTrue(response.context['form'].errors)
