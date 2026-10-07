from django import forms
from .models import MedicineCategory, Medicine


class MedicineCategoryForm(forms.ModelForm):
    def __init__(self, *args, pharmacy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pharmacy = pharmacy or getattr(self.instance, 'pharmacy', None)

    class Meta:
        model = MedicineCategory
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Analgesics, Antibiotics',
                'autofocus': True,
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional brief description of this therapeutic class...',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'name': 'Category Name',
            'description': 'Description',
            'is_active': 'Is Active Catalog Category',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name:
            raise forms.ValidationError("Category name cannot be empty.")
        
        # Check uniqueness case-insensitively
        qs = MedicineCategory.objects.filter(name__iexact=name, pharmacy=self.pharmacy)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"A category with the name '{name}' already exists.")
        return name


class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = [
            'category',
            'generic_name',
            'brand_name',
            'dosage_form',
            'strength',
            'unit',
            'description',
            'minimum_stock_level',
            'is_active'
        ]
        widgets = {
            'category': forms.Select(attrs={
                'class': 'form-control form-select',
            }),
            'generic_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Paracetamol, Amoxicillin',
                'autofocus': True,
            }),
            'brand_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Panadol, Augmentin (optional)',
            }),
            'dosage_form': forms.Select(attrs={
                'class': 'form-control form-select',
            }),
            'strength': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 500mg, 250mg/5ml',
            }),
            'unit': forms.Select(attrs={
                'class': 'form-control form-select',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional instructions, indications or special storage requirements...',
            }),
            'minimum_stock_level': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': 'e.g., 10',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
        labels = {
            'category': 'Therapeutic Category',
            'generic_name': 'Generic Name',
            'brand_name': 'Brand Name',
            'dosage_form': 'Dosage Form',
            'strength': 'Strength',
            'unit': 'Dispensing Unit',
            'description': 'Description / Notes',
            'minimum_stock_level': 'Minimum Stock Level (Alert Threshold)',
            'is_active': 'Active in Formulary',
        }

    def __init__(self, *args, pharmacy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pharmacy = pharmacy or getattr(self.instance, 'pharmacy', None)
        # Order categories by name and show active first
        self.fields['category'].queryset = MedicineCategory.objects.filter(
            pharmacy=self.pharmacy
        ).order_by('-is_active', 'name')
        self.fields['category'].empty_label = "-- Select Category --"
        self.fields['dosage_form'].empty_label = "-- Select Dosage Form --"
        self.fields['unit'].empty_label = "-- Select Unit --"

    def clean_generic_name(self):
        val = self.cleaned_data.get('generic_name', '').strip()
        if not val:
            raise forms.ValidationError("Generic name is required.")
        return val

    def clean_brand_name(self):
        return self.cleaned_data.get('brand_name', '').strip()

    def clean_strength(self):
        val = self.cleaned_data.get('strength', '').strip()
        if not val:
            raise forms.ValidationError("Strength is required.")
        return val

    def clean_minimum_stock_level(self):
        val = self.cleaned_data.get('minimum_stock_level')
        if val is None or val < 0:
            raise forms.ValidationError("Minimum stock level cannot be negative.")
        return val

    def clean(self):
        cleaned_data = super().clean()
        generic_name = cleaned_data.get('generic_name')
        brand_name = cleaned_data.get('brand_name', '')
        strength = cleaned_data.get('strength')
        dosage_form = cleaned_data.get('dosage_form')

        if generic_name and strength and dosage_form:
            duplicates = Medicine.objects.filter(
                pharmacy=self.pharmacy,
                generic_name__iexact=generic_name,
                brand_name__iexact=brand_name,
                strength__iexact=strength,
                dosage_form=dosage_form
            )
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError(
                    "A medicine with this identical formulation (Generic Name, Brand Name, Strength, and Dosage Form) already exists."
                )
        return cleaned_data
