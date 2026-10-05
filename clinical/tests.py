from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from dispensing.models import (
    Consultation, DispensingItem, DispensingTransaction, DoseUnitChoices, TransactionStatusChoices,
    TransactionTypeChoices,
)
from inventory.models import MedicineBatch
from medicines.models import Medicine, MedicineCategory

from .models import (
    Allergen, AllergyRule, AlertTypeChoices, ClinicalAlert, ClinicalCheckResult,
    ClinicalCheckStatus, ClinicalCheckType, ClinicalReview, DrugInteractionRule,
    SeverityChoices, DosageRule, DosageAlertReason, RuleLifecycleStatus,
)
from .services import (
    check_allergies, check_drug_interactions, current_review,
    invalidate_clinical_review, run_clinical_review,
)
from .dosage import check_dosage, dosage_fingerprint

User = get_user_model()


class ClinicalTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='clinical_staff', password='pw', role='PHARMACY_STAFF'
        )
        self.category = MedicineCategory.objects.create(name='Synthetic Clinical Test Medicines')
        self.medicines = [self.make_medicine(name) for name in ('Synthetic Alpha', 'Synthetic Beta', 'Synthetic Gamma')]
        self.batches = [self.make_batch(medicine, index) for index, medicine in enumerate(self.medicines, 1)]

    def make_medicine(self, name):
        return Medicine.objects.create(
            category=self.category,
            generic_name=name,
            strength='1 test-unit',
            dosage_form='TABLET',
            unit='tablet',
        )

    def make_batch(self, medicine, index):
        return MedicineBatch.objects.create(
            medicine=medicine,
            batch_number=f'CLINICAL-{index}',
            quantity_received=100,
            quantity_remaining=100,
            cost_price='1.00',
            selling_price='2.00',
            date_received=date.today(),
            expiry_date=date.today() + timedelta(days=365),
        )

    def make_transaction(self, transaction_type=TransactionTypeChoices.DIRECT_SALE):
        return DispensingTransaction.objects.create(
            user=self.user,
            transaction_type=transaction_type,
            status=TransactionStatusChoices.DRAFT,
        )

    def make_rule(self, medicine_a=None, medicine_b=None, severity=SeverityChoices.HIGH, active=True):
        return DrugInteractionRule.objects.create(
            medicine_a=medicine_a or self.medicines[0],
            medicine_b=medicine_b or self.medicines[1],
            severity=severity,
            description='Synthetic interaction description',
            explanation='Synthetic interaction explanation',
            recommendation='Synthetic interaction recommendation',
            source_reference='SYNTHETIC-REFERENCE-001',
            is_active=active,
            status=RuleLifecycleStatus.ACTIVE, approved_by=self.user, approved_at=timezone.now(),
        )

    def cart(self, medicines=None, quantity=2):
        medicines = medicines or self.medicines[:2]
        return {
            str(medicine.pk): {
                'medicine_id': medicine.pk,
                'medicine_name': str(medicine),
                'quantity': quantity,
            }
            for medicine in medicines
        }

    def set_session_cart(self, transaction, medicines=None, quantity=2):
        session = self.client.session
        session[f'cart_{transaction.pk}'] = self.cart(medicines, quantity)
        session.save()


class DrugInteractionRuleTests(ClinicalTestBase):
    def test_rule_creation_and_canonical_order(self):
        rule = self.make_rule(medicine_a=self.medicines[1], medicine_b=self.medicines[0])
        self.assertLess(rule.medicine_a_id, rule.medicine_b_id)
        self.assertEqual(rule.severity, SeverityChoices.HIGH)

    def test_same_medicine_rule_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.make_rule(medicine_a=self.medicines[0], medicine_b=self.medicines[0])

    def test_reversed_duplicate_rule_is_rejected(self):
        self.make_rule()
        with self.assertRaises(ValidationError):
            self.make_rule(medicine_a=self.medicines[1], medicine_b=self.medicines[0])


