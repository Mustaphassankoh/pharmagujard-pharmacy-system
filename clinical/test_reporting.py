import csv
import io
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from medicines.models import Medicine, MedicineCategory

from .models import (
    AllergyRule, Allergen, ClinicalRuleAudit, DosageRule, DrugInteractionRule,
    RuleLifecycleStatus,
)
from .reporting import (
    effective_state, get_action_required_rules, get_all_rule_rows,
    get_filtered_rule_rows, get_governance_summary, get_rule_lineage,
    is_expiring_soon, review_state,
)

User = get_user_model()


class GovernanceReportingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='report_admin', password='pw', role='ADMIN')
        self.staff = User.objects.create_user(username='report_staff', password='pw', role='PHARMACY_STAFF')
        self.superuser = User.objects.create_superuser(username='report_root', password='pw')
        category = MedicineCategory.objects.create(name='Reporting Synthetic Medicines')
        self.a = Medicine.objects.create(category=category, generic_name='Report Alpha', brand_name='Alpha Brand', strength='1', dosage_form='TABLET', unit='tablet')
        self.b = Medicine.objects.create(category=category, generic_name='Report Beta', strength='1', dosage_form='TABLET', unit='tablet')
        self.allergen = Allergen.objects.create(name='Report Allergen')

    def governance_fields(self, status=RuleLifecycleStatus.DRAFT, **extra):
        values = {'status': status, 'created_by': self.admin}
        if status in (RuleLifecycleStatus.APPROVED, RuleLifecycleStatus.ACTIVE):
            values.update(approved_by=self.admin, approved_at=timezone.now())
        if status == RuleLifecycleStatus.RETIRED:
            values.update(is_active=False, retired_by=self.admin, retired_at=timezone.now())
        values.update(extra)
        return values

    def interaction(self, status=RuleLifecycleStatus.DRAFT, version=1, **extra):
        governance = self.governance_fields(status, version=version, **extra)
        return DrugInteractionRule.objects.create(
            medicine_a=self.a, medicine_b=self.b, severity='HIGH', description='Reporting interaction',
            explanation='Synthetic', recommendation='Synthetic', source_reference='REPORT-SOURCE-ALPHA',
            source_title='Synthetic Source Title', **governance,
        )

    def allergy(self, status=RuleLifecycleStatus.DRAFT, version=1, **extra):
        return AllergyRule.objects.create(
            medicine=self.a, allergen=self.allergen, severity='MODERATE', description='Reporting allergy',
            explanation='Synthetic', recommendation='Synthetic', source_reference='REPORT-ALLERGY',
            **self.governance_fields(status, version=version, **extra),
        )

    def dosage(self, status=RuleLifecycleStatus.DRAFT, version=1, **extra):
        return DosageRule.objects.create(
            medicine=self.a, dose_unit='MG', max_single_dose=100, severity='HIGH', description='Reporting dosage',
            explanation='Synthetic', recommendation='Synthetic', source_reference='REPORT-DOSAGE',
            **self.governance_fields(status, version=version, **extra),
        )

    def test_governance_pages_require_authentication_and_admin_role(self):
        urls = [
            reverse('clinical:governance_dashboard'), reverse('clinical:rule_report'),
            reverse('clinical:audit_report'), reverse('clinical:export_rules_csv'),
            reverse('clinical:export_audits_csv'),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        self.client.login(username='report_staff', password='pw')
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.login(username='report_admin', password='pw')
        self.assertEqual(self.client.get(urls[0]).status_code, 200)
        self.client.login(username='report_root', password='pw')
        self.assertEqual(self.client.get(urls[0]).status_code, 200)

    def test_summary_lifecycle_and_rule_type_counts(self):
        self.interaction(RuleLifecycleStatus.DRAFT)
        self.allergy(RuleLifecycleStatus.UNDER_REVIEW)
        self.dosage(RuleLifecycleStatus.APPROVED)
        summary = get_governance_summary()
        self.assertEqual(summary['total'], 3)
        self.assertEqual((summary['draft'], summary['under_review'], summary['approved']), (1, 1, 1))
        self.assertEqual(summary['by_type']['interaction']['total'], 1)
        self.assertEqual(summary['by_type']['allergy']['total'], 1)
        self.assertEqual(summary['by_type']['dosage']['total'], 1)

    def test_effective_future_expired_and_expiring_metrics(self):
        now = timezone.now()
        self.interaction(RuleLifecycleStatus.ACTIVE, effective_to=now + timedelta(days=10))
        self.allergy(RuleLifecycleStatus.ACTIVE, effective_from=now + timedelta(days=2))
        self.dosage(RuleLifecycleStatus.ACTIVE, effective_to=now - timedelta(seconds=1))
        summary = get_governance_summary(now=now)
        self.assertEqual(summary['currently_effective'], 1)
        self.assertEqual(summary['future'], 1)
        self.assertEqual(summary['expired'], 1)
        self.assertEqual(summary['expiring_soon'], 1)
        retired = self.interaction(RuleLifecycleStatus.RETIRED, version=2)
        self.assertEqual(effective_state(retired, now), 'retired')
        self.assertFalse(is_expiring_soon(retired, now))

    def test_review_date_states_and_action_queues(self):
        today = timezone.localdate()
        draft = self.interaction(next_review_date=None)
        under_review = self.allergy(RuleLifecycleStatus.UNDER_REVIEW, next_review_date=today - timedelta(days=1))
        approved = self.dosage(RuleLifecycleStatus.APPROVED, next_review_date=today + timedelta(days=10))
        rows = get_all_rule_rows()
        queues = get_action_required_rules(rows)
        self.assertEqual(review_state(draft, today), 'none')
        self.assertEqual(review_state(under_review, today), 'overdue')
        self.assertEqual(review_state(approved, today), 'due_soon')
        self.assertEqual(len(queues['draft']), 1)
        self.assertEqual(len(queues['under_review']), 1)
        self.assertEqual(len(queues['approved']), 1)
        self.assertEqual(len(queues['review_due']), 2)

    def test_rule_report_filters_and_search(self):
        self.interaction(RuleLifecycleStatus.ACTIVE)
        self.allergy(RuleLifecycleStatus.DRAFT)
        self.dosage(RuleLifecycleStatus.RETIRED)
        self.assertEqual(len(get_filtered_rule_rows({'rule_type': 'allergy'})), 1)
        self.assertEqual(len(get_filtered_rule_rows({'status': 'ACTIVE'})), 1)
        self.assertEqual(len(get_filtered_rule_rows({'severity': 'MODERATE'})), 1)
        self.assertEqual(len(get_filtered_rule_rows({'effective_state': 'retired'})), 1)
        self.assertEqual(len(get_filtered_rule_rows({'q': 'Report Alpha'})), 3)
        self.assertEqual(len(get_filtered_rule_rows({'q': 'REPORT-SOURCE-ALPHA'})), 1)

    def test_dashboard_displays_recent_audit_without_raw_snapshots(self):
        rule = self.interaction()
        audit = ClinicalRuleAudit.objects.create(
            rule_type='DrugInteractionRule', rule_object_id=rule.pk, rule_version=1,
            action='CREATED', changed_by=self.admin, change_reason='Dashboard audit reason',
            before_snapshot={'secret_detail': 'before'}, after_snapshot={'secret_detail': 'after'},
        )
        self.client.login(username='report_admin', password='pw')
        response = self.client.get(reverse('clinical:governance_dashboard'))
        self.assertContains(response, 'Dashboard audit reason')
        self.assertNotContains(response, 'secret_detail')
        detail = self.client.get(reverse('clinical:audit_detail', args=[audit.pk]))
        self.assertContains(detail, 'secret_detail')
        self.assertEqual(self.client.post(reverse('clinical:audit_detail', args=[audit.pk])).status_code, 405)

    def test_rule_history_displays_lineage_and_events(self):
        first = self.interaction(version=1)
        second = self.interaction(version=2, supersedes=first)
        ClinicalRuleAudit.objects.create(rule_type='DrugInteractionRule', rule_object_id=first.pk, rule_version=1, action='CREATED')
        lineage = get_rule_lineage(second)
        self.assertEqual([rule.version for rule in lineage], [1, 2])
        self.client.login(username='report_admin', password='pw')
        response = self.client.get(reverse('clinical:rule_history', args=['interaction', second.pk]))
        self.assertContains(response, 'Version Lineage')
        self.assertContains(response, 'Root version')
        self.assertContains(response, 'v2')

    def test_rule_csv_export_honors_filters(self):
        self.interaction(RuleLifecycleStatus.ACTIVE)
        self.allergy(RuleLifecycleStatus.DRAFT)
        self.client.login(username='report_admin', password='pw')
        response = self.client.get(reverse('clinical:export_rules_csv'), {'rule_type': 'allergy'})
        self.assertEqual(response['Content-Type'], 'text/csv')
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], 'Allergy')

    def test_audit_csv_export_is_readable_and_excludes_snapshots(self):
        rule = self.interaction()
        ClinicalRuleAudit.objects.create(
            rule_type='DrugInteractionRule', rule_object_id=rule.pk, rule_version=1,
            action='CREATED', changed_by=self.admin, change_reason='CSV reason',
            before_snapshot={'not_exported': True}, after_snapshot={'not_exported': True},
        )
        self.client.login(username='report_admin', password='pw')
        response = self.client.get(reverse('clinical:export_audits_csv'))
        content = response.content.decode()
        self.assertIn('CSV reason', content)
        self.assertNotIn('not_exported', content)

    def test_rule_report_paginates(self):
        for version in range(1, 27):
            self.interaction(version=version)
        self.client.login(username='report_admin', password='pw')
        response = self.client.get(reverse('clinical:rule_report'))
        self.assertEqual(len(response.context['page_obj']), 25)
        self.assertEqual(response.context['page_obj'].paginator.num_pages, 2)

    def test_reporting_is_read_only(self):
        rule = self.interaction()
        self.client.login(username='report_admin', password='pw')
        self.client.get(reverse('clinical:governance_dashboard'))
        self.client.get(reverse('clinical:rule_report'))
        rule.refresh_from_db()
        self.assertEqual(rule.status, RuleLifecycleStatus.DRAFT)
        self.assertEqual(DrugInteractionRule.objects.count(), 1)
