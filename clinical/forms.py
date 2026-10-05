from django import forms

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