class ClinicalServiceTests(ClinicalTestBase):
    def test_inactive_rule_is_ignored(self):
        self.make_rule(active=False)
        result = check_drug_interactions(self.make_transaction(), [m.pk for m in self.medicines[:2]])
        self.assertEqual(result['status'], ClinicalCheckStatus.PASSED)
        self.assertEqual(result['alerts'], [])

    def test_active_rule_detected_and_snapshot_fields_preserved(self):
        self.make_rule()
        transaction = self.make_transaction()
        result = check_drug_interactions(transaction, [m.pk for m in self.medicines[:2]])
        alert = result['alerts'][0]
        self.assertEqual(result['status'], ClinicalCheckStatus.WARNING)
        self.assertEqual(alert.explanation, 'Synthetic interaction explanation')
        self.assertEqual(alert.recommendation, 'Synthetic interaction recommendation')
        self.assertEqual(alert.source_reference, 'SYNTHETIC-REFERENCE-001')

    def test_all_severities_are_preserved(self):
        rule = self.make_rule()
        transaction = self.make_transaction()
        for severity in SeverityChoices.values:
            with self.subTest(severity=severity):
                rule.severity = severity
                DrugInteractionRule.objects.filter(pk=rule.pk).update(severity=severity)
                result = check_drug_interactions(transaction, [m.pk for m in self.medicines[:2]])
                self.assertEqual(result['alerts'][0].severity, severity)

    def test_one_medicine_is_not_applicable(self):
        result = check_drug_interactions(self.make_transaction(), [self.medicines[0].pk])
        self.assertEqual(result['status'], ClinicalCheckStatus.NOT_APPLICABLE)
        self.assertEqual(result['checked_pairs'], 0)

    def test_two_medicines_without_rule_pass(self):
        result = check_drug_interactions(self.make_transaction(), [m.pk for m in self.medicines[:2]])
        self.assertEqual(result['status'], ClinicalCheckStatus.PASSED)
        self.assertEqual(result['checked_pairs'], 1)

    def test_three_medicines_evaluate_all_unique_pairs(self):
        result = check_drug_interactions(self.make_transaction(), [m.pk for m in self.medicines])
        self.assertEqual(result['checked_pairs'], 3)

    def test_multiple_rules_create_multiple_alerts(self):
        self.make_rule()
        self.make_rule(medicine_a=self.medicines[1], medicine_b=self.medicines[2])
        transaction = self.make_transaction()
        result = check_drug_interactions(transaction, [m.pk for m in self.medicines])
        self.assertEqual(result['status'], ClinicalCheckStatus.WARNING)
        self.assertEqual(len(result['alerts']), 2)

    def test_rerun_does_not_create_duplicate_alerts(self):
        self.make_rule()
        transaction = self.make_transaction()
        ids = [m.pk for m in self.medicines[:2]]
        check_drug_interactions(transaction, ids)
        check_drug_interactions(transaction, ids)
        self.assertEqual(ClinicalAlert.objects.filter(transaction=transaction).count(), 1)

    def test_cart_change_invalidates_review_and_alerts(self):
        self.make_rule()
        transaction = self.make_transaction()
        check_drug_interactions(transaction, [m.pk for m in self.medicines[:2]])
        invalidate_clinical_review(transaction)
        review = ClinicalReview.objects.get(transaction=transaction)
        self.assertEqual(review.status, ClinicalCheckStatus.NOT_CHECKED)
        self.assertIsNone(review.checked_at)
        self.assertFalse(ClinicalAlert.objects.filter(transaction=transaction).exists())
        self.assertIsNone(current_review(transaction, [m.pk for m in self.medicines]))

    def test_review_does_not_deduct_stock(self):
        before = [batch.quantity_remaining for batch in self.batches]
        check_drug_interactions(self.make_transaction(), [m.pk for m in self.medicines[:2]])
        for batch, expected in zip(self.batches, before):
            batch.refresh_from_db()
            self.assertEqual(batch.quantity_remaining, expected)

    def test_missing_medicine_returns_not_checked(self):
        result = check_drug_interactions(self.make_transaction(), [self.medicines[0].pk, 999999])
        self.assertEqual(result['status'], ClinicalCheckStatus.NOT_CHECKED)

    def test_rule_edits_do_not_change_historical_alert_snapshot(self):
        rule = self.make_rule()
        transaction = self.make_transaction()
        alert = check_drug_interactions(transaction, [m.pk for m in self.medicines[:2]])['alerts'][0]
        rule.explanation = 'Edited later'
        rule.recommendation = 'Edited recommendation'
        rule.source_reference = 'EDITED-SOURCE'
        DrugInteractionRule.objects.filter(pk=rule.pk).update(
            explanation=rule.explanation, recommendation=rule.recommendation, source_reference=rule.source_reference,
        )
        alert.refresh_from_db()
        self.assertEqual(alert.explanation, 'Synthetic interaction explanation')
        self.assertEqual(alert.recommendation, 'Synthetic interaction recommendation')
        self.assertEqual(alert.source_reference, 'SYNTHETIC-REFERENCE-001')


