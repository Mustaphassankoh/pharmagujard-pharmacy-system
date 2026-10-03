"""Milestone 13 cross-cutting system evaluation tests.

These tests supplement the feature-level suites with acceptance, integrity,
query-efficiency, and repeatable development-scale timing evidence.
"""
import json
import time
from datetime import date, timedelta
from statistics import mean

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from clinical.models import ClinicalAlert, ClinicalCheckResult, ClinicalReview
from dispensing.models import (
    DispensingItem, DispensingTransaction, TransactionStatusChoices,
    TransactionTypeChoices,
)
from inventory.models import MedicineBatch, StockTransaction
from medicines.models import Medicine, MedicineCategory

User = get_user_model()


class AuthenticationAndAccessEvaluationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='evaluation-admin', password='pw', role='ADMIN')
        cls.staff = User.objects.create_user(username='evaluation-staff', password='pw', role='PHARMACY_STAFF')

    def test_login_logout_and_unauthenticated_protection(self):
        login = self.client.post(reverse('login'), {'username': self.staff.username, 'password': 'pw'})
        self.assertRedirects(login, reverse('dashboard'))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        logout = self.client.post(reverse('logout'))
        self.assertRedirects(logout, reverse('login'))
        protected = self.client.get(reverse('inventory:inventory_list'))
        self.assertRedirects(protected, f"{reverse('login')}?next={reverse('inventory:inventory_list')}")

    def test_admin_and_staff_access_matrix(self):
        shared = [
            reverse('dashboard'), reverse('medicines:medicine_list'),
            reverse('inventory:inventory_list'), reverse('dispensing:transaction_list'),
        ]
        admin_only = [
            reverse('medicines:medicine_create'), reverse('inventory:batch_create'),
            reverse('inventory:transaction_list'), reverse('clinical:governance_dashboard'),
            reverse('clinical:rule_report'), reverse('clinical:export_rules_csv'),
        ]

        self.client.force_login(self.admin)
        for url in shared + admin_only:
            with self.subTest(role='ADMIN', url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.staff)
        for url in shared:
            with self.subTest(role='PHARMACY_STAFF', url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        for url in admin_only:
            with self.subTest(role='PHARMACY_STAFF', url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_django_admin_requires_staff_privilege(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)

        self.admin.role = 'PHARMACY_STAFF'
        self.admin.save(update_fields=['role'])
        self.admin.refresh_from_db()
        self.assertFalse(self.admin.is_staff)


class TransactionIntegrityEvaluationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='integrity-staff', password='pw', role='PHARMACY_STAFF')
        category = MedicineCategory.objects.create(name='Evaluation Medicines')
        self.medicine = Medicine.objects.create(
            category=category, generic_name='Synthetic Evaluation Medicine',
            strength='10 mg', dosage_form='TABLET', unit='tablet',
        )
        self.batch = MedicineBatch.objects.create(
            medicine=self.medicine, batch_number='EVAL-BATCH', quantity_received=20,
            quantity_remaining=20, cost_price='3.00', selling_price='7.50',
            date_received=date.today(), expiry_date=date.today() + timedelta(days=90),
        )
        self.client.force_login(self.user)

    def test_repeated_confirmation_does_not_double_deduct(self):
        transaction = DispensingTransaction.objects.create(
            user=self.user, transaction_type=TransactionTypeChoices.DIRECT_SALE,
            status=TransactionStatusChoices.DRAFT,
        )
        session = self.client.session
        session[f'cart_{transaction.pk}'] = {
            str(self.medicine.pk): {
                'medicine_id': self.medicine.pk,
                'medicine_name': str(self.medicine),
                'quantity': 3,
            }
        }
        session.save()

        first = self.client.post(reverse('dispensing:confirm_sale', args=[transaction.pk]))
        self.assertEqual(first.status_code, 302)
        transaction.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(transaction.status, TransactionStatusChoices.COMPLETED)
        self.assertEqual(transaction.total_amount, 22.50)
        self.assertEqual(self.batch.quantity_remaining, 17)
        self.assertEqual(DispensingItem.objects.filter(transaction=transaction).count(), 1)
        self.assertEqual(StockTransaction.objects.filter(reference_number=transaction.transaction_number).count(), 1)

        second = self.client.post(reverse('dispensing:confirm_sale', args=[transaction.pk]))
        self.assertEqual(second.status_code, 404)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining, 17)
        self.assertEqual(DispensingItem.objects.filter(transaction=transaction).count(), 1)
        self.assertEqual(StockTransaction.objects.filter(reference_number=transaction.transaction_number).count(), 1)

    def test_invalid_identifiers_and_missing_stock_fail_without_partial_state(self):
        self.assertEqual(self.client.get(reverse('inventory:batch_detail', args=[999999])).status_code, 404)
        self.assertEqual(self.client.get(reverse('dispensing:transaction_detail', args=[999999])).status_code, 404)

        transaction = DispensingTransaction.objects.create(user=self.user)
        session = self.client.session
        session[f'cart_{transaction.pk}'] = {
            str(self.medicine.pk): {
                'medicine_id': self.medicine.pk,
                'medicine_name': str(self.medicine),
                'quantity': 21,
            }
        }
        session.save()
        response = self.client.post(reverse('dispensing:confirm_sale', args=[transaction.pk]))
        self.assertEqual(response.status_code, 302)
        transaction.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(transaction.status, TransactionStatusChoices.DRAFT)
        self.assertEqual(self.batch.quantity_remaining, 20)
        self.assertFalse(DispensingItem.objects.filter(transaction=transaction).exists())


