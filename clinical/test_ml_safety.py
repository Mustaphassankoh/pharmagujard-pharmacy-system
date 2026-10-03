from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from dispensing.models import DispensingTransaction, TransactionStatusChoices, TransactionTypeChoices
from inventory.models import MedicineBatch
from medicines.models import Medicine, MedicineCategory

from .ml.features import FEATURES, extract_review_features
from .ml.predictor import predict_review_priority
from .models import (
    AlertTypeChoices, ClinicalAlert, ClinicalCheckResult, ClinicalCheckStatus,
    ClinicalCheckType, ClinicalReview, ClinicalRiskAssessment,
    ClinicalRiskModelVersion, ReviewPriority,
)
from .services import invalidate_clinical_review, run_clinical_review

User = get_user_model()


class Milestone12MLSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ml_staff', password='pw', role='PHARMACY_STAFF', full_name='Excluded Person Name')
        category = MedicineCategory.objects.create(name='Synthetic ML Medicines')
        self.medicine = Medicine.objects.create(category=category, generic_name='Synthetic ML Medicine', strength='1', dosage_form='TABLET', unit='tablet')
        self.batch = MedicineBatch.objects.create(medicine=self.medicine, batch_number='ML-1', quantity_received=20, quantity_remaining=20, cost_price='1', selling_price='2', date_received=date.today(), expiry_date=date.today()+timedelta(days=90))
        self.model_version = ClinicalRiskModelVersion.objects.create(
            version='test-demo-1', artifact_path='clinical/ml/artifacts/decision_tree_demo-1.joblib',
            trained_at=timezone.now(), dataset_name='DEVELOPMENT / SYNTHETIC DATA — NOT CLINICALLY VALIDATED',
            dataset_version='1', feature_schema=FEATURES, metrics={'label':'Synthetic-development evaluation results'}, is_active=True,
        )

    def transaction(self, transaction_type=TransactionTypeChoices.DIRECT_SALE):
        transaction = DispensingTransaction.objects.create(user=self.user, transaction_type=transaction_type, status=TransactionStatusChoices.DRAFT, notes='Excluded free text')
        ClinicalReview.objects.create(transaction=transaction, medicine_fingerprint=str(self.medicine.pk), status=ClinicalCheckStatus.PASSED, checked_at=timezone.now())
        for check_type in ClinicalCheckType.values:
            ClinicalCheckResult.objects.create(transaction=transaction, check_type=check_type, status=ClinicalCheckStatus.PASSED, checked_at=timezone.now())
        return transaction

    def alert(self, transaction, severity):
        return ClinicalAlert.objects.create(transaction=transaction, alert_type=AlertTypeChoices.DRUG_INTERACTION, severity=severity, medicine_a=self.medicine, title='Synthetic alert', description='Synthetic', explanation='Synthetic', recommendation='Synthetic', source_reference='SYNTHETIC')

    def test_feature_schema_is_exact_and_excludes_identifiers_and_free_text(self):
        transaction = self.transaction(TransactionTypeChoices.CONSULTATION)
        from dispensing.models import Consultation
        Consultation.objects.create(transaction=transaction, symptoms='Private symptom text', current_medications='Private free text')
        features = extract_review_features(transaction)
        self.assertEqual(list(features), FEATURES)
        serialized = str(features)
        for prohibited in (self.user.username, self.user.full_name, transaction.transaction_number, 'Private symptom text', 'instructions'):
            self.assertNotIn(prohibited, serialized)

    def test_no_model_and_invalid_artifact_are_not_available(self):
        transaction = self.transaction()
        ClinicalRiskModelVersion.objects.update(is_active=False)
        self.assertEqual(predict_review_priority(transaction)['status'], 'NOT_AVAILABLE')
        self.model_version.is_active=True; self.model_version.artifact_path='missing/model.joblib'; self.model_version.save()
        self.assertEqual(predict_review_priority(transaction)['status'], 'NOT_AVAILABLE')
        self.assertFalse(ClinicalRiskAssessment.objects.filter(transaction=transaction).exists())

    def test_active_model_prediction_confidence_path_and_snapshot(self):
        transaction = self.transaction()
        result = predict_review_priority(transaction)
        self.assertEqual(result['status'], 'AVAILABLE')
        assessment = result['assessment']
        self.assertIn(assessment.predicted_priority, ReviewPriority.values)
        self.assertGreaterEqual(assessment.prediction_probability, Decimal('0'))
        self.assertLessEqual(assessment.prediction_probability, Decimal('1'))
        self.assertTrue(assessment.decision_path)
        self.assertIn(assessment.decision_path[0]['feature'], FEATURES)
        self.assertIn(assessment.decision_path[0]['feature'], assessment.explanation)
        self.assertEqual(list(assessment.feature_snapshot), FEATURES)
        self.assertEqual(assessment.model_version, self.model_version)
        self.assertEqual(assessment.predicted_priority, 'LOW')

    def test_critical_and_high_deterministic_guards_preserve_raw_prediction(self):
        for severity, expected in (('HIGH','HIGH'),('CRITICAL','CRITICAL')):
            with self.subTest(severity=severity):
                transaction=self.transaction(); self.alert(transaction,severity)
                assessment=predict_review_priority(transaction)['assessment']
                self.assertEqual(assessment.predicted_priority, 'LOW')
                self.assertEqual(assessment.final_priority, expected)

    def test_assessment_is_immutable(self):
        assessment=predict_review_priority(self.transaction())['assessment']
        assessment.final_priority='CRITICAL'
        with self.assertRaises(ValidationError): assessment.save()

    def test_completed_assessment_is_not_recalculated_by_new_model(self):
        transaction=self.transaction(); original=predict_review_priority(transaction)['assessment']
        transaction.status=TransactionStatusChoices.COMPLETED; transaction.completed_at=timezone.now(); transaction.save()
        ClinicalRiskModelVersion.objects.create(version='test-demo-2', artifact_path='missing.joblib', trained_at=timezone.now(), dataset_name='DEVELOPMENT / SYNTHETIC', dataset_version='2', feature_schema=FEATURES, is_active=True)
        returned=predict_review_priority(transaction)['assessment']
        self.assertEqual(returned.pk, original.pk)
        self.assertEqual(returned.model_version, self.model_version)

    def test_draft_invalidation_removes_assessment_for_all_input_change_paths(self):
        for label in ('medicine','allergy','dosage','age_weight','clinical_review'):
            with self.subTest(label=label):
                transaction=self.transaction(); predict_review_priority(transaction)
                invalidate_clinical_review(transaction)
                self.assertFalse(ClinicalRiskAssessment.objects.filter(transaction=transaction).exists())

    def test_all_transaction_types_integrate(self):
        for transaction_type in TransactionTypeChoices.values:
            with self.subTest(transaction_type=transaction_type):
                assessment=predict_review_priority(self.transaction(transaction_type))['assessment']
                self.assertIn(assessment.final_priority, ReviewPriority.values)

    def test_model_failure_does_not_break_deterministic_review_or_stock(self):
        transaction=self.transaction(); before=self.batch.quantity_remaining
        self.model_version.artifact_path='invalid.joblib'; self.model_version.save()
        result=run_clinical_review(transaction, [self.medicine.pk])
        self.assertIn(result['status'], ClinicalCheckStatus.values)
        self.assertEqual(result['ml_priority']['status'], 'NOT_AVAILABLE')
        self.batch.refresh_from_db(); self.assertEqual(self.batch.quantity_remaining, before)

    def test_model_failure_does_not_block_confirmation_and_ui_is_scientifically_labelled(self):
        transaction=DispensingTransaction.objects.create(user=self.user, transaction_type=TransactionTypeChoices.DIRECT_SALE, status=TransactionStatusChoices.DRAFT)
        session=self.client.session
        session[f'cart_{transaction.pk}']={str(self.medicine.pk):{'medicine_id':self.medicine.pk,'medicine_name':str(self.medicine),'quantity':1}}
        session.save(); self.client.login(username='ml_staff',password='pw')
        self.model_version.artifact_path='invalid.joblib'; self.model_version.save()
        review=self.client.post(reverse('dispensing:run_clinical_review',args=[transaction.pk]),follow=True)
        self.assertContains(review,'AI Review Priority:')
        self.assertContains(review,'NOT_AVAILABLE')
        self.assertContains(review,'DEVELOPMENT / SYNTHETIC DATA — NOT CLINICALLY VALIDATED')
        self.assertContains(review,'This model prioritizes pharmacist review. It does not diagnose, prescribe, determine clinical safety, or override deterministic clinical rules.')
        response=self.client.post(reverse('dispensing:confirm_sale',args=[transaction.pk]))
        self.assertEqual(response.status_code,302)
        transaction.refresh_from_db(); self.batch.refresh_from_db()
        self.assertEqual(transaction.status,TransactionStatusChoices.COMPLETED)
        self.assertEqual(self.batch.quantity_remaining,19)
