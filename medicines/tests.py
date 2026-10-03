from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from accounts.models import User
from medicines.models import MedicineCategory, Medicine, DosageFormChoices, UnitChoices


class MedicineCategoryModelTests(TestCase):
    def test_create_category_and_trim(self):
        category = MedicineCategory.objects.create(
            name="   Analgesics   ",
            description="Pain relievers"
        )
        self.assertEqual(category.name, "Analgesics")
        self.assertTrue(category.is_active)
        self.assertEqual(str(category), "Analgesics")

    def test_duplicate_category_name_rejected(self):
        MedicineCategory.objects.create(name="Antibiotics")
        duplicate = MedicineCategory(name="antibiotics")
        with self.assertRaises(ValidationError):
            duplicate.clean()


class MedicineModelTests(TestCase):
    def setUp(self):
        self.category = MedicineCategory.objects.create(name="Analgesics")

    def test_create_medicine_success(self):
        med = Medicine.objects.create(
            category=self.category,
            generic_name="Paracetamol",
            brand_name="Panadol",
            dosage_form=DosageFormChoices.TABLET,
            strength="500mg",
            unit=UnitChoices.TABLET,
            minimum_stock_level=20
        )
        self.assertEqual(str(med), "Paracetamol (Panadol) - 500mg Tablet")
        self.assertTrue(med.is_active)

    def test_negative_minimum_stock_rejected(self):
        med = Medicine(
            category=self.category,
            generic_name="Ibuprofen",
            dosage_form=DosageFormChoices.TABLET,
            strength="400mg",
            unit=UnitChoices.TABLET,
            minimum_stock_level=-5
        )
        with self.assertRaises(ValidationError):
            med.clean()

    def test_duplicate_formulation_rejected(self):
        Medicine.objects.create(
            category=self.category,
            generic_name="Paracetamol",
            brand_name="Panadol",
            dosage_form=DosageFormChoices.TABLET,
            strength="500mg",
            unit=UnitChoices.TABLET
        )
        duplicate = Medicine(
            category=self.category,
            generic_name="paracetamol",
            brand_name="panadol",
            dosage_form=DosageFormChoices.TABLET,
            strength="500mg",
            unit=UnitChoices.TABLET
        )
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_different_strength_allowed(self):
        Medicine.objects.create(
            category=self.category,
            generic_name="Paracetamol",
            brand_name="Panadol",
            dosage_form=DosageFormChoices.TABLET,
            strength="500mg",
            unit=UnitChoices.TABLET
        )
        different_strength = Medicine(
            category=self.category,
            generic_name="Paracetamol",
            brand_name="Panadol",
            dosage_form=DosageFormChoices.TABLET,
            strength="1000mg",
            unit=UnitChoices.TABLET
        )
        # Should not raise validation error
        different_strength.clean()

    def test_category_protected_from_deletion_with_linked_medicines(self):
        Medicine.objects.create(
            category=self.category,
            generic_name="Aspirin",
            dosage_form=DosageFormChoices.TABLET,
            strength="100mg",
            unit=UnitChoices.TABLET
        )
        with self.assertRaises(ProtectedError):
            self.category.delete()


class MedicineViewsAndPermissionsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="adminuser",
            password="adminpassword123",
            role="ADMIN",
            full_name="Admin Pharmacist"
        )
        self.staff_user = User.objects.create_user(
            username="staffuser",
            password="staffpassword123",
            role="PHARMACY_STAFF",
            full_name="Staff Tech"
        )
        self.category = MedicineCategory.objects.create(name="Antibiotics", description="Bacterial infection remedies")
        self.med = Medicine.objects.create(
            category=self.category,
            generic_name="Amoxicillin",
            brand_name="Amoxil",
            dosage_form=DosageFormChoices.CAPSULE,
            strength="500mg",
            unit=UnitChoices.CAPSULE,
            minimum_stock_level=15
        )

    def test_unauthenticated_redirected_to_login(self):
        # Accessing medicine list redirects to login
        res = self.client.get(reverse('medicines:medicine_list'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login/', res.url)

        # Accessing category list redirects to login
        res = self.client.get(reverse('medicines:category_list'))
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login/', res.url)

    def test_admin_can_manage_categories(self):
        self.client.login(username="adminuser", password="adminpassword123")

        # 1. View category list
        res = self.client.get(reverse('medicines:category_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Antibiotics")

        # 2. Add category
        res = self.client.post(reverse('medicines:category_create'), {
            'name': 'Antimalarials',
            'description': 'Malaria treatments',
            'is_active': 'on'
        })
        self.assertEqual(res.status_code, 302)
        self.assertTrue(MedicineCategory.objects.filter(name="Antimalarials").exists())

        # 3. Edit category
        cat = MedicineCategory.objects.get(name="Antimalarials")
        res = self.client.post(reverse('medicines:category_update', args=[cat.pk]), {
            'name': 'Antimalarials Updated',
            'description': 'Updated description',
            'is_active': 'on'
        })
        self.assertEqual(res.status_code, 302)
        cat.refresh_from_db()
        self.assertEqual(cat.name, "Antimalarials Updated")

        # 4. Deactivate category
        res = self.client.post(reverse('medicines:category_toggle_status', args=[cat.pk]))
        self.assertEqual(res.status_code, 302)
        cat.refresh_from_db()
        self.assertFalse(cat.is_active)

    def test_admin_can_manage_medicines(self):
        self.client.login(username="adminuser", password="adminpassword123")

        # Add medicine
        res = self.client.post(reverse('medicines:medicine_create'), {
            'category': self.category.pk,
            'generic_name': 'Ciprofloxacin',
            'brand_name': 'Cipro',
            'dosage_form': DosageFormChoices.TABLET,
            'strength': '500mg',
            'unit': UnitChoices.TABLET,
            'description': 'Fluoroquinolone',
            'minimum_stock_level': 10,
            'is_active': 'on'
        })
        self.assertEqual(res.status_code, 302)
        cipro = Medicine.objects.get(generic_name="Ciprofloxacin")
        self.assertEqual(cipro.category, self.category)

        # Edit medicine
        res = self.client.post(reverse('medicines:medicine_update', args=[cipro.pk]), {
            'category': self.category.pk,
            'generic_name': 'Ciprofloxacin',
            'brand_name': 'Ciprobay',
            'dosage_form': DosageFormChoices.TABLET,
            'strength': '500mg',
            'unit': UnitChoices.TABLET,
            'description': 'Updated notes',
            'minimum_stock_level': 25,
            'is_active': 'on'
        })
        self.assertEqual(res.status_code, 302)
        cipro.refresh_from_db()
        self.assertEqual(cipro.brand_name, "Ciprobay")
        self.assertEqual(cipro.minimum_stock_level, 25)

        # Toggle medicine status (deactivate)
        res = self.client.post(reverse('medicines:medicine_toggle_status', args=[cipro.pk]))
        self.assertEqual(res.status_code, 302)
        cipro.refresh_from_db()
        self.assertFalse(cipro.is_active)

    def test_pharmacy_staff_access_permissions(self):
        self.client.login(username="staffuser", password="staffpassword123")

        # Staff CAN view medicine list
        res = self.client.get(reverse('medicines:medicine_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Amoxicillin")

        # Staff CAN view medicine detail
        res = self.client.get(reverse('medicines:medicine_detail', args=[self.med.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Amoxil")

        # Staff CANNOT add medicine (HTTP 403)
        res = self.client.get(reverse('medicines:medicine_create'))
        self.assertEqual(res.status_code, 403)

        # Staff CANNOT edit medicine (HTTP 403)
        res = self.client.get(reverse('medicines:medicine_update', args=[self.med.pk]))
        self.assertEqual(res.status_code, 403)

        # Staff CANNOT view category list (HTTP 403)
        res = self.client.get(reverse('medicines:category_list'))
        self.assertEqual(res.status_code, 403)

        # Staff CANNOT add category (HTTP 403)
        res = self.client.get(reverse('medicines:category_create'))
        self.assertEqual(res.status_code, 403)

    def test_search_and_filter_and_pagination(self):
        self.client.login(username="staffuser", password="staffpassword123")

        # Create additional medicines
        cat_pain = MedicineCategory.objects.create(name="Analgesics")
        Medicine.objects.create(
            category=cat_pain,
            generic_name="Paracetamol",
            brand_name="Panadol Extra",
            dosage_form=DosageFormChoices.TABLET,
            strength="500mg",
            unit=UnitChoices.TABLET,
            is_active=True
        )
        Medicine.objects.create(
            category=cat_pain,
            generic_name="Ibuprofen",
            brand_name="Advil",
            dosage_form=DosageFormChoices.TABLET,
            strength="400mg",
            unit=UnitChoices.TABLET,
            is_active=False
        )

        # Search by generic name
        res = self.client.get(reverse('medicines:medicine_list') + '?q=paracetamol')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Paracetamol")
        self.assertNotContains(res, "Amoxicillin")

        # Search by brand name
        res = self.client.get(reverse('medicines:medicine_list') + '?q=advil')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ibuprofen")
        self.assertNotContains(res, "Amoxicillin")

        # Filter by category
        res = self.client.get(reverse('medicines:medicine_list') + f'?category={cat_pain.pk}')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Paracetamol")
        self.assertContains(res, "Ibuprofen")
        self.assertNotContains(res, "Amoxicillin")

        # Filter by status (inactive)
        res = self.client.get(reverse('medicines:medicine_list') + '?status=inactive')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ibuprofen")
        self.assertNotContains(res, "Paracetamol")

        # Pagination: create 20 items to verify pagination
        for i in range(20):
            Medicine.objects.create(
                category=cat_pain,
                generic_name=f"MedItem_{i:02d}",
                dosage_form=DosageFormChoices.TABLET,
                strength="10mg",
                unit=UnitChoices.TABLET
            )

        res = self.client.get(reverse('medicines:medicine_list') + '?page=1')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context['medicines'].has_next())