class DataIntegrityEvaluationTests(TestCase):
    def test_relationships_have_no_orphans_and_quantities_are_non_negative(self):
        self.assertFalse(Medicine.objects.filter(category__isnull=True).exists())
        self.assertFalse(MedicineBatch.objects.filter(medicine__isnull=True).exists())
        self.assertFalse(StockTransaction.objects.filter(batch__isnull=True).exists())
        self.assertFalse(DispensingItem.objects.filter(transaction__isnull=True).exists())
        self.assertFalse(DispensingItem.objects.filter(medicine__isnull=True).exists())
        self.assertFalse(DispensingItem.objects.filter(batch__isnull=True).exists())
        self.assertFalse(ClinicalReview.objects.filter(transaction__isnull=True).exists())
        self.assertFalse(ClinicalCheckResult.objects.filter(transaction__isnull=True).exists())
        self.assertFalse(ClinicalAlert.objects.filter(transaction__isnull=True).exists())
        self.assertFalse(MedicineBatch.objects.filter(quantity_remaining__lt=0).exists())


class QueryEfficiencyEvaluationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='query-admin', password='pw', role='ADMIN')
        category = MedicineCategory.objects.create(name='Query Evaluation')
        medicines = [
            Medicine(category=category, generic_name=f'Query Medicine {index:02}', strength='1 mg', dosage_form='TABLET')
            for index in range(30)
        ]
        Medicine.objects.bulk_create(medicines)
        MedicineBatch.objects.bulk_create([
            MedicineBatch(
                medicine=medicine, batch_number=f'QUERY-{medicine.pk}', quantity_received=10,
                quantity_remaining=10, cost_price='1.00', selling_price='2.00',
                date_received=date.today(), expiry_date=date.today() + timedelta(days=90),
            )
            for medicine in Medicine.objects.filter(category=category)
        ])
        for _ in range(30):
            DispensingTransaction.objects.create(
                user=cls.admin, transaction_type=TransactionTypeChoices.DIRECT_SALE,
            )

    def setUp(self):
        self.client.force_login(self.admin)

    def _assert_query_budget(self, url, maximum):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), maximum, f'{url} used {len(queries)} queries')
        return len(queries)

    def test_representative_pages_stay_within_development_query_budgets(self):
        results = {
            'inventory_list': self._assert_query_budget(reverse('inventory:inventory_list'), 10),
            'transaction_list': self._assert_query_budget(reverse('dispensing:transaction_list'), 8),
            'governance_dashboard': self._assert_query_budget(reverse('clinical:governance_dashboard'), 12),
            'rule_report': self._assert_query_budget(reverse('clinical:rule_report'), 12),
        }
        print('M13_QUERY_COUNTS=' + json.dumps(results, sort_keys=True))


class PerformanceEvaluationTests(TestCase):
    """Print measured development-scale timings for the evaluation report."""
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='performance-admin', password='pw', role='ADMIN')
        cls.staff = User.objects.create_user(username='performance-staff', password='pw', role='PHARMACY_STAFF')
        category = MedicineCategory.objects.create(name='Performance Evaluation')
        medicines = [
            Medicine(category=category, generic_name=f'Performance Medicine {index:02}', strength='1 mg', dosage_form='TABLET')
            for index in range(30)
        ]
        Medicine.objects.bulk_create(medicines)
        MedicineBatch.objects.bulk_create([
            MedicineBatch(
                medicine=medicine, batch_number=f'PERF-{medicine.pk}', quantity_received=20,
                quantity_remaining=20, cost_price='1.00', selling_price='2.00',
                date_received=date.today(), expiry_date=date.today() + timedelta(days=120),
            )
            for medicine in Medicine.objects.filter(category=category)
        ])

    def _measure(self, callback, runs=5):
        durations = []
        for _ in range(runs):
            started = time.perf_counter()
            response = callback()
            durations.append((time.perf_counter() - started) * 1000)
            self.assertLess(response.status_code, 500)
        return {'runs': runs, 'average_ms': round(mean(durations), 2), 'slowest_ms': round(max(durations), 2)}

    def test_development_scale_response_times(self):
        results = {}
        results['login'] = self._measure(lambda: self.client.post(reverse('login'), {
            'username': self.staff.username, 'password': 'pw',
        }))
        self.client.force_login(self.admin)
        endpoints = {
            'dashboard': reverse('dashboard'),
            'medicine_list': reverse('medicines:medicine_list'),
            'inventory_list': reverse('inventory:inventory_list'),
            'governance_dashboard': reverse('clinical:governance_dashboard'),
            'rule_report': reverse('clinical:rule_report'),
            'csv_export': reverse('clinical:export_rules_csv'),
        }
        for label, url in endpoints.items():
            results[label] = self._measure(lambda url=url: self.client.get(url))
        results['transaction_creation'] = self._measure(
            lambda: self.client.get(reverse('dispensing:new_direct_sale'))
        )
        medicine = Medicine.objects.filter(category__name='Performance Evaluation').first()
        transaction = DispensingTransaction.objects.create(
            user=self.admin, transaction_type=TransactionTypeChoices.DIRECT_SALE,
        )
        session = self.client.session
        session[f'cart_{transaction.pk}'] = {
            str(medicine.pk): {
                'medicine_id': medicine.pk, 'medicine_name': str(medicine), 'quantity': 1,
            }
        }
        session.save()
        results['clinical_review'] = self._measure(
            lambda: self.client.post(reverse('dispensing:run_clinical_review', args=[transaction.pk]))
        )
        print('M13_PERFORMANCE_JSON=' + json.dumps(results, sort_keys=True))
