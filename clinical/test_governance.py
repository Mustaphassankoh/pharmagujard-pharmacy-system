from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from dispensing.models import DispensingTransaction, TransactionStatusChoices, TransactionTypeChoices
from inventory.models import MedicineBatch
from medicines.models import Medicine, MedicineCategory

from .governance import (
    activate_rule, approve_rule, create_rule, create_rule_version, effective_rules,
    retire_rule, submit_rule_for_review,
)
from .models import (
    AllergyRule, Allergen, ClinicalAlert, ClinicalRuleAudit, DosageRule,
    DrugInteractionRule, RuleAuditAction, RuleLifecycleStatus, SeverityChoices,
)
from .services import check_allergies, check_drug_interactions
from .dosage import check_dosage

User = get_user_model()


class ClinicalRuleGovernanceTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username='governance_creator', password='pw', role='ADMIN')
        self.approver = User.objects.create_user(username='governance_approver', password='pw', role='ADMIN')
        self.staff = User.objects.create_user(username='governance_staff', password='pw', role='PHARMACY_STAFF')
        category = MedicineCategory.objects.create(name='Synthetic Governance Medicines')
        self.a = Medicine.objects.create(category=category, generic_name='Governance A', strength='1', dosage_form='TABLET', unit='tablet')
        self.b = Medicine.objects.create(category=category, generic_name='Governance B', strength='1', dosage_form='TABLET', unit='tablet')
        self.allergen = Allergen.objects.create(name='Synthetic Governance Allergen')
        for index, medicine in enumerate((self.a, self.b), 1):
            MedicineBatch.objects.create(
                medicine=medicine, batch_number=f'GOV-{index}', quantity_received=10, quantity_remaining=10,
                cost_price='1', selling_price='2', date_received=date.today(), expiry_date=date.today() + timedelta(days=30),
            )

    def interaction_rule(self, **changes):
        values = dict(
            medicine_a=self.a, medicine_b=self.b, severity=SeverityChoices.HIGH,
            description='Synthetic governed interaction', explanation='Synthetic explanation',
            recommendation='Synthetic recommendation', source_reference='SYNTHETIC-GOV-SOURCE',
            created_by=self.creator,
        )
        values.update(changes)
        return DrugInteractionRule.objects.create(**values)

    def activate(self, rule):
        submit_rule_for_review(rule, self.creator, 'Ready for independent review.')
        approve_rule(rule, self.approver, 'Verified synthetic rule.')
        return activate_rule(rule, self.approver, 'Effective for synthetic tests.')

    def transaction(self, transaction_type=TransactionTypeChoices.DIRECT_SALE):
        return DispensingTransaction.objects.create(user=self.staff, transaction_type=transaction_type, status=TransactionStatusChoices.DRAFT)

    def test_new_rule_defaults_to_draft_and_version_one(self):
        rule = self.interaction_rule()
        self.assertEqual(rule.status, RuleLifecycleStatus.DRAFT)
        self.assertEqual(rule.version, 1)
        self.assertFalse(rule.is_currently_usable)

    def test_create_service_records_creator_and_audit(self):
        rule = create_rule(
            DrugInteractionRule, self.creator, 'Initial controlled creation.',
            medicine_a=self.a, medicine_b=self.b, severity='HIGH', description='Synthetic',
            explanation='Synthetic', recommendation='Synthetic', source_reference='SYNTHETIC',
        )
        audit = ClinicalRuleAudit.objects.get(rule_type='DrugInteractionRule', rule_object_id=rule.pk)
        self.assertEqual(rule.created_by, self.creator)
        self.assertEqual(audit.action, RuleAuditAction.CREATED)

    def test_lifecycle_states_before_active_are_not_eligible(self):
        rule = self.interaction_rule()
        self.assertFalse(effective_rules(DrugInteractionRule.objects.filter(pk=rule.pk)).exists())
        submit_rule_for_review(rule, self.creator)
        self.assertFalse(effective_rules(DrugInteractionRule.objects.filter(pk=rule.pk)).exists())
        approve_rule(rule, self.approver)
        self.assertFalse(effective_rules(DrugInteractionRule.objects.filter(pk=rule.pk)).exists())
        activate_rule(rule, self.approver)
        self.assertTrue(effective_rules(DrugInteractionRule.objects.filter(pk=rule.pk)).exists())

    def test_invalid_transition_and_self_approval_rejected(self):
        rule = self.interaction_rule()
        with self.assertRaises(ValidationError):
            activate_rule(rule, self.approver)
        submit_rule_for_review(rule, self.creator)
        with self.assertRaises(ValidationError):
            approve_rule(rule, self.creator)

    def test_staff_cannot_transition_rules(self):
        rule = self.interaction_rule()
        with self.assertRaises(PermissionDenied):
            submit_rule_for_review(rule, self.staff)
        with self.assertRaises(PermissionDenied):
            retire_rule(rule, self.staff, 'Not authorized')

    def test_effective_date_window(self):
        future = self.activate(self.interaction_rule(effective_from=timezone.now() + timedelta(days=1)))
        self.assertFalse(effective_rules(DrugInteractionRule.objects.filter(pk=future.pk)).exists())
        active = self.activate(self.interaction_rule(version=2, effective_from=timezone.now() - timedelta(days=1), effective_to=timezone.now() + timedelta(days=1)))
        self.assertTrue(effective_rules(DrugInteractionRule.objects.filter(pk=active.pk)).exists())
        expired = self.activate(self.interaction_rule(version=3, effective_to=timezone.now() - timedelta(seconds=1)))
        self.assertFalse(effective_rules(DrugInteractionRule.objects.filter(pk=expired.pk)).exists())

    def test_invalid_effective_range_rejected(self):
        with self.assertRaises(ValidationError):
            self.interaction_rule(effective_from=timezone.now(), effective_to=timezone.now() - timedelta(days=1))

    def test_transitions_create_append_only_audit_history(self):
        rule = self.interaction_rule()
        self.activate(rule)
        retire_rule(rule, self.approver, 'Synthetic source retired.')
        actions = list(ClinicalRuleAudit.objects.filter(rule_object_id=rule.pk).values_list('action', flat=True))
        for action in (RuleAuditAction.SUBMITTED_FOR_REVIEW, RuleAuditAction.REVIEWED, RuleAuditAction.APPROVED, RuleAuditAction.ACTIVATED, RuleAuditAction.RETIRED):
            self.assertIn(action, actions)
        audit = ClinicalRuleAudit.objects.filter(rule_object_id=rule.pk).first()
        audit.change_reason = 'Tampered'
        with self.assertRaises(ValidationError):
            audit.save()
        with self.assertRaises(ValidationError):
            audit.delete()

    def test_active_clinical_fields_are_immutable(self):
        rule = self.activate(self.interaction_rule())
        rule.explanation = 'Attempted in-place clinical edit'
        with self.assertRaises(ValidationError):
            rule.save()

    def test_new_version_preserves_predecessor_and_activation_retires_it(self):
        old = self.activate(self.interaction_rule())
        new = create_rule_version(old, self.creator, 'Updated verified explanation.', {'explanation': 'Version two explanation'})
        self.assertEqual(new.version, 2)
        self.assertEqual(new.supersedes, old)
        self.assertEqual(new.status, RuleLifecycleStatus.DRAFT)
        self.assertTrue(DrugInteractionRule.objects.filter(pk=old.pk).exists())
        self.activate(new)
        old.refresh_from_db()
        self.assertEqual(old.status, RuleLifecycleStatus.RETIRED)
        self.assertFalse(old.is_active)

    def test_interaction_service_only_uses_active_effective_rule_and_snapshots_version(self):
        rule = self.interaction_rule()
        transaction = self.transaction()
        self.assertEqual(check_drug_interactions(transaction, [self.a.pk, self.b.pk])['alerts'], [])
        self.activate(rule)
        alert = check_drug_interactions(transaction, [self.a.pk, self.b.pk])['alerts'][0]
        self.assertEqual(alert.snapshot_details['rule_version'], 1)
        retire_rule(rule, self.approver, 'No longer current.')
        self.assertEqual(check_drug_interactions(transaction, [self.a.pk, self.b.pk])['alerts'], [])

    def test_allergy_and_dosage_services_respect_governance(self):
        allergy = AllergyRule.objects.create(
            medicine=self.a, allergen=self.allergen, severity='HIGH', description='Synthetic allergy',
            explanation='Synthetic', recommendation='Synthetic', source_reference='SYNTHETIC', created_by=self.creator,
        )
        dosage = DosageRule.objects.create(
            medicine=self.a, dose_unit='MG', max_single_dose=100, severity='HIGH', description='Synthetic dosage',
            explanation='Synthetic', recommendation='Synthetic', source_reference='SYNTHETIC', created_by=self.creator,
        )
        transaction = self.transaction(TransactionTypeChoices.CONSULTATION)
        from dispensing.models import Consultation
        consultation = Consultation.objects.create(transaction=transaction, symptoms='Synthetic')
        consultation.structured_allergies.add(self.allergen)
        self.assertEqual(check_allergies(transaction, [self.a.pk])['alerts'], [])
        self.assertEqual(check_dosage(transaction, {str(self.a.pk): {'medicine_id': self.a.pk, 'dose_amount': '200', 'dose_unit': 'MG'}})['alerts'], [])
        self.activate(allergy)
        self.activate(dosage)
        self.assertEqual(len(check_allergies(transaction, [self.a.pk])['alerts']), 1)
        dosage_alert = check_dosage(transaction, {str(self.a.pk): {'medicine_id': self.a.pk, 'dose_amount': '200', 'dose_unit': 'MG'}})['alerts'][0]
        self.assertEqual(dosage_alert.snapshot_details['rule_version'], 1)

    def test_retirement_does_not_mutate_existing_alert_snapshot(self):
        rule = self.activate(self.interaction_rule())
        transaction = self.transaction()
        alert = check_drug_interactions(transaction, [self.a.pk, self.b.pk])['alerts'][0]
        original = (alert.explanation, alert.source_reference, alert.snapshot_details.copy())
        retire_rule(rule, self.approver, 'Superseded source.')
        alert.refresh_from_db()
        self.assertEqual((alert.explanation, alert.source_reference, alert.snapshot_details), original)