class ClinicalWorkflowTests(ClinicalTestBase):
    def setUp(self):
        super().setUp()
        self.client.login(username='clinical_staff', password='pw')

    def test_review_endpoint_works_for_all_dispensing_workflows(self):
        self.make_rule()
        cases = (
            (TransactionTypeChoices.DIRECT_SALE, 'dispensing:sale_cart'),
            (TransactionTypeChoices.EXTERNAL_PRESCRIPTION, 'dispensing:external_prescription_cart'),
            (TransactionTypeChoices.CONSULTATION, 'dispensing:consultation_cart'),
        )
        for transaction_type, cart_view in cases:
            with self.subTest(transaction_type=transaction_type):
                transaction = self.make_transaction(transaction_type)
                self.set_session_cart(transaction)
                response = self.client.post(
                    reverse('dispensing:run_clinical_review', kwargs={'pk': transaction.pk}), follow=True
                )
                self.assertRedirects(response, reverse(cart_view, kwargs={'pk': transaction.pk}))
                self.assertContains(response, 'Drug Interaction Warning')
                self.assertContains(response, 'Synthetic interaction explanation')

    def test_cart_displays_not_yet_evaluated_without_false_conclusion(self):
        transaction = self.make_transaction()
        response = self.client.get(reverse('dispensing:sale_cart', kwargs={'pk': transaction.pk}))
        self.assertContains(response, 'Not yet evaluated')
        html = response.content.decode()
        ai_panel = html.split('<section class="ai-panel"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(ai_panel.count('Not yet evaluated'), 1)
        self.assertNotIn('class="ai-priority-heading">NOT YET EVALUATED', ai_panel)
        self.assertContains(response, 'Run the clinical review to evaluate drug interactions, allergies, dosage checks, and AI review priority.')
        self.assertNotContains(response, 'Not available')
        self.assertNotContains(response, '>PASSED<', html=False)

    def test_one_medicine_uses_not_applicable_card_without_page_banner(self):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        self.set_session_cart(transaction, [self.medicines[0]])

        response = self.client.post(
            reverse('dispensing:run_clinical_review', kwargs={'pk': transaction.pk}),
            follow=True,
        )

        self.assertContains(response, 'Drug Interaction Check')
        self.assertContains(response, 'NOT_APPLICABLE')
        self.assertNotContains(
            response,
            'Drug interaction checking is not applicable with fewer than two medicines.',
        )
        self.assertContains(response, 'Clinical Review: INCOMPLETE')

    def test_two_medicines_without_interaction_show_passed(self):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        self.set_session_cart(transaction, self.medicines[:2])

        self.client.post(
            reverse('dispensing:run_clinical_review', kwargs={'pk': transaction.pk}),
        )

        interaction = ClinicalCheckResult.objects.get(
            transaction=transaction,
            check_type=ClinicalCheckType.DRUG_INTERACTION,
        )
        self.assertEqual(interaction.status, ClinicalCheckStatus.PASSED)
        ClinicalCheckResult.objects.filter(transaction=transaction).update(
            status=ClinicalCheckStatus.PASSED
        )
        response = self.client.get(
            reverse('dispensing:consultation_cart', kwargs={'pk': transaction.pk})
        )
        self.assertContains(response, 'Clinical Review: COMPLETE')

    def test_not_checked_result_marks_review_incomplete(self):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        self.set_session_cart(transaction, [self.medicines[0]])
        run_clinical_review(transaction, [self.medicines[0].pk])
        ClinicalCheckResult.objects.filter(
            transaction=transaction,
            check_type=ClinicalCheckType.DOSAGE,
        ).update(status=ClinicalCheckStatus.NOT_CHECKED)

        response = self.client.get(
            reverse('dispensing:consultation_cart', kwargs={'pk': transaction.pk})
        )

        self.assertContains(response, 'Clinical Review: INCOMPLETE')
        self.assertContains(response, '2 checks were not fully evaluated.')

    def test_ai_metadata_is_inside_collapsed_technical_details(self):
        assessment = SimpleNamespace(
            predicted_priority='LOW',
            final_priority='LOW',
            prediction_probability=Decimal('0.91'),
            model_version=SimpleNamespace(version='synthetic-test-1'),
            feature_snapshot={
                'medicine_count': 1, 'interaction_warning_count': 0,
                'allergy_warning_count': 0, 'dosage_warning_count': 0,
                'low_alert_count': 0, 'moderate_alert_count': 0,
                'high_alert_count': 0, 'critical_alert_count': 0,
                'not_checked_count': 0, 'warning_check_count': 0,
                'transaction_type': 2,
            },
            decision_path=[],
            explanation='Synthetic technical explanation.',
        )
        ai_panel = render_to_string('dispensing/_ai_review_panel.html', {
            'assessment': assessment,
            'review_completed': True,
            'show_review_completeness': True,
            'review_complete': True,
            'incomplete_count': 0,
        })
        default_content, technical_content = ai_panel.split('<details class="ai-technical-details">', 1)

        self.assertNotIn('Final Guarded Priority', default_content)
        self.assertNotIn('Model Classification Confidence', default_content)
        self.assertNotIn('Model Version', default_content)
        self.assertIn('Show Technical AI Details', technical_content)
        self.assertIn('Final Guarded Priority', technical_content)
        self.assertIn('Model Classification Confidence', technical_content)
        self.assertIn('Model Version', technical_content)

    def test_warning_confirmation_requires_acknowledgement_and_saves_audit_fields(self):
        self.make_rule()
        transaction = self.make_transaction()
        self.set_session_cart(transaction)
        url = reverse('dispensing:confirm_sale', kwargs={'pk': transaction.pk})

        self.client.post(url)
        transaction.refresh_from_db()
        self.batches[0].refresh_from_db()
        self.assertEqual(transaction.status, TransactionStatusChoices.DRAFT)
        self.assertEqual(self.batches[0].quantity_remaining, 100)

        response = self.client.post(url, {
            'acknowledge_clinical_warnings': 'on',
            'acknowledgement_note': 'Synthetic warning reviewed.',
        })
        self.assertEqual(response.status_code, 302)
        transaction.refresh_from_db()
        alert = ClinicalAlert.objects.get(transaction=transaction)
        self.assertEqual(transaction.status, TransactionStatusChoices.COMPLETED)
        self.assertEqual(alert.acknowledged_by, self.user)
        self.assertIsNotNone(alert.acknowledged_at)
        self.assertEqual(alert.acknowledgement_note, 'Synthetic warning reviewed.')

    def test_critical_warning_requires_acknowledgement(self):
        self.make_rule(severity=SeverityChoices.CRITICAL)
        transaction = self.make_transaction()
        self.set_session_cart(transaction)
        self.client.post(reverse('dispensing:confirm_sale', kwargs={'pk': transaction.pk}))
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, TransactionStatusChoices.DRAFT)

    def test_not_checked_confirmation_does_not_deduct_stock(self):
        transaction = self.make_transaction()
        session = self.client.session
        session[f'cart_{transaction.pk}'] = {
            str(self.medicines[0].pk): self.cart([self.medicines[0]])[str(self.medicines[0].pk)],
            '999999': {'medicine_id': 999999, 'medicine_name': 'Missing', 'quantity': 1},
        }
        session.save()
        self.client.post(reverse('dispensing:confirm_sale', kwargs={'pk': transaction.pk}))
        transaction.refresh_from_db()
        self.batches[0].refresh_from_db()
        self.assertEqual(transaction.status, TransactionStatusChoices.DRAFT)
        self.assertEqual(self.batches[0].quantity_remaining, 100)

    def test_completed_transaction_detail_uses_historical_snapshot(self):
        rule = self.make_rule()
        transaction = self.make_transaction()
        self.set_session_cart(transaction)
        self.client.post(reverse('dispensing:confirm_sale', kwargs={'pk': transaction.pk}), {
            'acknowledge_clinical_warnings': 'on',
            'acknowledgement_note': 'Reviewed for history',
        })
        rule.explanation = 'Changed source rule text'
        DrugInteractionRule.objects.filter(pk=rule.pk).update(explanation=rule.explanation)
        response = self.client.get(reverse('dispensing:transaction_detail', kwargs={'pk': transaction.pk}))
        self.assertContains(response, 'Historical Clinical Safety Review')
        self.assertContains(response, 'Synthetic interaction explanation')
        self.assertNotContains(response, 'Changed source rule text')
        self.assertContains(response, 'Reviewed for history')
        self.assertContains(response, self.user.username)

    def test_consultation_free_text_medications_are_context_not_checked_claim(self):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        Consultation.objects.create(
            transaction=transaction,
            symptoms='Synthetic symptom',
            current_medications='Unstructured Medicine Z',
        )
        self.set_session_cart(transaction, [self.medicines[0]])
        response = self.client.get(reverse('dispensing:consultation_cart', kwargs={'pk': transaction.pk}))
        self.assertContains(response, 'Unstructured Medicine Z')
        self.assertContains(response, 'were not included in structured drug-interaction matching')

    def test_clinical_review_requires_authentication(self):
        transaction = self.make_transaction()
        self.client.logout()
        response = self.client.post(reverse('dispensing:run_clinical_review', kwargs={'pk': transaction.pk}))
        self.assertEqual(response.status_code, 302)


