from django import forms
from .models import DoseUnitChoices


class AddToCartForm(forms.Form):
    """
    Validates a medicine-add-to-cart request.
    medicine_id is submitted as a hidden field populated by the JS search widget.
    quantity is entered by the user.
    """
    medicine_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        min_value=1,
        error_messages={'required': "Please select a medicine from the search results."}
    )
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity",
        error_messages={
            'required': "Please enter a quantity.",
            'min_value': "Quantity must be at least 1.",
        }
    )

class PrescriptionItemForm(AddToCartForm):
    """
    Extends AddToCartForm with optional clinical fields for external prescriptions.
    """
    dose = forms.CharField(max_length=100, required=False, label="Dose")
    frequency = forms.CharField(max_length=100, required=False, label="Frequency")
    duration = forms.CharField(max_length=100, required=False, label="Duration")
    instructions = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False,
        label="Instructions"
    )
    dose_amount = forms.DecimalField(max_digits=12, decimal_places=4, min_value=0.0001, required=False, label='Structured dose amount')
    dose_unit = forms.ChoiceField(choices=[('', '---------'), *DoseUnitChoices.choices], required=False, label='Structured dose unit')
    frequency_per_day = forms.DecimalField(max_digits=8, decimal_places=4, min_value=0.0001, required=False, label='Frequency per day')
    duration_days = forms.IntegerField(min_value=1, required=False, label='Duration in days')

    def clean(self):
        cleaned = super().clean()
        amount, unit = cleaned.get('dose_amount'), cleaned.get('dose_unit')
        if (amount is None) != (not unit):
            raise forms.ValidationError('Structured dose amount and unit must be provided together.')
        return cleaned

from .models import ExternalPrescription

class ExternalPrescriptionForm(forms.ModelForm):
    class Meta:
        model = ExternalPrescription
        fields = [
            'prescription_source', 'prescriber_name', 'facility_name',
            'prescription_date', 'reference_number', 'notes'
        ]
        widgets = {
            'prescription_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

from .models import Consultation

class ConsultationForm(forms.ModelForm):
    class Meta:
        model = Consultation
        fields = [
            'age', 'sex', 'weight', 'symptoms', 'symptom_duration',
            'structured_allergies', 'known_allergies', 'current_medications',
            'pregnancy_status', 'notes'
        ]
        labels = {
            'structured_allergies': 'Structured allergies',
            'known_allergies': 'Additional allergy notes',
        }
        widgets = {
            'symptoms': forms.Textarea(attrs={'rows': 3}),
            'known_allergies': forms.Textarea(attrs={'rows': 2}),
            'structured_allergies': forms.CheckboxSelectMultiple(),
            'current_medications': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        if weight is not None and weight <= 0:
            raise forms.ValidationError("Weight must be positive.")
        return weight

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['structured_allergies'].queryset = self.fields['structured_allergies'].queryset.filter(is_active=True)
        for name, field in self.fields.items():
            if name != 'structured_allergies':
                field.widget.attrs.update({'class': 'form-control'})
