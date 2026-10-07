from django import forms
from .models import MedicineBatch

class MedicineBatchCreateForm(forms.ModelForm):
    class Meta:
        model = MedicineBatch
        fields = [
            'medicine', 'batch_number', 'quantity_received',
            'cost_price', 'selling_price', 'date_received', 'expiry_date'
        ]
        widgets = {
            'date_received': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'cost_price': 'Cost Price (SLE)',
            'selling_price': 'Selling Price (SLE)',
        }

    def __init__(self, *args, pharmacy=None, **kwargs):
        super().__init__(*args, **kwargs)
        if pharmacy is not None:
            self.fields['medicine'].queryset = self.fields['medicine'].queryset.filter(pharmacy=pharmacy)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})


class MedicineBatchUpdateForm(forms.ModelForm):
    class Meta:
        model = MedicineBatch
        fields = [
            'batch_number', 'cost_price', 'selling_price',
            'date_received', 'expiry_date', 'is_active'
        ]
        widgets = {
            'date_received': forms.DateInput(attrs={'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'cost_price': 'Cost Price (SLE)',
            'selling_price': 'Selling Price (SLE)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Quantity fields are deliberately excluded to prevent casual editing
        for name, field in self.fields.items():
            if name == 'is_active':
                field.widget.attrs.update({'class': 'form-check-input'})
            else:
                field.widget.attrs.update({'class': 'form-control'})


class StockAdjustmentForm(forms.Form):
    ADJUSTMENT_CHOICES = [
        ('INCREASE', 'Increase Stock'),
        ('DECREASE', 'Decrease Stock'),
    ]
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_CHOICES,
        widget=forms.RadioSelect
    )
    quantity = forms.IntegerField(
        min_value=1,
        help_text="The amount to increase or decrease the stock by."
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text="Reason for the adjustment (e.g., Damaged, Expired, Correction)."
    )
