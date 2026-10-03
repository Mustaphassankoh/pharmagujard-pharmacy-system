from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from datetime import date
from django.utils import timezone

from medicines.models import Medicine

class MedicineBatch(models.Model):
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name='batches',
        help_text="The medicine this batch belongs to."
    )
    batch_number = models.CharField(
        max_length=100,
        help_text="The manufacturer's batch or lot number."
    )
    quantity_received = models.PositiveIntegerField(
        validators=[MinValueValidator(1, message="Quantity received must be greater than 0.")],
        help_text="The total initial quantity received for this batch."
    )
    quantity_remaining = models.PositiveIntegerField(
        help_text="The current remaining stock for this batch."
    )
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Cost price per unit."
    )
    selling_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Selling price per unit."
    )
    date_received = models.DateField(
        default=date.today,
        help_text="Date the batch was received into inventory."
    )
    expiry_date = models.DateField(
        help_text="Expiration date of the batch."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this batch is active. Inactive batches are excluded from available stock."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Medicine Batch"
        verbose_name_plural = "Medicine Batches"
        ordering = ['expiry_date', 'date_received']
        constraints = [
            models.UniqueConstraint(
                fields=['medicine', 'batch_number'],
                name='unique_medicine_batch'
            )
        ]

    def clean(self):
        super().clean()
        if self.batch_number:
            self.batch_number = self.batch_number.strip()           
        if self.quantity_remaining is not None and self.quantity_received is not None:
            if not self.pk and self.quantity_remaining > self.quantity_received:
                raise ValidationError({
                    'quantity_remaining': "Initial quantity remaining cannot exceed the quantity received."
                })
                
        if self.date_received and self.expiry_date:
            if self.expiry_date <= self.date_received:
                raise ValidationError({
                    'expiry_date': "Expiry date must be later than the date received."
                })

    def save(self, *args, **kwargs):
        if self.batch_number:
            self.batch_number = self.batch_number.strip()
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return date.today() >= self.expiry_date

    @property
    def is_expiring_soon(self):
        if self.is_expired:
            return False
        # Expiring in <= 30 days
        thirty_days_from_now = date.today() + timezone.timedelta(days=30)
        return self.expiry_date <= thirty_days_from_now

    @property
    def is_out_of_stock(self):
        return self.quantity_remaining == 0

    @property
    def status(self):
        if not self.is_active:
            return "Inactive"
        if self.is_expired:
            return "Expired"
        if self.is_out_of_stock:
            return "Out of Stock"
        if self.is_expiring_soon:
            return "Expiring Soon"
        return "Active"

    def __str__(self):
        return f"{self.medicine.generic_name} - {self.batch_number}"


class TransactionTypeChoices(models.TextChoices):
    STOCK_IN = 'STOCK_IN', 'Stock In'
    ADJUSTMENT_INCREASE = 'ADJUSTMENT_INCREASE', 'Adjustment (Increase)'
    ADJUSTMENT_DECREASE = 'ADJUSTMENT_DECREASE', 'Adjustment (Decrease)'
    DISPENSED = 'DISPENSED', 'Dispensed'


class StockTransaction(models.Model):
    batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name='transactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        help_text="User who performed the transaction."
    )
    transaction_type = models.CharField(
        max_length=50,
        choices=TransactionTypeChoices.choices
    )
    quantity = models.PositiveIntegerField(
        help_text="Quantity involved in the transaction."
    )
    previous_quantity = models.PositiveIntegerField(
        help_text="Quantity remaining before the transaction."
    )
    new_quantity = models.PositiveIntegerField(
        help_text="Quantity remaining after the transaction."
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes for adjustments or corrections."
    )
    reference_number = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text="Optional structured reference (e.g. dispensing transaction number DS-2026-000001)."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stock Transaction"
        verbose_name_plural = "Stock Transactions"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.batch.batch_number} ({self.quantity})"
