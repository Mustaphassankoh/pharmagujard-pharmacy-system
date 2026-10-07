from django import forms
from django.core.exceptions import ValidationError

from medicines.models import Medicine

from .models import Allergen, AllergyRule, ClinicalRiskModelVersion, DosageRule, DrugInteractionRule


class CompactAdminForm(forms.ModelForm):
    """Shared presentation defaults for editable clinical knowledge forms."""

    compact_rows = {
        'description': 3,
        'explanation': 4,
        'recommendation': 3,
        'change_reason': 3,
        'notes': 3,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, rows in self.compact_rows.items():
            if name in self.fields and isinstance(self.fields[name].widget, forms.Textarea):
                self.fields[name].widget.attrs.update({'rows': rows, 'class': 'compact-textarea'})
        help_texts = {
            'source_reference': 'Enter the guideline, document, or reference supporting this rule.',
            'effective_from': 'The date and time when this rule becomes usable in clinical checks.',
            'effective_to': 'Optional. After this date, the rule will no longer be used for new clinical checks.',
            'supersedes': 'Select the previous version replaced by this rule.',
            'severity': 'Controls how prominently this rule is presented during clinical review.',
        }
        for name, help_text in help_texts.items():
            if name in self.fields:
                self.fields[name].help_text = help_text
        if 'source_reference' in self.fields:
            self.fields['source_reference'].error_messages['required'] = (
                'A source reference is required before this rule can be activated.'
            )


class DrugInteractionRuleAdminForm(CompactAdminForm):
    class Meta:
        model = DrugInteractionRule
        fields = '__all__'


class AllergyRuleAdminForm(CompactAdminForm):
    class Meta:
        model = AllergyRule
        fields = '__all__'


class DosageRuleAdminForm(CompactAdminForm):
    class Meta:
        model = DosageRule
        fields = '__all__'


class AllergenAdminForm(CompactAdminForm):
    class Meta:
        model = Allergen
        fields = '__all__'
        widgets = {'description': forms.Textarea(attrs={'rows': 3, 'class': 'compact-textarea'})}


class ClinicalRiskModelVersionAdminForm(CompactAdminForm):
    class Meta:
        model = ClinicalRiskModelVersion
        fields = '__all__'


class TenantAllergenForm(forms.ModelForm):
    class Meta:
        model = Allergen
        fields = ('name', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, pharmacy, **kwargs):
        self.pharmacy = pharmacy
        super().__init__(*args, **kwargs)
        self.instance.pharmacy = pharmacy

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        duplicates = Allergen.objects.filter(pharmacy=self.pharmacy, name__iexact=name)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise ValidationError('An allergen with this name already exists for this pharmacy.')
        return name


class TenantRuleForm(CompactAdminForm):
    date_fields = ('effective_from', 'effective_to')

    def __init__(self, *args, pharmacy, **kwargs):
        self.pharmacy = pharmacy
        super().__init__(*args, **kwargs)
        self.instance.pharmacy = pharmacy
        for name in self.date_fields:
            if name in self.fields:
                self.fields[name].widget = forms.DateTimeInput(attrs={'type': 'datetime-local'})
        if 'next_review_date' in self.fields:
            self.fields['next_review_date'].widget = forms.DateInput(attrs={'type': 'date'})
        if 'source_date' in self.fields:
            self.fields['source_date'].widget = forms.DateInput(attrs={'type': 'date'})

    def _scope_medicines(self, *field_names):
        medicines = Medicine.objects.filter(pharmacy=self.pharmacy, is_active=True).order_by('generic_name', 'strength')
        for name in field_names:
            self.fields[name].queryset = medicines


RULE_FORM_FIELDS = (
    'severity', 'description', 'explanation', 'recommendation', 'source_reference',
    'source_title', 'source_version', 'source_date', 'source_url',
    'effective_from', 'effective_to', 'next_review_date', 'change_reason',
)


class TenantDrugInteractionRuleForm(TenantRuleForm):
    class Meta:
        model = DrugInteractionRule
        fields = ('medicine_a', 'medicine_b') + RULE_FORM_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scope_medicines('medicine_a', 'medicine_b')

    def clean(self):
        cleaned = super().clean()
        medicine_a, medicine_b = cleaned.get('medicine_a'), cleaned.get('medicine_b')
        if medicine_a and medicine_b:
            if medicine_a == medicine_b:
                self.add_error('medicine_b', 'Select two different medicines.')
            else:
                low, high = sorted((medicine_a.pk, medicine_b.pk))
                if DrugInteractionRule.objects.filter(
                    pharmacy=self.pharmacy, medicine_a_id=low, medicine_b_id=high, version=1,
                ).exists():
                    self.add_error(None, 'A matching interaction rule version already exists for this pharmacy.')
        return cleaned


class TenantAllergyRuleForm(TenantRuleForm):
    class Meta:
        model = AllergyRule
        fields = ('medicine', 'allergen') + RULE_FORM_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scope_medicines('medicine')
        self.fields['allergen'].queryset = Allergen.objects.filter(
            pharmacy=self.pharmacy, is_active=True,
        ).order_by('name')


class TenantDosageRuleForm(TenantRuleForm):
    class Meta:
        model = DosageRule
        fields = (
            'medicine', 'dose_unit', 'min_single_dose', 'max_single_dose', 'max_daily_dose',
            'min_frequency_per_day', 'max_frequency_per_day', 'max_duration_days',
            'min_age', 'max_age', 'min_weight', 'max_weight',
        ) + RULE_FORM_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scope_medicines('medicine')
