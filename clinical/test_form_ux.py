from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from medicines.models import Medicine, MedicineCategory

from .forms import AllergyRuleAdminForm, DosageRuleAdminForm, DrugInteractionRuleAdminForm
from .governance import approve_rule, submit_rule_for_review
from .models import Allergen, AllergyRule, DrugInteractionRule, SeverityChoices


class FriendlyClinicalFormValidationTests(TestCase):
    def setUp(self):
        category = MedicineCategory.objects.create(name='Form UX Medicines')
        self.a = Medicine.objects.create(
            category=category, generic_name='UX Alpha', strength='1 mg',
            dosage_form='TABLET', unit='tablet',
        )
        self.b = Medicine.objects.create(
            category=category, generic_name='UX Beta', strength='1 mg',
            dosage_form='TABLET', unit='tablet',
        )
        self.allergen = Allergen.objects.create(name='UX Allergen')
        self.creator = get_user_model().objects.create_user(
            username='ux-creator', password='pw', role='ADMIN'
        )

    def interaction_data(self, **changes):
        data = {
            'medicine_a': self.a.pk, 'medicine_b': self.b.pk,
            'severity': SeverityChoices.HIGH, 'description': 'Interaction summary',
            'explanation': 'Readable explanation', 'recommendation': 'Readable recommendation',
            'source_reference': 'UX-GUIDELINE', 'version': 1, 'status': 'DRAFT',
            'change_reason': '', 'is_active': True,
        }
        data.update(changes)
        return data

    def test_same_medicine_error_is_field_specific_and_readable(self):
        form = DrugInteractionRuleAdminForm(data=self.interaction_data(medicine_b=self.a.pk))
        self.assertFalse(form.is_valid())
        self.assertIn('Medicine A and Medicine B cannot be the same medicine.', form.errors['medicine_b'])

    def test_reversed_pair_is_normalized_without_constraint_error(self):
        form = DrugInteractionRuleAdminForm(
            data=self.interaction_data(medicine_a=self.b.pk, medicine_b=self.a.pk)
        )
        self.assertTrue(form.is_valid(), form.errors)
        rule = form.save()
        self.assertLess(rule.medicine_a_id, rule.medicine_b_id)
        self.assertNotIn('canonical_interaction_pair_order', str(form.errors))

    def test_duplicate_interaction_has_friendly_non_field_error(self):
        DrugInteractionRule.objects.create(**{
            'medicine_a': self.a, 'medicine_b': self.b, 'severity': SeverityChoices.HIGH,
            'description': 'Existing', 'explanation': 'Existing', 'recommendation': 'Existing',
            'source_reference': 'SOURCE',
        })
        form = DrugInteractionRuleAdminForm(data=self.interaction_data())
        self.assertFalse(form.is_valid())
        errors = str(form.errors)
        self.assertIn('A drug interaction rule already exists for these two medicines in this version.', errors)
        self.assertNotIn('unique_versioned_interaction_pair', errors)
        self.assertNotIn('IntegrityError', errors)

    def test_duplicate_allergy_rule_has_friendly_error(self):
        common = dict(
            medicine=self.a, allergen=self.allergen, severity='HIGH', description='Existing',
            explanation='Existing', recommendation='Existing', source_reference='SOURCE',
        )
        AllergyRule.objects.create(**common)
        form = AllergyRuleAdminForm(data={
            'medicine': self.a.pk, 'allergen': self.allergen.pk, 'severity': 'HIGH',
            'description': 'New', 'explanation': 'New', 'recommendation': 'New',
            'source_reference': 'SOURCE', 'version': 1, 'status': 'DRAFT', 'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn(
            'An allergy rule already exists for this medicine and allergen in this version.',
            str(form.errors),
        )

    def test_effective_date_dosage_range_and_source_messages_are_readable(self):
        now = timezone.now()
        interaction = DrugInteractionRuleAdminForm(data=self.interaction_data(
            effective_from=(now + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S'),
            effective_to=now.strftime('%Y-%m-%d %H:%M:%S'),
        ))
        self.assertFalse(interaction.is_valid())
        self.assertEqual(
            interaction.errors.as_data()['effective_to'][0].message,
            "'Effective from' must be earlier than 'Effective to'.",
        )

        dosage = DosageRuleAdminForm(data={
            'medicine': self.a.pk, 'dose_unit': 'MG', 'min_single_dose': '10',
            'max_single_dose': '5', 'severity': 'HIGH', 'description': 'Dose',
            'explanation': 'Explain', 'recommendation': 'Recommend', 'source_reference': '',
            'version': 1, 'status': 'DRAFT', 'is_active': True,
        })
        self.assertFalse(dosage.is_valid())
        self.assertIn('Minimum single dose cannot be greater than maximum single dose.', str(dosage.errors))
        self.assertIn('A source reference is required before this rule can be activated.', str(dosage.errors))

    def test_self_approval_message_is_readable(self):
        rule = DrugInteractionRule.objects.create(
            medicine_a=self.a, medicine_b=self.b, severity='HIGH', description='Rule',
            explanation='Explain', recommendation='Recommend', source_reference='SOURCE',
            created_by=self.creator,
        )
        submit_rule_for_review(rule, self.creator)
        with self.assertRaisesMessage(
            ValidationError, 'You cannot approve a rule that you created yourself.'
        ):
            approve_rule(rule, self.creator)

    def test_database_constraint_remains_a_final_safety_net(self):
        values = dict(
            medicine_a=self.a, medicine_b=self.b, severity='HIGH', description='Rule',
            explanation='Explain', recommendation='Recommend', source_reference='SOURCE', version=1,
        )
        DrugInteractionRule.objects.bulk_create([DrugInteractionRule(**values)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            DrugInteractionRule.objects.bulk_create([DrugInteractionRule(**values)])
