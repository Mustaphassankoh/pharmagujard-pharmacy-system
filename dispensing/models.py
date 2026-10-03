from django.db import models
from django.conf import settings
from django.utils import timezone

from inventory.models import MedicineBatch
from medicines.models import Medicine


class TransactionTypeChoices(models.TextChoices):
    DIRECT_SALE = 'DIRECT_SALE', 'Direct Sale'
    EXTERNAL_PRESCRIPTION = 'EXTERNAL_PRESCRIPTION', 'External Prescription'
    CONSULTATION = 'CONSULTATION', 'Consultation'


class TransactionStatusChoices(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class DoseUnitChoices(models.TextChoices):
    MG = 'MG', 'mg'
    G = 'G', 'g'
    MCG = 'MCG', 'mcg'
    ML = 'ML', 'mL'
    TABLET = 'TABLET', 'tablet'
    CAPSULE = 'CAPSULE', 'capsule'
    UNIT = 'UNIT', 'unit'


class DispensingTransaction(models.Model):
    """
    Central model for all dispensing transactions.
    DRAFT  → items in session cart, no stock deducted.
    COMPLETED → items committed to DispensingItem, stock deducted.
    CANCELLED → no stock impact.
    """
    transaction_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        db_index=True,
        help_text="Auto-generated after initial save. Format: TX-YYYY-NNNNNN."
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='dispensing_transactions',
        help_text="Staff member who created this transaction."
    )
    transaction_type = models.CharField(
        max_length=30,
        choices=TransactionTypeChoices.choices,
        default=TransactionTypeChoices.DIRECT_SALE,
    )
    status = models.CharField(
        max_length=20,
        choices=TransactionStatusChoices.choices,
        default=TransactionStatusChoices.DRAFT,
    )
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=0,
        help_text="Sum of all line totals (before any discounts/taxes)."
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=0,
        help_text="Final amount charged."
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Set when transaction status changes to COMPLETED."
    )

    class Meta:
        verbose_name = "Dispensing Transaction"
        verbose_name_plural = "Dispensing Transactions"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        """
        Transaction number is generated from the database PK after first save.
        This guarantees uniqueness without a count() query.
        Format: TX-{year}-{pk zero-padded to 6 digits}
        """
        super().save(*args, **kwargs)
        if not self.transaction_number:
            year = self.created_at.year
            self.transaction_number = f"TX-{year}-{self.pk:06d}"
            # Use update() to avoid recursion and to avoid triggering signals
            DispensingTransaction.objects.filter(pk=self.pk).update(
                transaction_number=self.transaction_number
            )

    def __str__(self):
        return f"{self.transaction_number} ({self.get_status_display()})"


class DispensingItem(models.Model):
    """
    One row per batch allocation within a dispensing transaction.
    A single medicine request may produce multiple rows if FEFO spreads
    the quantity across multiple batches.
    """
    transaction = models.ForeignKey(
        DispensingTransaction,
        on_delete=models.CASCADE,
        related_name='items',
    )
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name='dispensing_items',
    )
    batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name='dispensing_items',
    )
    quantity = models.PositiveIntegerField(
        help_text="Units dispensed from this specific batch."
    )
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Selling price per unit at the time of dispensing (from MedicineBatch.selling_price)."
    )
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="quantity × unit_price."
    )
    # Clinical dosage fields for External Prescriptions
    dose = models.CharField(max_length=100, blank=True, null=True)
    frequency = models.CharField(max_length=100, blank=True, null=True)
    duration = models.CharField(max_length=100, blank=True, null=True)
    instructions = models.TextField(blank=True, null=True)
    dose_amount = models.DecimalField(max_digits=12, decimal_places=4, blank=True, null=True)
    dose_unit = models.CharField(max_length=20, choices=DoseUnitChoices.choices, blank=True, null=True)
    frequency_per_day = models.DecimalField(max_digits=8, decimal_places=4, blank=True, null=True)
    duration_days = models.PositiveIntegerField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dispensing Item"
        verbose_name_plural = "Dispensing Items"
        ordering = ['transaction', 'medicine__generic_name']

    def __str__(self):
        return f"{self.medicine.generic_name} × {self.quantity} @ {self.unit_price}"


class PrescriptionSourceChoices(models.TextChoices):
    HOSPITAL = 'HOSPITAL', 'Hospital'
    CLINIC = 'CLINIC', 'Clinic'
    DOCTOR = 'DOCTOR', 'Doctor'
    COMMUNITY_HEALTH_CENTER = 'COMMUNITY_HEALTH_CENTER', 'Community Health Center'
    OTHER = 'OTHER', 'Other'


class ExternalPrescription(models.Model):
    transaction = models.OneToOneField(
        DispensingTransaction,
        on_delete=models.CASCADE,
        related_name='external_prescription'
    )
    prescription_source = models.CharField(
        max_length=50,
        choices=PrescriptionSourceChoices.choices,
        blank=True, null=True
    )
    prescriber_name = models.CharField(max_length=200, blank=True, null=True)
    facility_name = models.CharField(max_length=200, blank=True, null=True)
    prescription_date = models.DateField(blank=True, null=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "External Prescription"
        verbose_name_plural = "External Prescriptions"

    def __str__(self):
        return f"Prescription for {self.transaction.transaction_number}"


class SexChoices(models.TextChoices):
    MALE = 'MALE', 'Male'
    FEMALE = 'FEMALE', 'Female'
    OTHER = 'OTHER', 'Other'


class PregnancyStatusChoices(models.TextChoices):
    NOT_PREGNANT = 'NOT_PREGNANT', 'Not Pregnant'
    PREGNANT = 'PREGNANT', 'Pregnant'
    UNKNOWN = 'UNKNOWN', 'Unknown / Not Applicable'


class Consultation(models.Model):
    transaction = models.OneToOneField(
        DispensingTransaction,
        on_delete=models.CASCADE,
        related_name='consultation'
    )
    age = models.PositiveIntegerField(blank=True, null=True)
    sex = models.CharField(
        max_length=20,
        choices=SexChoices.choices,
        blank=True, null=True
    )
    weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        blank=True, null=True,
        help_text="Weight in kg"
    )
    symptoms = models.TextField(help_text="Required")
    symptom_duration = models.CharField(max_length=100, blank=True, null=True)
    known_allergies = models.TextField(blank=True, null=True)
    structured_allergies = models.ManyToManyField(
        'clinical.Allergen',
        blank=True,
        related_name='consultations',
        help_text='Structured allergies included in automated allergy checking.',
    )
    current_medications = models.TextField(blank=True, null=True)
    pregnancy_status = models.CharField(
        max_length=20,
        choices=PregnancyStatusChoices.choices,
        blank=True, null=True
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Consultation"
        verbose_name_plural = "Consultations"

    def __str__(self):
        return f"Consultation for {self.transaction.transaction_number}"
