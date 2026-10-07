from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from inventory.models import MedicineBatch
from medicines.models import Medicine, MedicineCategory

from .models import Pharmacy

User = get_user_model()


class StaffManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pharmacy_a = Pharmacy.objects.create(name='Staff Pharmacy A', address='A')
        cls.pharmacy_b = Pharmacy.objects.create(name='Staff Pharmacy B', address='B')
        cls.admin_a = User.objects.create_user(username='staff-admin-a', password='pw', full_name='Admin A', role='ADMIN', pharmacy=cls.pharmacy_a)
        cls.staff_a = User.objects.create_user(username='existing-staff-a', password='pw', full_name='Existing Staff A', pharmacy=cls.pharmacy_a)
        cls.admin_b = User.objects.create_user(username='staff-admin-b', password='pw', full_name='Admin B', role='ADMIN', pharmacy=cls.pharmacy_b)
        cls.staff_b = User.objects.create_user(username='existing-staff-b', password='pw', full_name='Existing Staff B', pharmacy=cls.pharmacy_b)

    def test_admin_staff_list_is_tenant_scoped(self):
        self.client.force_login(self.admin_a)
        response = self.client.get(reverse('staff_list'))
        self.assertContains(response, self.staff_a.full_name)
        self.assertNotContains(response, self.staff_b.full_name)

    def test_admin_creates_fixed_role_staff_in_own_pharmacy(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(reverse('staff_create'), {
            'full_name': 'Created Staff', 'username': 'created-staff',
            'email': 'created@example.com', 'password1': 'Strong-Staff-Pass-2026!',
            'password2': 'Strong-Staff-Pass-2026!',
        })
        staff = User.objects.get(username='created-staff')
        self.assertRedirects(response, reverse('staff_list'))
        self.assertEqual(staff.role, 'PHARMACY_STAFF')
        self.assertEqual(staff.pharmacy, self.pharmacy_a)
        self.assertTrue(staff.check_password('Strong-Staff-Pass-2026!'))

    def test_admin_can_update_deactivate_and_reset_own_staff(self):
        self.client.force_login(self.admin_a)
        self.client.post(reverse('staff_update', args=[self.staff_a.pk]), {
            'full_name': 'Updated Staff A', 'username': self.staff_a.username,
            'email': 'updated-a@example.com',
        })
        self.client.post(reverse('staff_password', args=[self.staff_a.pk]), {
            'password1': 'Reset-Staff-Pass-2026!', 'password2': 'Reset-Staff-Pass-2026!',
        })
        self.staff_a.refresh_from_db()
        self.assertEqual(self.staff_a.full_name, 'Updated Staff A')
        self.assertTrue(self.staff_a.check_password('Reset-Staff-Pass-2026!'))
        self.client.post(reverse('staff_deactivate', args=[self.staff_a.pk]))
        self.staff_a.refresh_from_db()
        self.assertFalse(self.staff_a.is_active)

    def test_staff_cannot_access_management_or_profile(self):
        self.client.force_login(self.staff_a)
        urls = (
            reverse('staff_list'), reverse('staff_create'),
            reverse('staff_update', args=[self.staff_a.pk]),
            reverse('staff_password', args=[self.staff_a.pk]),
            reverse('pharmacy_profile'),
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(reverse('staff_deactivate', args=[self.staff_a.pk])).status_code, 403)

    def test_admin_cannot_manage_foreign_staff_by_url(self):
        self.client.force_login(self.admin_a)
        for url_name in ('staff_update', 'staff_password'):
            self.assertEqual(self.client.get(reverse(url_name, args=[self.staff_b.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('staff_deactivate', args=[self.staff_b.pk])).status_code, 404)

    def test_pharmacy_profile_updates_only_current_pharmacy(self):
        self.client.force_login(self.admin_a)
        response = self.client.post(reverse('pharmacy_profile'), {
            'name': 'Staff Pharmacy A Updated', 'address': 'Updated Address',
            'phone': '+23276000111', 'email': 'a-updated@example.com',
            'license_number': 'LIC-A',
        })
        self.assertRedirects(response, reverse('pharmacy_profile'))
        self.pharmacy_a.refresh_from_db()
        self.pharmacy_b.refresh_from_db()
        self.assertEqual(self.pharmacy_a.name, 'Staff Pharmacy A Updated')
        self.assertEqual(self.pharmacy_b.name, 'Staff Pharmacy B')

    def test_sidebar_uses_approved_operational_navigation(self):
        self.client.force_login(self.admin_a)
        admin_response = self.client.get(reverse('dashboard'))
        self.assertContains(admin_response, 'Clinical oversight')
        self.assertNotContains(admin_response, 'Administration')
        self.assertNotContains(admin_response, 'Pharmacy Profile')
        self.assertEqual(self.client.get(reverse('pharmacy_profile')).status_code, 200)
        self.client.force_login(self.staff_a)
        staff_response = self.client.get(reverse('dashboard'))
        self.assertNotContains(staff_response, 'Clinical oversight')
        self.assertNotContains(staff_response, 'Administration')
        self.assertNotContains(staff_response, 'Pharmacy Profile')


class MultiPharmacyOnboardingFlowTests(TestCase):
    def registration_data(self, suffix):
        phone_suffix = {'A': '01', 'B': '02'}[suffix]
        return {
            'pharmacy_name': f'Onboarding Pharmacy {suffix}',
            'pharmacy_address': f'{suffix} Main Road',
            'pharmacy_phone': f'+232760000{phone_suffix}',
            'pharmacy_email': f'pharmacy-{suffix.lower()}@example.com',
            'license_number': '',
            'admin_full_name': f'Admin {suffix}',
            'admin_username': f'onboarding-admin-{suffix.lower()}',
            'admin_email': f'admin-{suffix.lower()}@example.com',
            'password1': 'Rugged-Cedar-7429!',
            'password2': 'Rugged-Cedar-7429!',
        }

    def test_registration_to_staff_login_and_workflow_creation(self):
        self.client.post(reverse('register_pharmacy'), self.registration_data('A'))
        admin = User.objects.get(username='onboarding-admin-a')
        self.assertEqual(int(self.client.session['_auth_user_id']), admin.pk)
        self.client.post(reverse('staff_create'), {
            'full_name': 'Onboarding Staff A', 'username': 'onboarding-staff-a',
            'email': 'staff-a@example.com', 'password1': 'Silver-Comet-4821!',
            'password2': 'Silver-Comet-4821!',
        })
        category = MedicineCategory.objects.create(pharmacy=admin.pharmacy, name='Onboarding Medicines A')
        medicine = Medicine.objects.create(pharmacy=admin.pharmacy, category=category, generic_name='Onboarding Medicine A', strength='10mg', dosage_form='TABLET', unit='tablet')
        MedicineBatch.objects.create(medicine=medicine, batch_number='ONBOARD-A', quantity_received=20, quantity_remaining=20, cost_price='1', selling_price='2', date_received=date.today(), expiry_date=date.today() + timedelta(days=90))
        self.client.post(reverse('logout'))
        login_response = self.client.post(reverse('login'), {'username': 'onboarding-staff-a', 'password': 'Silver-Comet-4821!'})
        self.assertRedirects(login_response, reverse('dashboard'))
        for route in ('dispensing:new_direct_sale', 'dispensing:new_external_prescription', 'dispensing:new_consultation'):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 302)
        self.assertEqual(admin.pharmacy.dispensing_transactions.count(), 3)

    def test_second_public_registration_remains_fully_separate(self):
        self.client.post(reverse('register_pharmacy'), self.registration_data('A'))
        admin_a = User.objects.get(username='onboarding-admin-a')
        category_a = MedicineCategory.objects.create(pharmacy=admin_a.pharmacy, name='Private Catalogue A')
        Medicine.objects.create(pharmacy=admin_a.pharmacy, category=category_a, generic_name='Private Medicine A', strength='1', dosage_form='TABLET', unit='tablet')
        self.client.post(reverse('logout'))
        self.client.post(reverse('register_pharmacy'), self.registration_data('B'))
        admin_b = User.objects.get(username='onboarding-admin-b')
        response = self.client.get(reverse('medicines:medicine_list'))
        self.assertNotContains(response, 'Private Medicine A')
        self.assertNotEqual(admin_a.pharmacy, admin_b.pharmacy)
        self.assertEqual(admin_b.pharmacy.medicines.count(), 0)
        self.assertEqual(admin_b.pharmacy.dispensing_transactions.count(), 0)