class AllergyModelAndServiceTests(ClinicalTestBase):
    def setUp(self):
        super().setUp()
        self.allergen = Allergen.objects.create(
            name='Synthetic Allergen Alpha',
            description='Synthetic test allergen only.',
        )

    def make_allergy_rule(self, medicine=None, allergen=None, severity=SeverityChoices.HIGH, active=True):
        return AllergyRule.objects.create(
            medicine=medicine or self.medicines[0],
            allergen=allergen or self.allergen,
            severity=severity,
            description='Synthetic allergy description',
            explanation='Synthetic allergy explanation',
            recommendation='Synthetic allergy recommendation',
            source_reference='SYNTHETIC-ALLERGY-REFERENCE-001',
            is_active=active,
            status=RuleLifecycleStatus.ACTIVE, approved_by=self.user, approved_at=timezone.now(),
        )

    def make_consultation_transaction(self, allergens=None, known_allergies=''):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        consultation = Consultation.objects.create(
            transaction=transaction,
            symptoms='Synthetic symptom',
            known_allergies=known_allergies,
        )
        if allergens:
            consultation.structured_allergies.set(allergens)
        return transaction, consultation

    def test_allergen_and_allergy_rule_creation(self):
        rule = self.make_allergy_rule()
        self.assertEqual(str(self.allergen), 'Synthetic Allergen Alpha')
        self.assertEqual(rule.medicine, self.medicines[0])
        self.assertEqual(rule.allergen, self.allergen)

    def test_duplicate_medicine_allergen_rule_is_rejected(self):
        self.make_allergy_rule()
        with self.assertRaises(ValidationError):
            self.make_allergy_rule()

    def test_inactive_rule_is_ignored_and_active_rule_is_detected(self):
        transaction, _ = self.make_consultation_transaction([self.allergen])
        self.make_allergy_rule(active=False)
        result = check_allergies(transaction, [self.medicines[0].pk])
        self.assertEqual(result['status'], ClinicalCheckStatus.PASSED)
        self.assertEqual(result['alerts'], [])
        AllergyRule.objects.all().delete()
        self.make_allergy_rule()
        result = check_allergies(transaction, [self.medicines[0].pk])
        self.assertEqual(result['status'], ClinicalCheckStatus.WARNING)

    def test_all_severities_and_snapshot_text_are_preserved(self):
        rule = self.make_allergy_rule()
        transaction, _ = self.make_consultation_transaction([self.allergen])
        for severity in SeverityChoices.values:
            with self.subTest(severity=severity):
                rule.severity = severity
                AllergyRule.objects.filter(pk=rule.pk).update(severity=severity)
                alert = check_allergies(transaction, [self.medicines[0].pk])['alerts'][0]
                self.assertEqual(alert.severity, severity)
                self.assertEqual(alert.explanation, 'Synthetic allergy explanation')
                self.assertEqual(alert.recommendation, 'Synthetic allergy recommendation')
                self.assertEqual(alert.source_reference, 'SYNTHETIC-ALLERGY-REFERENCE-001')

    def test_free_text_alone_is_not_reported_as_checked(self):
        transaction, consultation = self.make_consultation_transaction(known_allergies='Synthetic free-text allergy')
        result = check_allergies(transaction, [self.medicines[0].pk])
        consultation.refresh_from_db()
        self.assertEqual(consultation.known_allergies, 'Synthetic free-text allergy')
        self.assertEqual(result['status'], ClinicalCheckStatus.NOT_CHECKED)
        self.assertTrue(result['details']['context_unavailable'])

    def test_structured_allergy_no_match_passes(self):
        transaction, _ = self.make_consultation_transaction([self.allergen])
        result = check_allergies(transaction, [self.medicines[0].pk])
        self.assertEqual(result['status'], ClinicalCheckStatus.PASSED)

    def test_multiple_matches_create_multiple_alerts_without_rerun_duplicates(self):
        second_allergen = Allergen.objects.create(name='Synthetic Allergen Beta')
        self.make_allergy_rule()
        self.make_allergy_rule(allergen=second_allergen)
        transaction, _ = self.make_consultation_transaction([self.allergen, second_allergen])
        ids = [self.medicines[0].pk]
        result = check_allergies(transaction, ids)
        self.assertEqual(len(result['alerts']), 2)
        check_allergies(transaction, ids)
        self.assertEqual(ClinicalAlert.objects.filter(transaction=transaction, alert_type=AlertTypeChoices.ALLERGY).count(), 2)

    def test_interaction_and_allergy_alerts_coexist_and_overall_warning_wins(self):
        self.make_rule()
        self.make_allergy_rule()
        transaction, _ = self.make_consultation_transaction([self.allergen])
        result = run_clinical_review(transaction, [m.pk for m in self.medicines[:2]])
        self.assertEqual(result['status'], ClinicalCheckStatus.WARNING)
        self.assertEqual({alert.alert_type for alert in result['alerts']}, {AlertTypeChoices.DRUG_INTERACTION, AlertTypeChoices.ALLERGY})

    def test_direct_and_external_without_structured_data_are_not_allergy_passed(self):
        for transaction_type in (TransactionTypeChoices.DIRECT_SALE, TransactionTypeChoices.EXTERNAL_PRESCRIPTION):
            with self.subTest(transaction_type=transaction_type):
                result = check_allergies(self.make_transaction(transaction_type), [self.medicines[0].pk])
                self.assertEqual(result['status'], ClinicalCheckStatus.NOT_CHECKED)

    def test_allergy_review_does_not_deduct_stock(self):
        transaction, _ = self.make_consultation_transaction([self.allergen])
        self.make_allergy_rule()
        check_allergies(transaction, [self.medicines[0].pk])
        self.batches[0].refresh_from_db()
        self.assertEqual(self.batches[0].quantity_remaining, 100)

    def test_rule_edit_does_not_change_alert_snapshot(self):
        rule = self.make_allergy_rule()
        transaction, _ = self.make_consultation_transaction([self.allergen])
        alert = check_allergies(transaction, [self.medicines[0].pk])['alerts'][0]
        rule.explanation = 'Changed later'
        rule.recommendation = 'Changed later recommendation'
        rule.source_reference = 'CHANGED-LATER'
        AllergyRule.objects.filter(pk=rule.pk).update(
            explanation=rule.explanation, recommendation=rule.recommendation, source_reference=rule.source_reference,
        )
        alert.refresh_from_db()
        self.assertEqual(alert.explanation, 'Synthetic allergy explanation')
        self.assertEqual(alert.recommendation, 'Synthetic allergy recommendation')
        self.assertEqual(alert.source_reference, 'SYNTHETIC-ALLERGY-REFERENCE-001')


