from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Pharmacy
from dispensing.models import DispensingTransaction, TransactionStatusChoices, TransactionTypeChoices
from medicines.models import Medicine, MedicineCategory

from .models import (
    Allergen, AllergyRule, ClinicalCheckStatus, DosageRule, DrugInteractionRule,
    RuleLifecycleStatus,
)
from .services import check_drug_interactions

User = get_user_model()


class TenantKnowledgeManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pharmacy_a = Pharmacy.objects.create(name='Knowledge Pharmacy A')
        cls.pharmacy_b = Pharmacy.objects.create(name='Knowledge Pharmacy B')
        cls.admin_a = User.objects.create_user(
            username='knowledge-admin-a', password='pw', full_name='Admin A',
            role='ADMIN', pharmacy=cls.pharmacy_a,
        )
        cls.reviewer_a = User.objects.create_user(
            username='knowledge-reviewer-a', password='pw', full_name='Reviewer A',
            role='ADMIN', pharmacy=cls.pharmacy_a,
        )
        cls.staff_a = User.objects.create_user(
            username='knowledge-staff-a', password='pw', full_name='Staff A',
            role='PHARMACY_STAFF', pharmacy=cls.pharmacy_a,
        )
        cls.admin_b = User.objects.create_user(
            username='knowledge-admin-b', password='pw', full_name='Admin B',
            role='ADMIN', pharmacy=cls.pharmacy_b,
        )
        category_a = MedicineCategory.objects.create(pharmacy=cls.pharmacy_a, name='Knowledge A')
        category_b = MedicineCategory.objects.create(pharmacy=cls.pharmacy_b, name='Knowledge B')
        cls.medicine_a1 = Medicine.objects.create(
            pharmacy=cls.pharmacy_a, category=category_a, generic_name='Tenant Alpha',
            strength='10mg', dosage_form='TABLET', unit='tablet',
        )
        cls.medicine_a2 = Medicine.objects.create(
            pharmacy=cls.pharmacy_a, category=category_a, generic_name='Tenant Beta',
            strength='20mg', dosage_form='TABLET', unit='tablet',
        )
        cls.medicine_b = Medicine.objects.create(
            pharmacy=cls.pharmacy_b, category=category_b, generic_name='Foreign Medicine',
            strength='30mg', dosage_form='TABLET', unit='tablet',
        )
        cls.allergen_a = Allergen.objects.create(pharmacy=cls.pharmacy_a, name='Tenant Pollen')
        cls.allergen_b = Allergen.objects.create(pharmacy=cls.pharmacy_b, name='Foreign Allergen')

    def common_rule_data(self):
        return {
            'severity': 'HIGH', 'description': 'Tenant rule description',
            'explanation': 'Tenant rule explanation', 'recommendation': 'Tenant recommendation',
            'source_reference': 'TENANT-SOURCE-001', 'source_title': '', 'source_version': '',
            'source_date': '', 'source_url': '', 'effective_from': '', 'effective_to': '',
            'next_review_date': '', 'change_reason': 'Initial tenant configuration',
        }

    def interaction_data(self, **overrides):
        data = self.common_rule_data() | {
            'medicine_a': self.medicine_a2.pk, 'medicine_b': self.medicine_a1.pk,
        }
        data.update(overrides)
        return data

    def login_admin(self):
        self.client.force_login(self.admin_a)

    def test_admin_can_open_scoped_management_and_staff_receives_403(self):
        foreign = DrugInteractionRule.objects.create(
            pharmacy=self.pharmacy_b, medicine_a=self.medicine_b,
            medicine_b=Medicine.objects.create(
                pharmacy=self.pharmacy_b, category=self.medicine_b.category,
                generic_name='Foreign Pair', strength='1mg', dosage_form='TABLET', unit='tablet',
            ), severity='HIGH', description='Foreign rule', explanation='Foreign',
            recommendation='Foreign', source_reference='FOREIGN', created_by=self.admin_b,
        )
        self.login_admin()
        response = self.client.get(reverse('clinical:rule_management'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, foreign.description)
        self.client.force_login(self.staff_a)
        self.assertEqual(self.client.get(reverse('clinical:rule_management')).status_code, 403)

    def test_admin_creates_and_edits_tenant_allergen_with_friendly_duplicate(self):
        self.login_admin()
        response = self.client.post(reverse('clinical:allergen_create'), {
            'name': 'Latex', 'description': 'Natural rubber latex', 'is_active': 'on',
        })
        self.assertRedirects(response, reverse('clinical:rule_management'))
        allergen = Allergen.objects.get(name='Latex')
        self.assertEqual(allergen.pharmacy, self.pharmacy_a)
        duplicate = self.client.post(reverse('clinical:allergen_create'), {
            'name': 'latex', 'description': '', 'is_active': 'on',
        })
        self.assertContains(duplicate, 'already exists for this pharmacy')

    def test_admin_creates_all_rule_types_for_current_pharmacy(self):
        self.login_admin()
        response = self.client.post(
            reverse('clinical:rule_create', args=['interaction']), self.interaction_data(),
        )
        self.assertRedirects(response, reverse('clinical:rule_management'))
        allergy = self.common_rule_data() | {
            'medicine': self.medicine_a1.pk, 'allergen': self.allergen_a.pk,
        }
        self.assertRedirects(
            self.client.post(reverse('clinical:rule_create', args=['allergy']), allergy),
            reverse('clinical:rule_management'),
        )
        dosage = self.common_rule_data() | {
            'medicine': self.medicine_a1.pk, 'dose_unit': 'MG', 'min_single_dose': '5',
            'max_single_dose': '20', 'max_daily_dose': '60',
            'min_frequency_per_day': '1', 'max_frequency_per_day': '3',
            'max_duration_days': '7', 'min_age': '', 'max_age': '',
            'min_weight': '', 'max_weight': '',
        }
        self.assertRedirects(
            self.client.post(reverse('clinical:rule_create', args=['dosage']), dosage),
            reverse('clinical:rule_management'),
        )
        for model in (DrugInteractionRule, AllergyRule, DosageRule):
            rule = model.objects.get()
            self.assertEqual(rule.pharmacy, self.pharmacy_a)
            self.assertEqual(rule.status, RuleLifecycleStatus.DRAFT)
            self.assertEqual(rule.created_by, self.admin_a)

    def test_foreign_choices_are_hidden_and_forged_ids_rejected(self):
        self.login_admin()
        interaction_url = reverse('clinical:rule_create', args=['interaction'])
        response = self.client.get(interaction_url)
        self.assertNotContains(response, self.medicine_b.generic_name)
        forged = self.client.post(
            interaction_url, self.interaction_data(medicine_b=self.medicine_b.pk),
        )
        self.assertContains(forged, 'Select a valid choice')
        allergy_url = reverse('clinical:rule_create', args=['allergy'])
        allergy = self.common_rule_data() | {
            'medicine': self.medicine_a1.pk, 'allergen': self.allergen_b.pk,
        }
        forged_allergen = self.client.post(allergy_url, allergy)
        self.assertContains(forged_allergen, 'Select a valid choice')

    def test_interaction_validation_is_friendly_and_order_is_canonical(self):
        self.login_admin()
        url = reverse('clinical:rule_create', args=['interaction'])
        same = self.client.post(url, self.interaction_data(medicine_b=self.medicine_a2.pk))
        self.assertContains(same, 'Select two different medicines.')
        self.client.post(url, self.interaction_data())
        rule = DrugInteractionRule.objects.get()
        self.assertLess(rule.medicine_a_id, rule.medicine_b_id)
        duplicate = self.client.post(url, self.interaction_data())
        self.assertContains(duplicate, 'matching interaction rule version already exists')

    def test_cross_tenant_allergen_and_rule_urls_are_denied(self):
        foreign_rule = DrugInteractionRule.objects.create(
            pharmacy=self.pharmacy_b, medicine_a=self.medicine_b,
            medicine_b=Medicine.objects.create(
                pharmacy=self.pharmacy_b, category=self.medicine_b.category,
                generic_name='Foreign Second', strength='2mg', dosage_form='TABLET', unit='tablet',
            ), severity='HIGH', description='Foreign', explanation='Foreign',
            recommendation='Foreign', source_reference='FOREIGN', created_by=self.admin_b,
        )
        self.login_admin()
        self.assertEqual(self.client.get(reverse('clinical:allergen_update', args=[self.allergen_b.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse(
            'clinical:rule_lifecycle_action', args=['interaction', foreign_rule.pk, 'submit'],
        )).status_code, 404)

    def test_lifecycle_uses_services_and_active_rule_enters_checks(self):
        self.login_admin()
        self.client.post(reverse('clinical:rule_create', args=['interaction']), self.interaction_data())
        rule = DrugInteractionRule.objects.get()
        transaction = DispensingTransaction.objects.create(
            pharmacy=self.pharmacy_a, user=self.staff_a,
            transaction_type=TransactionTypeChoices.DIRECT_SALE,
            status=TransactionStatusChoices.DRAFT,
        )
        ids = [self.medicine_a1.pk, self.medicine_a2.pk]
        self.assertEqual(check_drug_interactions(transaction, ids)['status'], ClinicalCheckStatus.PASSED)
        self.client.post(reverse('clinical:rule_lifecycle_action', args=['interaction', rule.pk, 'submit']))
        rule.refresh_from_db()
        self.assertEqual(rule.status, RuleLifecycleStatus.UNDER_REVIEW)
        self.client.force_login(self.reviewer_a)
        self.client.post(reverse('clinical:rule_lifecycle_action', args=['interaction', rule.pk, 'approve']))
        self.client.post(reverse('clinical:rule_lifecycle_action', args=['interaction', rule.pk, 'activate']))
        rule.refresh_from_db()
        self.assertEqual(rule.status, RuleLifecycleStatus.ACTIVE)
        self.assertEqual(check_drug_interactions(transaction, ids)['status'], ClinicalCheckStatus.WARNING)

    def test_creator_cannot_self_approve_through_ui(self):
        rule = DrugInteractionRule.objects.create(
            pharmacy=self.pharmacy_a, medicine_a=self.medicine_a1, medicine_b=self.medicine_a2,
            severity='HIGH', description='Self approval test', explanation='Test',
            recommendation='Test', source_reference='TEST', created_by=self.admin_a,
            status=RuleLifecycleStatus.UNDER_REVIEW,
        )
        self.login_admin()
        response = self.client.post(
            reverse('clinical:rule_lifecycle_action', args=['interaction', rule.pk, 'approve']),
            follow=True,
        )
        self.assertContains(response, 'cannot approve a rule that you created')
        rule.refresh_from_db()
        self.assertEqual(rule.status, RuleLifecycleStatus.UNDER_REVIEW)

    def test_superuser_platform_admin_visibility_remains_available(self):
        superuser = User.objects.create_superuser(
            username='knowledge-platform-admin', password='pw', full_name='Platform Admin',
        )
        self.client.force_login(superuser)
        response = self.client.get(reverse('admin:clinical_druginteractionrule_changelist'))
        self.assertEqual(response.status_code, 200)

