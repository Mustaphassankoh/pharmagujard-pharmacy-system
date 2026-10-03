from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class MedicineCategory(models.Model):
    name = models.CharField(
        max_length=150,
        unique=True,
        help_text="Unique name of the medicine category (e.g., Analgesics, Antibiotics)."
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the category."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this category is active in the pharmacy catalog."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Medicine Category"
        verbose_name_plural = "Medicine Categories"
        ordering = ['name']

    def clean(self):
        super().clean()
        if self.name:
            self.name = self.name.strip()
            # Case-insensitive duplicate check for clean error reporting
            existing = MedicineCategory.objects.filter(name__iexact=self.name)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({'name': f"A category with the name '{self.name}' already exists."})

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DosageFormChoices(models.TextChoices):
    TABLET = 'TABLET', 'Tablet'
    CAPSULE = 'CAPSULE', 'Capsule'
    SYRUP = 'SYRUP', 'Syrup'
    SUSPENSION = 'SUSPENSION', 'Suspension'
    INJECTION = 'INJECTION', 'Injection'
    CREAM = 'CREAM', 'Cream'
    OINTMENT = 'OINTMENT', 'Ointment'
    DROPS = 'DROPS', 'Drops'
    INHALER = 'INHALER', 'Inhaler'
    POWDER = 'POWDER', 'Powder'
    OTHER = 'OTHER', 'Other'


class UnitChoices(models.TextChoices):
    TABLET = 'tablet', 'Tablet'
    CAPSULE = 'capsule', 'Capsule'
    BOTTLE = 'bottle', 'Bottle'
    VIAL = 'vial', 'Vial'
    AMPOULE = 'ampoule', 'Ampoule'
    SACHET = 'sachet', 'Sachet'
    TUBE = 'tube', 'Tube'
    PACK = 'pack', 'Pack'
    ML = 'ml', 'ml'
    UNIT = 'unit', 'Unit'
    OTHER = 'other', 'Other'


class Medicine(models.Model):
    category = models.ForeignKey(
        MedicineCategory,
        on_delete=models.PROTECT,
        related_name='medicines',
        help_text="Category this medicine belongs to."
    )
    generic_name = models.CharField(
        max_length=255,
        help_text="Generic or scientific name (e.g., Paracetamol, Amoxicillin)."
    )
    brand_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Commercial or brand name (e.g., Panadol, Amoxil), if applicable."
    )
    dosage_form = models.CharField(
        max_length=50,
        choices=DosageFormChoices.choices,
        help_text="Formulation of the drug."
    )
    strength = models.CharField(
        max_length=100,
        help_text="Strength or concentration (e.g., 500mg, 250mg/5ml)."
    )
    unit = models.CharField(
        max_length=50,
        choices=UnitChoices.choices,
        help_text="Standard dispensing unit."
    )
    description = models.TextField(
        blank=True,
        help_text="Optional clinical notes, storage instructions, or indications."
    )
    minimum_stock_level = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(0, message="Minimum stock level cannot be negative.")],
        help_text="Threshold quantity below which low-stock alerts are triggered."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this medicine is active in the pharmacy catalog."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Medicine"
        verbose_name_plural = "Medicines"
        ordering = ['generic_name', 'brand_name']
        constraints = [
            models.UniqueConstraint(
                fields=['generic_name', 'brand_name', 'strength', 'dosage_form'],
                name='unique_medicine_formulation'
            )
        ]

    def clean(self):
        super().clean()
        if self.generic_name:
            self.generic_name = self.generic_name.strip()
        if self.brand_name:
            self.brand_name = self.brand_name.strip()
        if self.strength:
            self.strength = self.strength.strip()

        if self.minimum_stock_level is not None and self.minimum_stock_level < 0:
            raise ValidationError({'minimum_stock_level': "Minimum stock level cannot be negative."})

        # Case-insensitive formulation duplicate check
        if self.generic_name and self.strength and self.dosage_form:
            duplicates = Medicine.objects.filter(
                generic_name__iexact=self.generic_name,
                brand_name__iexact=self.brand_name,
                strength__iexact=self.strength,
                dosage_form=self.dosage_form
            )
            if self.pk:
                duplicates = duplicates.exclude(pk=self.pk)
            if duplicates.exists():
                raise ValidationError(
                    "A medicine with this identical formulation (Generic Name, Brand Name, Strength, and Dosage Form) already exists."
                )

    def save(self, *args, **kwargs):
        if self.generic_name:
            self.generic_name = self.generic_name.strip()
        if self.brand_name:
            self.brand_name = self.brand_name.strip()
        if self.strength:
            self.strength = self.strength.strip()
        super().save(*args, **kwargs)

    @property
    def total_available_stock(self):
        from datetime import date
        from django.db.models import Sum

        if hasattr(self, '_valid_batches_cache'):
            return sum(batch.quantity_remaining for batch in self._valid_batches_cache)
        
        # Available stock is from batches that are active, not expired, and quantity > 0
        valid_batches = self.batches.filter(
            is_active=True,
            expiry_date__gt=date.today(),
            quantity_remaining__gt=0
        )
        total = valid_batches.aggregate(total=Sum('quantity_remaining'))['total']
        return total or 0

    @property
    def stock_status(self):
        stock = self.total_available_stock
        if stock == 0:
            return "Out of Stock"
        elif stock <= self.minimum_stock_level:
            return "Low Stock"
        return "In Stock"

    @property
    def active_batches_count(self):
        from datetime import date
        if hasattr(self, '_valid_batches_cache'):
            return len(self._valid_batches_cache)
        return self.batches.filter(
            is_active=True,
            expiry_date__gt=date.today(),
            quantity_remaining__gt=0
        ).count()

    @property
    def nearest_expiry_date(self):
        from datetime import date
        if hasattr(self, '_valid_batches_cache'):
            return min(
                (batch.expiry_date for batch in self._valid_batches_cache),
                default=None,
            )
        nearest_batch = self.batches.filter(
            is_active=True,
            expiry_date__gt=date.today(),
            quantity_remaining__gt=0
        ).order_by('expiry_date').first()
        
        return nearest_batch.expiry_date if nearest_batch else None

    def __str__(self):
        if self.brand_name:
            return f"{self.generic_name} ({self.brand_name}) - {self.strength} {self.get_dosage_form_display()}"
        return f"{self.generic_name} - {self.strength} {self.get_dosage_form_display()}"
