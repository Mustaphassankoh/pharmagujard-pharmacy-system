"""
Milestone 4 & Milestone 5 — Dispensing tests.
Covers:
  - Generic transaction number prefix (TX-YYYY-NNNNNN)
  - Generic confirm_transaction service
  - Direct Sale workflow
  - External Prescription workflow
  - Prescriber & Patient metadata update-or-create behavior (1 ExternalPrescription per DispensingTransaction)
  - Dosage instructions per item
  - FEFO stock deduction and atomic rollback
  - Draft and Cancelled transactions do NOT alter stock
  - View permissions and templates
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import MedicineBatch, StockTransaction, TransactionTypeChoices
from medicines.models import Medicine, MedicineCategory

from .forms import ConsultationForm, ExternalPrescriptionForm, PrescriptionItemForm
from .models import (
    DispensingItem,
    DispensingTransaction,
    ExternalPrescription,
    TransactionStatusChoices,
    TransactionTypeChoices as DispensingTypeChoices,
)
from .services import check_stock_availability, confirm_transaction, get_valid_batches_fefo

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_category():
    return MedicineCategory.objects.create(name="Test Category")


def make_medicine(category, name="Paracetamol", active=True):
    return Medicine.objects.create(
        category=category,
        generic_name=name,
        strength="500mg",
        dosage_form="TABLET",
        unit="tablet",
        minimum_stock_level=10,
        is_active=active,
    )


def make_batch(medicine, qty, expiry_delta_days=365, active=True, selling_price="10.00"):
    batch = MedicineBatch(
        medicine=medicine,
        batch_number=f"B-{medicine.pk}-{qty}-{expiry_delta_days}",
        quantity_received=qty,
        quantity_remaining=qty,
        cost_price="5.00",
        selling_price=selling_price,
        date_received=date.today(),
        expiry_date=date.today() + timedelta(days=expiry_delta_days),
        is_active=active,
    )
    batch.save()
    return batch


def make_draft_txn(user, transaction_type=DispensingTypeChoices.DIRECT_SALE):
    return DispensingTransaction.objects.create(
        user=user,
        transaction_type=transaction_type,
        status=TransactionStatusChoices.DRAFT,
    )


def build_cart(medicine, quantity, dose="", frequency="", duration="", instructions=""):
    return {
        str(medicine.pk): {
            'medicine_id': medicine.pk,
            'medicine_name': str(medicine),
            'quantity': quantity,
            'dose': dose,
            'frequency': frequency,
            'duration': duration,
            'instructions': instructions,
        }
    }


class CurrencyDisplayTests(TestCase):
    def setUp(self):
        self.category = make_category()
        self.medicine = make_medicine(self.category)
        make_batch(self.medicine, qty=20, selling_price='25.00')
        self.user = User.objects.create_user(username='currency-staff', password='pw', role='PHARMACIST')
        self.client.login(username='currency-staff', password='pw')

    def _assert_cart_currency(self, transaction_type, url_name):
        txn = make_draft_txn(self.user, transaction_type)
        session = self.client.session
        session[f'cart_{txn.pk}'] = build_cart(self.medicine, 2)
        session.save()
        response = self.client.get(reverse(url_name, args=[txn.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SLE 50.00')
        self.assertNotContains(response, 'GHS')

    def test_direct_sale_displays_sle_total(self):
        self._assert_cart_currency(DispensingTypeChoices.DIRECT_SALE, 'dispensing:sale_cart')

    def test_external_prescription_displays_sle_total(self):
        self._assert_cart_currency(DispensingTypeChoices.EXTERNAL_PRESCRIPTION, 'dispensing:external_prescription_cart')

    def test_consultation_displays_sle_total(self):
        self._assert_cart_currency(DispensingTypeChoices.CONSULTATION, 'dispensing:consultation_cart')


# ---------------------------------------------------------------------------
# Test: Generic Transaction Number Generation
# ---------------------------------------------------------------------------

class TransactionNumberTest(TestCase):
    def setUp(self):
        self.category = make_category()
        self.user = User.objects.create_user(username="admin", password="pw", role="ADMIN")

    def test_transaction_number_generated_from_pk_with_tx_prefix(self):
        txn = make_draft_txn(self.user, DispensingTypeChoices.DIRECT_SALE)
        txn.refresh_from_db()
        expected = f"TX-{txn.created_at.year}-{txn.pk:06d}"
        self.assertEqual(txn.transaction_number, expected)

    def test_external_prescription_uses_generic_tx_prefix(self):
        txn = make_draft_txn(self.user, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)
        txn.refresh_from_db()
        expected = f"TX-{txn.created_at.year}-{txn.pk:06d}"
        self.assertEqual(txn.transaction_number, expected)

    def test_transaction_numbers_unique(self):
        txn1 = make_draft_txn(self.user)
        txn2 = make_draft_txn(self.user)
        txn1.refresh_from_db()
        txn2.refresh_from_db()
        self.assertNotEqual(txn1.transaction_number, txn2.transaction_number)


# ---------------------------------------------------------------------------
# Test: FEFO & Stock Checks
# ---------------------------------------------------------------------------

class FefoServiceTest(TestCase):
    def setUp(self):
        self.category = make_category()
        self.medicine = make_medicine(self.category)
        self.user = User.objects.create_user(username="admin", password="pw", role="ADMIN")

    def test_fefo_order(self):
        """Batches returned in expiry_date ASC order."""
        earlier = make_batch(self.medicine, qty=10, expiry_delta_days=30)
        later = make_batch(self.medicine, qty=20, expiry_delta_days=200)
        batches = list(get_valid_batches_fefo(self.medicine))
        self.assertEqual(batches[0].pk, earlier.pk)
        self.assertEqual(batches[1].pk, later.pk)

    def test_expired_batch_excluded(self):
        """Expired batches are not included in FEFO."""
        make_batch(self.medicine, qty=50, expiry_delta_days=-1)
        self.assertEqual(get_valid_batches_fefo(self.medicine).count(), 0)

    def test_inactive_batch_excluded(self):
        """Inactive batches are excluded."""
        make_batch(self.medicine, qty=50, expiry_delta_days=100, active=False)
        self.assertEqual(get_valid_batches_fefo(self.medicine).count(), 0)

    def test_zero_stock_batch_excluded(self):
        """Out-of-stock batches are excluded."""
        batch = make_batch(self.medicine, qty=50, expiry_delta_days=100)
        batch.quantity_remaining = 0
        batch.save()
        self.assertEqual(get_valid_batches_fefo(self.medicine).count(), 0)

    def test_insufficient_stock_raises(self):
        """check_stock_availability raises when stock < requested."""
        make_batch(self.medicine, qty=5, expiry_delta_days=100)
        with self.assertRaises(ValidationError):
            check_stock_availability(self.medicine, 10)

    def test_quantity_zero_raises(self):
        """Quantity 0 is invalid."""
        make_batch(self.medicine, qty=50, expiry_delta_days=100)
        with self.assertRaises(ValidationError):
            check_stock_availability(self.medicine, 0)

    def test_single_batch_allocation(self):
        """Full quantity taken from one batch."""
        batch = make_batch(self.medicine, qty=50, expiry_delta_days=100)
        allocation = check_stock_availability(self.medicine, 20)
        self.assertEqual(len(allocation), 1)
        self.assertEqual(allocation[0][0].pk, batch.pk)
        self.assertEqual(allocation[0][1], 20)

    def test_multi_batch_fefo_allocation(self):
        """10 (earlier) + 20 (later), request 15 → 10 from A, 5 from B."""
        batch_a = make_batch(self.medicine, qty=10, expiry_delta_days=30)
        batch_b = make_batch(self.medicine, qty=20, expiry_delta_days=200)
        allocation = check_stock_availability(self.medicine, 15)
        self.assertEqual(len(allocation), 2)
        self.assertEqual(allocation[0][0].pk, batch_a.pk)
        self.assertEqual(allocation[0][1], 10)
        self.assertEqual(allocation[1][0].pk, batch_b.pk)
        self.assertEqual(allocation[1][1], 5)


# ---------------------------------------------------------------------------
# Test: Generic Confirm Transaction Service
# ---------------------------------------------------------------------------

class ConfirmTransactionTest(TestCase):
    def setUp(self):
        self.category = make_category()
        self.medicine = make_medicine(self.category)
        self.user = User.objects.create_user(username="admin", password="pw", role="ADMIN")

    def test_direct_sale_confirmation(self):
        """Stock is correctly deducted for Direct Sale."""
        batch = make_batch(self.medicine, qty=100, expiry_delta_days=100)
        txn = make_draft_txn(self.user, DispensingTypeChoices.DIRECT_SALE)
        cart = build_cart(self.medicine, 20)

        completed = confirm_transaction(txn, cart, self.user)

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining, 80)
        self.assertEqual(completed.status, TransactionStatusChoices.COMPLETED)
        self.assertIsNotNone(completed.completed_at)

    def test_external_prescription_confirmation(self):
        """Stock is correctly deducted for External Prescription."""
        batch = make_batch(self.medicine, qty=100, expiry_delta_days=100)
        txn = make_draft_txn(self.user, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)
        cart = build_cart(
            self.medicine, 20,
            dose="1 tablet", frequency="TDS", duration="5 days", instructions="Take after meal"
        )

        completed = confirm_transaction(txn, cart, self.user)

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining, 80)
        self.assertEqual(completed.status, TransactionStatusChoices.COMPLETED)

        item = DispensingItem.objects.get(transaction=completed)
        self.assertEqual(item.dose, "1 tablet")
        self.assertEqual(item.frequency, "TDS")
        self.assertEqual(item.duration, "5 days")
        self.assertEqual(item.instructions, "Take after meal")

    def test_dispensed_stock_transaction_created(self):
        """DISPENSED StockTransaction with correct prev/new qtys."""
        batch = make_batch(self.medicine, qty=100, expiry_delta_days=100)
        txn = make_draft_txn(self.user)
        cart = build_cart(self.medicine, 20)

        completed = confirm_transaction(txn, cart, self.user)

        stock_txn = StockTransaction.objects.filter(
            batch=batch,
            transaction_type=TransactionTypeChoices.DISPENSED,
        ).first()
        self.assertIsNotNone(stock_txn)
        self.assertEqual(stock_txn.quantity, 20)
        self.assertEqual(stock_txn.previous_quantity, 100)
        self.assertEqual(stock_txn.new_quantity, 80)
        self.assertEqual(stock_txn.reference_number, completed.transaction_number)

    def test_transaction_total_correct(self):
        """Total = qty × selling_price."""
        make_batch(self.medicine, qty=100, expiry_delta_days=100, selling_price="15.00")
        txn = make_draft_txn(self.user)
        cart = build_cart(self.medicine, 4)

        completed = confirm_transaction(txn, cart, self.user)

        self.assertEqual(completed.total_amount, Decimal('60.00'))

    def test_completed_transaction_financial_values_display_in_sle(self):
        make_batch(self.medicine, qty=100, expiry_delta_days=100, selling_price='1250.50')
        txn = make_draft_txn(self.user)
        completed = confirm_transaction(txn, build_cart(self.medicine, 2), self.user)
        self.client.login(username='admin', password='pw')

        history = self.client.get(reverse('dispensing:transaction_list'))
        detail = self.client.get(reverse('dispensing:transaction_detail', args=[completed.pk]))

        self.assertContains(history, 'SLE 2,501.00')
        self.assertContains(detail, 'SLE 1,250.50')
        self.assertContains(detail, 'SLE 2,501.00', count=2)

    def test_multi_batch_dispensing_fefo(self):
        """FEFO multi-batch dispensing deducts correctly."""
        batch_a = make_batch(self.medicine, qty=10, expiry_delta_days=30, selling_price="10.00")
        batch_b = make_batch(self.medicine, qty=20, expiry_delta_days=200, selling_price="12.00")
        txn = make_draft_txn(self.user)
        cart = build_cart(self.medicine, 15)

        completed = confirm_transaction(txn, cart, self.user)

        batch_a.refresh_from_db()
        batch_b.refresh_from_db()
        self.assertEqual(batch_a.quantity_remaining, 0)
        self.assertEqual(batch_b.quantity_remaining, 15)

        items = list(DispensingItem.objects.filter(transaction=completed).order_by('batch__expiry_date'))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].batch.pk, batch_a.pk)
        self.assertEqual(items[0].quantity, 10)
        self.assertEqual(items[1].batch.pk, batch_b.pk)
        self.assertEqual(items[1].quantity, 5)

    def test_insufficient_stock_blocks_completion(self):
        """Cannot exceed available stock."""
        make_batch(self.medicine, qty=5, expiry_delta_days=100)
        txn = make_draft_txn(self.user)
        cart = build_cart(self.medicine, 10)

        with self.assertRaises(ValidationError):
            confirm_transaction(txn, cart, self.user)

        txn.refresh_from_db()
        self.assertEqual(txn.status, TransactionStatusChoices.DRAFT)

    def test_insufficient_stock_does_not_change_stock(self):
        """Atomic rollback — partial stock should NOT be deducted."""
        batch = make_batch(self.medicine, qty=5, expiry_delta_days=100)
        txn = make_draft_txn(self.user)
        cart = build_cart(self.medicine, 10)

        try:
            confirm_transaction(txn, cart, self.user)
        except ValidationError:
            pass

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining, 5)

    def test_empty_cart_raises(self):
        """Empty cart should not be confirmable."""
        txn = make_draft_txn(self.user)
        with self.assertRaises(ValidationError):
            confirm_transaction(txn, {}, self.user)


# ---------------------------------------------------------------------------
# Test: ExternalPrescription Metadata Integrity
# ---------------------------------------------------------------------------

class ExternalPrescriptionMetadataTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="staff", password="pw", role="PHARMACY_STAFF")
        self.txn = make_draft_txn(self.user, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)

    def test_one_external_prescription_record_per_transaction(self):
        """One-to-one enforcement: saving metadata creates exactly 1 row."""
        ep1 = ExternalPrescription.objects.create(
            transaction=self.txn,
            prescriber_name="Dr. Smith",
        )
        self.assertEqual(ExternalPrescription.objects.filter(transaction=self.txn).count(), 1)

    def test_update_or_create_metadata_prevents_duplicates(self):
        """Updating metadata modifies existing row instead of duplicating."""
        ep1 = ExternalPrescription.objects.create(
            transaction=self.txn,
            prescriber_name="Dr. Smith",
        )
        # Re-save via view form (update)
        ep1.prescriber_name = "Dr. Jane Smith"
        ep1.save()

        self.assertEqual(ExternalPrescription.objects.filter(transaction=self.txn).count(), 1)
        ep_db = ExternalPrescription.objects.get(transaction=self.txn)
        self.assertEqual(ep_db.prescriber_name, "Dr. Jane Smith")

    def test_draft_prescription_does_not_affect_inventory(self):
        """DRAFT prescription metadata creation does not change medicine batch stock."""
        category = make_category()
        medicine = make_medicine(category)
        batch = make_batch(medicine, qty=50)

        ExternalPrescription.objects.create(
            transaction=self.txn,
            prescriber_name="Dr. Smith",
        )

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining, 50)
        self.assertFalse(StockTransaction.objects.filter(transaction_type=TransactionTypeChoices.DISPENSED).exists())

    def test_cancelled_prescription_does_not_affect_inventory(self):
        """CANCELLED external prescription does not touch stock."""
        category = make_category()
        medicine = make_medicine(category)
        batch = make_batch(medicine, qty=50)

        ExternalPrescription.objects.create(
            transaction=self.txn,
            prescriber_name="Dr. Smith",
        )
        self.txn.status = TransactionStatusChoices.CANCELLED
        self.txn.save()

        batch.refresh_from_db()
        self.assertEqual(batch.quantity_remaining, 50)
        self.assertFalse(StockTransaction.objects.filter(transaction_type=TransactionTypeChoices.DISPENSED).exists())


# ---------------------------------------------------------------------------
# Test: External Prescription Views & Workflow
# ---------------------------------------------------------------------------

class ExternalPrescriptionViewTests(TestCase):
    def setUp(self):
        self.category = make_category()
        self.medicine = make_medicine(self.category)
        self.batch = make_batch(self.medicine, qty=100, expiry_delta_days=100)
        self.admin = User.objects.create_user(username="admin", password="pw", role="ADMIN")
        self.staff = User.objects.create_user(username="staff", password="pw", role="PHARMACY_STAFF")

    def test_new_external_prescription_creates_draft(self):
        """GET /dispensing/external/new/ creates DRAFT EXTERNAL_PRESCRIPTION."""
        self.client.login(username="staff", password="pw")
        response = self.client.get(reverse('dispensing:new_external_prescription'))
        self.assertEqual(response.status_code, 302)

        txn = DispensingTransaction.objects.filter(user=self.staff).last()
        self.assertEqual(txn.transaction_type, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)
        self.assertEqual(txn.status, TransactionStatusChoices.DRAFT)
        self.assertTrue(txn.transaction_number.startswith("TX-"))

    def test_save_metadata_view(self):
        """POST /dispensing/<pk>/save-metadata/ updates prescription metadata without duplicates."""
        self.client.login(username="staff", password="pw")
        txn = make_draft_txn(self.staff, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)

        # Initial save
        response = self.client.post(
            reverse('dispensing:external_prescription_save_metadata', kwargs={'pk': txn.pk}),
            {
                'prescriber_name': 'Dr. Alice',
                'notes': 'Allergic to penicillin',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExternalPrescription.objects.filter(transaction=txn).count(), 1)
        ep = ExternalPrescription.objects.get(transaction=txn)
        self.assertEqual(ep.prescriber_name, 'Dr. Alice')

        # Re-save (edit metadata)
        response = self.client.post(
            reverse('dispensing:external_prescription_save_metadata', kwargs={'pk': txn.pk}),
            {
                'prescriber_name': 'Dr. Alice Updated',
                'notes': 'Allergic to penicillin',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExternalPrescription.objects.filter(transaction=txn).count(), 1)
        ep.refresh_from_db()
        self.assertEqual(ep.prescriber_name, 'Dr. Alice Updated')

    def test_add_item_with_dosage_to_prescription_cart(self):
        """POST /dispensing/<pk>/external-add/ stores medicine + dosage instructions in session."""
        self.client.login(username="staff", password="pw")
        txn = make_draft_txn(self.staff, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)

        response = self.client.post(
            reverse('dispensing:external_prescription_add_to_cart', kwargs={'pk': txn.pk}),
            {
                'medicine_id': self.medicine.pk,
                'quantity': 10,
                'dose': '2 tablets',
                'frequency': 'BD',
                'duration': '5 days',
                'instructions': 'Take after food',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        cart = self.client.session.get(f"cart_{txn.pk}", {})
        key = str(self.medicine.pk)
        self.assertIn(key, cart)
        self.assertEqual(cart[key]['quantity'], 10)
        self.assertEqual(cart[key]['dose'], '2 tablets')
        self.assertEqual(cart[key]['frequency'], 'BD')
        self.assertEqual(cart[key]['duration'], '5 days')
        self.assertEqual(cart[key]['instructions'], 'Take after food')

    def test_confirm_external_prescription_view(self):
        """POST /dispensing/<pk>/confirm-external/ completes prescription transaction."""
        self.client.login(username="staff", password="pw")
        txn = make_draft_txn(self.staff, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)

        # Save metadata first
        ExternalPrescription.objects.create(
            transaction=txn,
            prescriber_name="Dr. Gregory House",
        )

        # Set cart session
        session = self.client.session
        session[f"cart_{txn.pk}"] = {
            str(self.medicine.pk): {
                'medicine_id': self.medicine.pk,
                'medicine_name': str(self.medicine),
                'quantity': 15,
                'dose': '1 tab',
                'frequency': 'OD',
                'duration': '15 days',
                'instructions': 'Morning only',
            }
        }
        session.save()

        response = self.client.post(
            reverse('dispensing:confirm_external_prescription', kwargs={'pk': txn.pk}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        txn.refresh_from_db()
        self.assertEqual(txn.status, TransactionStatusChoices.COMPLETED)

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining, 85)

        item = DispensingItem.objects.get(transaction=txn)
        self.assertEqual(item.quantity, 15)
        self.assertEqual(item.dose, '1 tab')
        self.assertEqual(item.instructions, 'Morning only')

    def test_transaction_detail_shows_external_prescription_metadata(self):
        """Detail view displays prescriber and patient details if present."""
        self.client.login(username="admin", password="pw")
        txn = DispensingTransaction.objects.create(
            user=self.admin,
            transaction_type=DispensingTypeChoices.EXTERNAL_PRESCRIPTION,
            status=TransactionStatusChoices.COMPLETED,
            total_amount=Decimal('100.00'),
        )
        ExternalPrescription.objects.create(
            transaction=txn,
            prescriber_name="Dr. Strange",
        )

        response = self.client.get(reverse('dispensing:transaction_detail', kwargs={'pk': txn.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Strange")
        self.assertContains(response, "Prescription Metadata")

    def test_transaction_list_filters_by_external_prescription(self):
        """Filter transactions list by type = EXTERNAL_PRESCRIPTION."""
        self.client.login(username="admin", password="pw")
        txn1 = make_draft_txn(self.admin, DispensingTypeChoices.DIRECT_SALE)
        txn2 = make_draft_txn(self.admin, DispensingTypeChoices.EXTERNAL_PRESCRIPTION)

        response = self.client.get(
            reverse('dispensing:transaction_list'),
            {'type': DispensingTypeChoices.EXTERNAL_PRESCRIPTION}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, txn2.transaction_number)
        self.assertNotContains(response, txn1.transaction_number)

# ---------------------------------------------------------------------------
# Test: Consultation Workflow
# ---------------------------------------------------------------------------

from .models import Consultation, SexChoices, PregnancyStatusChoices

class ConsultationWorkflowTest(TestCase):
    def setUp(self):
        self.category = make_category()
        self.medicine = make_medicine(self.category, "Ibuprofen")
        self.batch = make_batch(self.medicine, qty=100)
        self.staff = User.objects.create_user(username="staff", password="pw", role="PHARMACIST")

    def test_new_consultation_creates_draft(self):
        """GET /dispensing/consultation/new/ creates DRAFT txn and redirects."""
        self.client.login(username="staff", password="pw")
        response = self.client.get(reverse('dispensing:new_consultation'))
        txn = DispensingTransaction.objects.get()
        self.assertEqual(txn.transaction_type, DispensingTypeChoices.CONSULTATION)
        self.assertEqual(txn.status, TransactionStatusChoices.DRAFT)
        self.assertRedirects(response, reverse('dispensing:consultation_cart', kwargs={'pk': txn.pk}))

    def test_consultation_cart_displays_safety_notice(self):
        """Consultation cart view displays the required clinical decision support text."""
        self.client.login(username="staff", password="pw")
        txn = make_draft_txn(self.staff, DispensingTypeChoices.CONSULTATION)
        response = self.client.get(reverse('dispensing:consultation_cart', kwargs={'pk': txn.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Clinical decision support has not been run.")

    def test_consultation_save_metadata(self):
        """POST /dispensing/<pk>/consultation-save-metadata/ creates/updates Consultation record."""
        self.client.login(username="staff", password="pw")
        txn = make_draft_txn(self.staff, DispensingTypeChoices.CONSULTATION)

        response = self.client.post(
            reverse('dispensing:consultation_save_metadata', kwargs={'pk': txn.pk}),
            {
                'sex': SexChoices.FEMALE,
                'age': 45,
                'weight': 75.5,
                'pregnancy_status': PregnancyStatusChoices.NOT_PREGNANT,
                'symptoms': 'Headache, fever',
                'symptom_duration': '3 days',
                'known_allergies': 'Penicillin',
                'current_medications': 'None',
                'notes': 'Encourage hydration.',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        metadata = Consultation.objects.get(transaction=txn)
        self.assertEqual(metadata.symptoms, 'Headache, fever')
        self.assertEqual(metadata.age, 45)
        self.assertEqual(metadata.sex, SexChoices.FEMALE)
        self.assertEqual(metadata.symptom_duration, '3 days')
        self.assertEqual(float(metadata.weight), 75.5)
        self.assertEqual(metadata.known_allergies, 'Penicillin')
        self.assertEqual(metadata.notes, 'Encourage hydration.')

    def test_consultation_form_uses_clear_units_and_supported_choices(self):
        form = ConsultationForm()

        self.assertEqual(form.fields['weight'].label, 'Weight (kg)')
        self.assertFalse(form.fields['weight'].required)
        self.assertFalse(form.fields['sex'].required)
        self.assertFalse(form.fields['pregnancy_status'].required)
        self.assertEqual(
            [value for value, _label in form.fields['sex'].choices if value],
            [SexChoices.MALE, SexChoices.FEMALE],
        )
        self.assertEqual(
            [value for value, _label in form.fields['pregnancy_status'].choices if value],
            [PregnancyStatusChoices.PREGNANT, PregnancyStatusChoices.NOT_PREGNANT],
        )

    def test_legacy_consultation_choices_cannot_be_submitted_by_new_form(self):
        form = ConsultationForm(data={
            'symptoms': 'Synthetic symptoms',
            'sex': SexChoices.OTHER,
            'pregnancy_status': PregnancyStatusChoices.UNKNOWN,
        })

        self.assertFalse(form.is_valid())
        self.assertIn('sex', form.errors)
        self.assertIn('pregnancy_status', form.errors)

    def test_consultation_validation_symptoms_required_and_weight_positive(self):
        """Validation enforces symptoms presence and positive weight."""
        self.client.login(username="staff", password="pw")
        txn = make_draft_txn(self.staff, DispensingTypeChoices.CONSULTATION)

        # Empty symptoms
        response = self.client.post(
            reverse('dispensing:consultation_save_metadata', kwargs={'pk': txn.pk}),
            {
                'symptoms': '',
                'weight': 60.0,
            },
            follow=True,
        )
        self.assertFalse(Consultation.objects.filter(transaction=txn).exists())

        # Negative weight
        response = self.client.post(
            reverse('dispensing:consultation_save_metadata', kwargs={'pk': txn.pk}),
            {
                'symptoms': 'Cough',
                'weight': -5.0,
            },
            follow=True,
        )
        self.assertFalse(Consultation.objects.filter(transaction=txn).exists())

    def test_confirm_consultation_view(self):
        """POST /dispensing/<pk>/confirm-consultation/ completes consultation transaction."""
        self.client.login(username="staff", password="pw")
        txn = make_draft_txn(self.staff, DispensingTypeChoices.CONSULTATION)

        # Ensure metadata exists
        Consultation.objects.create(
            transaction=txn,
            symptoms="Mild cough",
            weight=60.0,
        )

        # Set cart session
        session = self.client.session
        session[f"cart_{txn.pk}"] = build_cart(self.medicine, quantity=10)
        session.save()

        response = self.client.post(
            reverse('dispensing:confirm_consultation', kwargs={'pk': txn.pk}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        txn.refresh_from_db()
        self.assertEqual(txn.status, TransactionStatusChoices.COMPLETED)

        self.batch.refresh_from_db()
        self.assertEqual(self.batch.quantity_remaining, 90)

    def test_transaction_detail_shows_consultation_metadata(self):
        """Detail view displays consultation details if present."""
        self.client.login(username="staff", password="pw")
        txn = DispensingTransaction.objects.create(
            user=self.staff,
            transaction_type=DispensingTypeChoices.CONSULTATION,
            status=TransactionStatusChoices.COMPLETED,
            total_amount=Decimal('100.00'),
        )
        Consultation.objects.create(
            transaction=txn,
            symptoms="High fever",
            symptom_duration="2 days",
            notes="Review if fever persists.",
            weight=80.5,
            sex=SexChoices.OTHER,
            pregnancy_status=PregnancyStatusChoices.UNKNOWN,
        )

        response = self.client.get(reverse('dispensing:transaction_detail', kwargs={'pk': txn.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "High fever")
        self.assertContains(response, "2 days")
        self.assertContains(response, "Review if fever persists.")
        self.assertContains(response, "Consultation Details")
        self.assertContains(response, "Other")
        self.assertContains(response, "Unknown / Not Applicable")