class AllergyWorkflowTests(ClinicalTestBase):
    def setUp(self):
        super().setUp()
        self.client.login(username='clinical_staff', password='pw')
        self.allergen = Allergen.objects.create(name='Synthetic Workflow Allergen')

    def make_consultation_transaction(self):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        consultation = Consultation.objects.create(transaction=transaction, symptoms='Synthetic symptom')
        consultation.structured_allergies.add(self.allergen)
        return transaction, consultation

    def make_allergy_rule(self):
        return AllergyRule.objects.create(
            medicine=self.medicines[0], allergen=self.allergen, severity=SeverityChoices.CRITICAL,
            description='Synthetic workflow allergy', explanation='Synthetic workflow explanation',
            recommendation='Synthetic workflow recommendation', source_reference='SYNTHETIC-WORKFLOW-SOURCE',
            status=RuleLifecycleStatus.ACTIVE, approved_by=self.user, approved_at=timezone.now(),
        )

    def test_structured_allergies_can_be_saved_and_changed_selection_invalidates_review(self):
        second = Allergen.objects.create(name='Synthetic Workflow Allergen Two')
        transaction, consultation = self.make_consultation_transaction()
        run_clinical_review(transaction, [self.medicines[0].pk])
        response = self.client.post(reverse('dispensing:consultation_save_metadata', kwargs={'pk': transaction.pk}), {
            'symptoms': 'Synthetic symptom',
            'structured_allergies': [str(self.allergen.pk), str(second.pk)],
            'known_allergies': 'Free-text remains supported',
        })
        self.assertEqual(response.status_code, 302)
        consultation.refresh_from_db()
        self.assertEqual(consultation.structured_allergies.count(), 2)
        self.assertEqual(consultation.known_allergies, 'Free-text remains supported')
        self.assertFalse(ClinicalCheckResult.objects.filter(transaction=transaction).exists())


