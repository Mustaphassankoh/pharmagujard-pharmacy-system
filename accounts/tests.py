from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from clinical.models import (
    AllergyRule,
    ClinicalRiskAssessment,
    ClinicalRiskModelVersion,
    ClinicalRuleAudit,
    DosageRule,
    DrugInteractionRule,
)
from dispensing.models import DispensingTransaction
from inventory.models import MedicineBatch
from medicines.models import Medicine

from .models import User


class DeploymentReadinessTests(SimpleTestCase):
    def test_health_check_exposes_only_liveness(self):
        response = self.client.get(reverse('health_check'))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'ok'})

    def test_branded_error_handlers_hide_internal_details(self):
        from pharmacy_system.views import error_400, error_403, error_404, error_500

        request = RequestFactory().get('/synthetic-error/')
        for handler, status in (
            (error_400, 400),
            (error_403, 403),
            (error_404, 404),
            (error_500, 500),
        ):
            with self.subTest(status=status):
                response = handler(request)
                self.assertEqual(response.status_code, status)
                self.assertContains(response, 'PharmaGuard', status_code=status)
                self.assertNotContains(response, 'SECRET_KEY', status_code=status)

    def test_ml_artifact_paths_are_cross_platform_and_project_bound(self):
        from clinical.ml.predictor import resolve_artifact_path

        artifact = resolve_artifact_path(
            r'clinical\ml\artifacts\decision_tree_development-synthetic-1.joblib'
        )
        self.assertTrue(artifact.is_file())
        with self.assertRaises(ValueError):
            resolve_artifact_path('../outside-project.joblib')


class SidebarLayoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='sidebar-user', password='pw', full_name='Sidebar User', role='PHARMACY_STAFF'
        )
        self.client.force_login(self.user)

    def test_sign_out_is_in_the_sidebar_footer(self):
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'class="sidebar-footer"', html=False)
        self.assertContains(response, '>Sign Out<', html=False)
        self.assertContains(response, 'class="sidebar-logout-form"', html=False)
        footer = response.content.decode().split('<div class="sidebar-footer">', 1)[1].split('</div>', 1)[0]
        self.assertNotIn('sidebar-user', footer)
        self.assertNotIn('Sidebar User', footer)
        self.assertNotIn('Pharmacy Staff', footer)
        for navigation_label in ('Dashboard', 'Medicines', 'Inventory', 'Consultation', 'Transactions'):
            self.assertNotIn(navigation_label, footer)


class AdminBrandingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username='admin-ui-test',
            email='admin-ui@example.com',
            password='test-password',
            full_name='Admin UI Test',
            role='ADMIN',
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_admin_branding_and_stylesheet_are_present(self):
        response = self.client.get(reverse('admin:index'))

        self.assertContains(response, 'PharmaGuard Administration')
        self.assertContains(response, 'System Administration')
        self.assertContains(response, 'admin/css/pharmaguard_admin.css')
        self.assertEqual(admin.site.site_title, 'PharmaGuard Admin')

    def test_admin_login_is_branded(self):
        self.client.logout()
        response = self.client.get(reverse('admin:login'))

        self.assertContains(response, 'PharmaGuard Administration')
        self.assertContains(
            response,
            'Intelligent Pharmacy Management &amp; Clinical Decision Support',
        )
        self.assertContains(response, 'admin/css/pharmaguard_admin.css')

    def test_representative_admin_pages_render(self):
        urls = (
            reverse('admin:accounts_user_changelist'),
            reverse('admin:accounts_user_change', args=(self.admin_user.pk,)),
            reverse('admin:medicines_medicine_changelist'),
            reverse('admin:inventory_medicinebatch_changelist'),
            reverse('admin:clinical_druginteractionrule_changelist'),
            reverse('admin:clinical_allergyrule_changelist'),
            reverse('admin:clinical_dosagerule_changelist'),
            reverse('admin:clinical_clinicalruleaudit_changelist'),
            reverse('admin:clinical_clinicalriskmodelversion_changelist'),
            reverse('admin:clinical_clinicalriskassessment_changelist'),
            reverse('admin:dispensing_dispensingtransaction_changelist'),
        )

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'admin/css/pharmaguard_admin.css')

    def test_safety_sensitive_admin_permissions_are_unchanged(self):
        request = type('Request', (), {'user': self.admin_user})()
        read_only_models = (ClinicalRuleAudit, ClinicalRiskAssessment, DispensingTransaction)

        for model in read_only_models:
            model_admin = admin.site._registry[model]
            with self.subTest(model=model.__name__):
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))

        for model in (Medicine, MedicineBatch, DrugInteractionRule, AllergyRule, DosageRule, ClinicalRiskModelVersion):
            self.assertIn(model, admin.site._registry)

    def test_editable_admin_forms_are_grouped_and_explain_required_fields(self):
        expected_sections = {
            'admin:clinical_druginteractionrule_add': ('Rule Definition', 'Clinical Information', 'Source Information', 'Governance'),
            'admin:clinical_allergyrule_add': ('Rule Definition', 'Clinical Information', 'Source Information', 'Governance'),
            'admin:clinical_dosagerule_add': ('Rule Definition', 'Dose Limits', 'Patient Context', 'Governance'),
            'admin:clinical_allergen_add': ('Allergen Details',),
            'admin:clinical_clinicalriskmodelversion_add': ('Model Identity', 'Training Data', 'Technical Evidence'),
            'admin:medicines_medicine_add': ('Medicine Identity', 'Formulation', 'Inventory Settings'),
            'admin:inventory_medicinebatch_add': ('Batch Identity', 'Stock', 'Pricing', 'Dates'),
        }

        for url_name, sections in expected_sections.items():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Required fields')
                for section in sections:
                    self.assertContains(response, section)

    def test_admin_rule_forms_use_compact_textareas_and_help_text(self):
        response = self.client.get(reverse('admin:clinical_druginteractionrule_add'))

        self.assertContains(response, 'compact-textarea')
        self.assertContains(response, 'Enter the guideline, document, or reference supporting this rule.')
        self.assertContains(response, 'The date and time when this rule becomes usable in clinical checks.')

    def test_related_select_widgets_keep_their_action_controls_grouped(self):
        for url_name in (
            'admin:clinical_druginteractionrule_add',
            'admin:clinical_allergyrule_add',
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertContains(response, 'related-widget-wrapper')
                self.assertContains(response, 'related-widget-wrapper-link')
