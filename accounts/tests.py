from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from datetime import timedelta
from decimal import Decimal

from clinical.models import (
    AllergyRule,
    ClinicalRiskAssessment,
    ClinicalRiskModelVersion,
    ClinicalRuleAudit,
    DosageRule,
    DrugInteractionRule,
)
from dispensing.models import (
    DispensingItem, DispensingTransaction, TransactionStatusChoices,
    TransactionTypeChoices,
)
from inventory.models import MedicineBatch
from medicines.models import Medicine, MedicineCategory

from .models import Pharmacy, User
from .services import register_pharmacy_with_admin


class DashboardTests(TestCase):
    def setUp(self):
        self.pharmacy = Pharmacy.objects.create(name='Dashboard Pharmacy')
        other_pharmacy = Pharmacy.objects.create(name='Other Dashboard Pharmacy')
        self.user = User.objects.create_user(
            username='dashboard-user', password='pw', role='ADMIN', pharmacy=self.pharmacy,
        )
        other_user = User.objects.create_user(
            username='other-dashboard-user', password='pw', role='ADMIN', pharmacy=other_pharmacy,
        )
        category = MedicineCategory.objects.create(pharmacy=self.pharmacy, name='Dashboard Category')
        other_category = MedicineCategory.objects.create(pharmacy=other_pharmacy, name='Other Dashboard Category')
        self.medicine = Medicine.objects.create(
            pharmacy=self.pharmacy, category=category, generic_name='Dashboard Medicine',
            strength='10mg', dosage_form='TABLET', unit='tablet', minimum_stock_level=10,
        )
        Medicine.objects.create(
            pharmacy=other_pharmacy, category=other_category, generic_name='Other Medicine',
            strength='20mg', dosage_form='TABLET', unit='tablet', minimum_stock_level=10,
        )
        self.batch = MedicineBatch.objects.create(
            medicine=self.medicine, batch_number='DASH-001', quantity_received=8,
            quantity_remaining=8, cost_price='1.00', selling_price='2.00',
            expiry_date=timezone.localdate() + timedelta(days=90),
        )
        completed = DispensingTransaction.objects.create(
            user=self.user, transaction_type=TransactionTypeChoices.DIRECT_SALE,
            status=TransactionStatusChoices.COMPLETED, total_amount=Decimal('20.00'),
            completed_at=timezone.now(),
        )
        DispensingItem.objects.create(
            transaction=completed, medicine=self.medicine, batch=self.batch,
            quantity=4, unit_price=Decimal('2.00'), line_total=Decimal('8.00'),
        )
        DispensingTransaction.objects.create(
            user=self.user, transaction_type=TransactionTypeChoices.EXTERNAL_PRESCRIPTION,
            status=TransactionStatusChoices.DRAFT,
        )
        DispensingTransaction.objects.create(
            user=other_user, transaction_type=TransactionTypeChoices.DIRECT_SALE,
            status=TransactionStatusChoices.COMPLETED, total_amount=Decimal('999.00'),
            completed_at=timezone.now(),
        )
        self.client.force_login(self.user)

    def test_dashboard_uses_real_tenant_scoped_operational_data(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_medicines'], 1)
        self.assertEqual(response.context['low_stock_alerts'], 1)
        self.assertEqual(response.context['today_sales'], Decimal('20.00'))
        self.assertEqual(response.context['pending_prescriptions'], 1)
        self.assertEqual(response.context['direct_sales_today'], 1)
        self.assertEqual(response.context['medicines_dispensed_today'], 4)
        self.assertEqual(response.context['chart_total'], 1)
        self.assertEqual(len(response.context['chart_days']), 7)

    def test_dashboard_renders_requested_sections(self):
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Total Medicines')
        self.assertContains(response, 'Low Stock Alerts')
        self.assertContains(response, "Today's Sales")
        self.assertContains(response, 'Pending Prescriptions')
        self.assertContains(response, 'Operational Activity')
        self.assertContains(response, 'Transactions Over the Past 7 Days')


class PublicRegistrationTests(TestCase):
    def registration_data(self, **overrides):
        data = {
            'pharmacy_name': 'New Horizon Pharmacy',
            'pharmacy_address': '12 Test Street, Freetown',
            'pharmacy_phone': '+232 76 000 111',
            'pharmacy_email': 'contact@newhorizon.example',
            'license_number': 'LIC-TEST-001',
            'admin_full_name': 'First Administrator',
            'admin_username': 'first-admin',
            'admin_email': 'admin@newhorizon.example',
            'password1': 'S3cure-Pharmacy-Pass!',
            'password2': 'S3cure-Pharmacy-Pass!',
        }
        data.update(overrides)
        return data

    def test_public_pages_load(self):
        pages = {
            'home': 'Intelligent Pharmacy Management',
            'features': 'Practical tools across the pharmacy workflow',
            'about': 'Designed to make pharmacy work more structured',
            'how_it_works': 'A clear path from setup to governed dispensing',
            'register_pharmacy': 'Create your PharmaGuard workspace',
        }
        for url_name, expected in pages.items():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected)

    def test_valid_registration_creates_pharmacy_admin_and_logs_in(self):
        response = self.client.post(reverse('register_pharmacy'), self.registration_data())

        pharmacy = Pharmacy.objects.get(name='New Horizon Pharmacy')
        user = User.objects.get(username='first-admin')
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(user.pharmacy, pharmacy)
        self.assertEqual(user.role, 'ADMIN')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password('S3cure-Pharmacy-Pass!'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_duplicate_username_has_friendly_error(self):
        User.objects.create_user(username='first-admin', password='Existing-Pass-123!', full_name='Existing')
        response = self.client.post(reverse('register_pharmacy'), self.registration_data())

        self.assertContains(response, 'This username is already in use.')
        self.assertFalse(Pharmacy.objects.filter(name='New Horizon Pharmacy').exists())

    def test_duplicate_email_and_pharmacy_name_have_friendly_errors(self):
        Pharmacy.objects.create(name='New Horizon Pharmacy')
        User.objects.create_user(
            username='existing-email', email='admin@newhorizon.example',
            password='Existing-Pass-123!', full_name='Existing',
        )
        response = self.client.post(reverse('register_pharmacy'), self.registration_data())

        self.assertContains(response, 'A pharmacy with this name is already registered.')
        self.assertContains(response, 'An account with this email already exists.')

    def test_django_password_validation_is_applied(self):
        response = self.client.post(
            reverse('register_pharmacy'), self.registration_data(password1='password', password2='password')
        )

        self.assertContains(response, 'This password is too common.')
        self.assertFalse(Pharmacy.objects.filter(name='New Horizon Pharmacy').exists())

    def test_registration_service_rolls_back_pharmacy_if_user_creation_fails(self):
        data = self.registration_data()
        data.pop('password2')
        with patch('accounts.services.User.objects.create_user', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                register_pharmacy_with_admin(data)
        self.assertFalse(Pharmacy.objects.filter(name='New Horizon Pharmacy').exists())

    def test_authenticated_registration_and_home_redirect_to_dashboard(self):
        user = User.objects.create_user(username='signed-in', password='Valid-Pass-123!', full_name='Signed In')
        self.client.force_login(user)
        for url_name in ('home', 'register_pharmacy'):
            with self.subTest(url_name=url_name):
                self.assertRedirects(self.client.get(reverse(url_name)), reverse('dashboard'))

    def test_existing_login_still_authenticates(self):
        user = User.objects.create_user(username='login-user', password='Valid-Pass-123!', full_name='Login User')
        response = self.client.post(reverse('login'), {'username': 'login-user', 'password': 'Valid-Pass-123!'})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)


class PharmacyTenantFoundationTests(TestCase):
    def setUp(self):
        self.pharmacy_a = Pharmacy.objects.create(name='Tenant Pharmacy A')
        self.pharmacy_b = Pharmacy.objects.create(name='Tenant Pharmacy B')

    def test_pharmacy_creation_and_user_link(self):
        user = User.objects.create_user(
            username='tenant-user', password='pw', full_name='Tenant User',
            pharmacy=self.pharmacy_a,
        )
        self.assertEqual(user.pharmacy, self.pharmacy_a)
        self.assertTrue(self.pharmacy_a.is_active)

    def test_superuser_can_remain_without_pharmacy(self):
        user = User.objects.create_superuser(
            username='platform-admin', password='pw', full_name='Platform Admin'
        )
        self.assertIsNone(user.pharmacy)

    def test_category_names_are_unique_per_pharmacy(self):
        MedicineCategory.objects.create(pharmacy=self.pharmacy_a, name='Analgesics')
        MedicineCategory.objects.create(pharmacy=self.pharmacy_b, name='Analgesics')
        with self.assertRaises(IntegrityError), transaction.atomic():
            MedicineCategory.objects.create(pharmacy=self.pharmacy_a, name='Analgesics')

    def test_medicine_formulations_are_unique_per_pharmacy(self):
        category_a = MedicineCategory.objects.create(pharmacy=self.pharmacy_a, name='A')
        category_b = MedicineCategory.objects.create(pharmacy=self.pharmacy_b, name='B')
        values = dict(generic_name='TenantMed', brand_name='', strength='10mg', dosage_form='TABLET', unit='tablet')
        Medicine.objects.create(pharmacy=self.pharmacy_a, category=category_a, **values)
        Medicine.objects.create(pharmacy=self.pharmacy_b, category=category_b, **values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Medicine.objects.create(pharmacy=self.pharmacy_a, category=category_a, **values)

    def test_transaction_inherits_users_pharmacy(self):
        user = User.objects.create_user(
            username='tenant-staff', password='pw', full_name='Tenant Staff',
            pharmacy=self.pharmacy_a,
        )
        dispensing = DispensingTransaction.objects.create(user=user)
        self.assertEqual(dispensing.pharmacy, self.pharmacy_a)

    def test_clinical_knowledge_models_are_pharmacy_scoped(self):
        from clinical.models import Allergen

        Allergen.objects.create(pharmacy=self.pharmacy_a, name='Synthetic Allergen')
        Allergen.objects.create(pharmacy=self.pharmacy_b, name='Synthetic Allergen')
        for model in (Allergen, DrugInteractionRule, AllergyRule, DosageRule):
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.get_field('pharmacy').related_model, Pharmacy)

    def test_normal_admin_queryset_is_tenant_limited(self):
        user = User.objects.create_user(
            username='tenant-admin', password='pw', full_name='Tenant Admin',
            role='ADMIN', pharmacy=self.pharmacy_a,
        )
        category_a = MedicineCategory.objects.create(pharmacy=self.pharmacy_a, name='Visible')
        MedicineCategory.objects.create(pharmacy=self.pharmacy_b, name='Hidden')
        request = RequestFactory().get('/admin/medicines/medicinecategory/')
        request.user = user
        model_admin = admin.site._registry[MedicineCategory]
        self.assertEqual(list(model_admin.get_queryset(request)), [category_a])

    def test_demo_pharmacy_data_migration_is_present(self):
        migration = __import__(
            'accounts.migrations.0004_backfill_default_pharmacy', fromlist=['DEFAULT_PHARMACY_NAME']
        )
        self.assertEqual(migration.DEFAULT_PHARMACY_NAME, 'PharmaGuard Demo Pharmacy')


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

    def test_inventory_navigation_is_accessible_and_active_group_stays_open(self):
        response = self.client.get(reverse('inventory:low_stock_list'))

        self.assertContains(response, 'data-nav-group="inventory"', html=False)
        self.assertContains(response, 'data-active="true"', html=False)
        self.assertContains(response, 'aria-expanded="true"', html=False)
        self.assertContains(response, 'id="inventory-subnav"', html=False)
        self.assertContains(response, 'nav-child-link active', html=False)
        self.assertContains(response, 'js/sidebar.js')


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