class DosageRuleAndServiceTests(ClinicalTestBase):
    def make_dosage_rule(self, medicine=None, **overrides):
        values = {
            'medicine': medicine or self.medicines[0], 'dose_unit': DoseUnitChoices.MG,
            'min_single_dose': Decimal('100'), 'max_single_dose': Decimal('500'),
            'max_daily_dose': Decimal('1200'), 'min_frequency_per_day': Decimal('1'),
            'max_frequency_per_day': Decimal('3'), 'max_duration_days': 10,
            'severity': SeverityChoices.HIGH, 'description': 'Synthetic dosage rule',
            'explanation': 'Synthetic dosage explanation',
            'recommendation': 'Synthetic dosage recommendation',
            'source_reference': 'SYNTHETIC-DOSAGE-REFERENCE', 'is_active': True,
            'status': RuleLifecycleStatus.ACTIVE, 'approved_by': self.user, 'approved_at': timezone.now(),
        }
        values.update(overrides)
        return DosageRule.objects.create(**values)

    def dosage_cart(self, medicine=None, **overrides):
        medicine = medicine or self.medicines[0]
        line = {'medicine_id': medicine.pk, 'medicine_name': str(medicine), 'quantity': 1,
                'dose_amount': '250', 'dose_unit': 'MG', 'frequency_per_day': '2', 'duration_days': 5}
        line.update(overrides)
        return {str(medicine.pk): line}

    def test_rule_creation_and_invalid_ranges(self):
        self.assertEqual(self.make_dosage_rule().dose_unit, 'MG')
        for values in (
            {'min_single_dose': 600, 'max_single_dose': 500},
            {'min_age': 20, 'max_age': 10}, {'min_weight': 20, 'max_weight': 10},
            {'min_frequency_per_day': 4, 'max_frequency_per_day': 3},
        ):
            DosageRule.objects.all().delete()
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.make_dosage_rule(**values)

    def test_source_and_positive_limits_are_required(self):
        with self.assertRaises(ValidationError):
            self.make_dosage_rule(source_reference='')
        with self.assertRaises(ValidationError):
            self.make_dosage_rule(max_daily_dose=0)

    def test_valid_dosage_passes_and_daily_dose_uses_decimal(self):
        self.make_dosage_rule()
        result = check_dosage(self.make_transaction(), self.dosage_cart(dose_amount='0.1', frequency_per_day='3'))
        self.assertEqual(result['status'], ClinicalCheckStatus.WARNING)  # below synthetic minimum
        self.assertEqual(result['details']['items'][0]['calculated_daily_dose'], '0.3')

        transaction = self.make_transaction()
        result = check_dosage(transaction, self.dosage_cart())
        self.assertEqual(result['status'], ClinicalCheckStatus.PASSED)

    def test_each_supported_violation_reason_creates_warning(self):
        self.make_dosage_rule()
        cases = (
            ({'dose_amount': '99'}, DosageAlertReason.BELOW_SINGLE_DOSE),
            ({'dose_amount': '501'}, DosageAlertReason.ABOVE_SINGLE_DOSE),
            ({'dose_amount': '500', 'frequency_per_day': '3'}, DosageAlertReason.ABOVE_DAILY_DOSE),
            ({'frequency_per_day': '0.5'}, DosageAlertReason.FREQUENCY_TOO_LOW),
            ({'frequency_per_day': '4'}, DosageAlertReason.FREQUENCY_TOO_HIGH),
            ({'duration_days': 11}, DosageAlertReason.DURATION_TOO_LONG),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason):
                transaction = self.make_transaction()
                result = check_dosage(transaction, self.dosage_cart(**changes))
                self.assertEqual(result['status'], ClinicalCheckStatus.WARNING)
                self.assertIn(reason, [alert.dosage_reason for alert in result['alerts']])

    def test_not_checked_reasons_are_conservative(self):
        cases = (
            (self.dosage_cart(dose_amount='', dose_unit=''), 'No structured dosage'),
            (self.dosage_cart(), 'No verified dosage rule'),
        )
        for cart, reason in cases:
            with self.subTest(reason=reason):
                result = check_dosage(self.make_transaction(), cart)
                self.assertEqual(result['status'], ClinicalCheckStatus.NOT_CHECKED)
                self.assertIn(reason, result['details']['reason'])
        self.make_dosage_rule()
        result = check_dosage(self.make_transaction(), self.dosage_cart(dose_unit='ML'))
        self.assertEqual(result['status'], ClinicalCheckStatus.NOT_CHECKED)
        self.assertIn('incompatible', result['details']['reason'])

    def test_required_age_and_weight_missing_are_not_checked(self):
        for field in ('min_age', 'min_weight'):
            DosageRule.objects.all().delete()
            self.make_dosage_rule(**{field: 1})
            transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
            Consultation.objects.create(transaction=transaction, symptoms='Synthetic')
            result = check_dosage(transaction, self.dosage_cart())
            self.assertEqual(result['status'], ClinicalCheckStatus.NOT_CHECKED)
            self.assertIn('required', result['details']['reason'])

    def test_inactive_rule_ignored_and_multiple_medicines_independent(self):
        self.make_dosage_rule(is_active=False)
        second = self.make_dosage_rule(medicine=self.medicines[1])
        cart = self.dosage_cart()
        cart.update(self.dosage_cart(self.medicines[1], dose_amount='600'))
        result = check_dosage(self.make_transaction(), cart)
        self.assertEqual(result['status'], ClinicalCheckStatus.WARNING)
        self.assertTrue(all(alert.dosage_rule_reference_id == second.pk for alert in result['alerts']))
        self.assertEqual(len(result['details']['items']), 2)

    def test_rerun_no_duplicates_and_snapshot_survives_rule_edit(self):
        rule = self.make_dosage_rule()
        transaction = self.make_transaction()
        cart = self.dosage_cart(dose_amount='601')
        check_dosage(transaction, cart)
        check_dosage(transaction, cart)
        self.assertEqual(ClinicalAlert.objects.filter(transaction=transaction, alert_type=AlertTypeChoices.DOSAGE).count(), 2)
        alert = ClinicalAlert.objects.filter(transaction=transaction, dosage_reason=DosageAlertReason.ABOVE_SINGLE_DOSE).get()
        rule.explanation = 'Changed after alert'
        DosageRule.objects.filter(pk=rule.pk).update(explanation=rule.explanation)
        alert.refresh_from_db()
        self.assertEqual(alert.snapshot_details['explanation'], 'Synthetic dosage explanation')

    def test_dosage_fingerprint_changes_with_dose_frequency_duration_and_context(self):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        consultation = Consultation.objects.create(transaction=transaction, symptoms='Synthetic', age=20, weight=50)
        base = dosage_fingerprint(transaction, self.dosage_cart())
        for changes in ({'dose_amount': '251'}, {'frequency_per_day': '3'}, {'duration_days': 6}):
            self.assertNotEqual(base, dosage_fingerprint(transaction, self.dosage_cart(**changes)))
        consultation.age = 21
        consultation.save()
        self.assertNotEqual(base, dosage_fingerprint(transaction, self.dosage_cart()))

    def test_structured_and_free_text_fields_save(self):
        transaction = self.make_transaction()
        item = DispensingItem.objects.create(
            transaction=transaction, medicine=self.medicines[0], batch=self.batches[0], quantity=1,
            unit_price='2', line_total='2', dose='250 mg', frequency='twice daily', duration='five days',
            instructions='Synthetic', dose_amount='250', dose_unit='MG', frequency_per_day='2', duration_days=5,
        )
        item.refresh_from_db()
        self.assertEqual(item.dose, '250 mg')
        self.assertEqual(item.dose_amount, Decimal('250'))


class AllergyWorkflowRemainingTests(ClinicalTestBase):
    def setUp(self):
        super().setUp()
        self.client.login(username='clinical_staff', password='pw')
        self.allergen = Allergen.objects.create(name='Synthetic Remaining Workflow Allergen')

    def make_consultation_transaction(self):
        transaction = self.make_transaction(TransactionTypeChoices.CONSULTATION)
        consultation = Consultation.objects.create(transaction=transaction, symptoms='Synthetic symptom')
        consultation.structured_allergies.add(self.allergen)
        return transaction, consultation

    def make_allergy_rule(self):
        return AllergyRule.objects.create(
            medicine=self.medicines[0], allergen=self.allergen, severity=SeverityChoices.CRITICAL,
            description='Synthetic workflow allergy', explanation='Synthetic workflow explanation',
            recommendation='Synthetic workflow recommendation', source_reference='SYNTHETIC-WORKFLOW-SOURCE',
            status=RuleLifecycleStatus.ACTIVE, approved_by=self.user, approved_at=timezone.now(),
        )

    def test_allergy_warning_requires_acknowledgement_and_records_audit(self):
        self.make_allergy_rule()
        transaction, _ = self.make_consultation_transaction()
        self.set_session_cart(transaction, [self.medicines[0]])
        url = reverse('dispensing:confirm_consultation', kwargs={'pk': transaction.pk})
        self.client.post(url)
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, TransactionStatusChoices.DRAFT)
        response = self.client.post(url, {
            'acknowledge_clinical_warnings': 'on',
            'acknowledgement_note': 'Synthetic allergy reviewed.',
        })
        self.assertEqual(response.status_code, 302)
        transaction.refresh_from_db()
        alert = ClinicalAlert.objects.get(transaction=transaction, alert_type=AlertTypeChoices.ALLERGY)
        self.assertEqual(transaction.status, TransactionStatusChoices.COMPLETED)
        self.assertEqual(alert.acknowledged_by, self.user)
        self.assertIsNotNone(alert.acknowledged_at)
        self.assertEqual(alert.acknowledgement_note, 'Synthetic allergy reviewed.')

    def test_historical_allergy_alert_is_displayed_from_snapshot(self):
        rule = self.make_allergy_rule()
        transaction, _ = self.make_consultation_transaction()
        self.set_session_cart(transaction, [self.medicines[0]])
        self.client.post(reverse('dispensing:confirm_consultation', kwargs={'pk': transaction.pk}), {
            'acknowledge_clinical_warnings': 'on',
        })
        rule.explanation = 'Edited after completion'
        AllergyRule.objects.filter(pk=rule.pk).update(explanation=rule.explanation)
        response = self.client.get(reverse('dispensing:transaction_detail', kwargs={'pk': transaction.pk}))
        self.assertContains(response, 'Allergy Review')
        self.assertContains(response, 'Synthetic workflow explanation')
        self.assertNotContains(response, 'Edited after completion')

    def test_cart_medicine_change_invalidates_all_check_types(self):
        transaction, _ = self.make_consultation_transaction()
        self.set_session_cart(transaction, [self.medicines[0]])
        run_clinical_review(transaction, [self.medicines[0].pk])
        session = self.client.session
        session[f'cart_{transaction.pk}'] = self.cart([self.medicines[0]])
        session.save()
        self.client.post(reverse('dispensing:add_to_cart', kwargs={'pk': transaction.pk}), {
            'medicine_id': self.medicines[1].pk,
            'quantity': 1,
        })
        self.assertFalse(ClinicalCheckResult.objects.filter(transaction=transaction).exists())
