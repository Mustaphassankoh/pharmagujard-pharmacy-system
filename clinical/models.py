from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from dispensing.models import DispensingTransaction, DoseUnitChoices
from medicines.models import Medicine


class SeverityChoices(models.TextChoices):
    LOW = 'LOW', 'Low'
    MODERATE = 'MODERATE', 'Moderate'
    HIGH = 'HIGH', 'High'
    CRITICAL = 'CRITICAL', 'Critical'


class ClinicalCheckStatus(models.TextChoices):
    PASSED = 'PASSED', 'Passed'
    WARNING = 'WARNING', 'Warning'
    NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not Applicable'
    NOT_CHECKED = 'NOT_CHECKED', 'Not Checked'


class AlertTypeChoices(models.TextChoices):
    DRUG_INTERACTION = 'DRUG_INTERACTION', 'Drug Interaction'
    ALLERGY = 'ALLERGY', 'Allergy'
    DOSAGE = 'DOSAGE', 'Dosage'


class ClinicalCheckType(models.TextChoices):
    DRUG_INTERACTION = 'DRUG_INTERACTION', 'Drug Interaction'
    ALLERGY = 'ALLERGY', 'Allergy'
    DOSAGE = 'DOSAGE', 'Dosage'


class DosageAlertReason(models.TextChoices):
    BELOW_SINGLE_DOSE = 'BELOW_SINGLE_DOSE', 'Below single dose'
    ABOVE_SINGLE_DOSE = 'ABOVE_SINGLE_DOSE', 'Above single dose'
    ABOVE_DAILY_DOSE = 'ABOVE_DAILY_DOSE', 'Above daily dose'
    FREQUENCY_TOO_LOW = 'FREQUENCY_TOO_LOW', 'Frequency too low'
    FREQUENCY_TOO_HIGH = 'FREQUENCY_TOO_HIGH', 'Frequency too high'
    DURATION_TOO_LONG = 'DURATION_TOO_LONG', 'Duration too long'


class RuleLifecycleStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
    APPROVED = 'APPROVED', 'Approved'
    ACTIVE = 'ACTIVE', 'Active'
    RETIRED = 'RETIRED', 'Retired'


class RuleAuditAction(models.TextChoices):
    MIGRATED = 'MIGRATED', 'Migrated'
    CREATED = 'CREATED', 'Created'
    UPDATED = 'UPDATED', 'Updated'
    SUBMITTED_FOR_REVIEW = 'SUBMITTED_FOR_REVIEW', 'Submitted for Review'
    REVIEWED = 'REVIEWED', 'Reviewed'
    APPROVED = 'APPROVED', 'Approved'
    ACTIVATED = 'ACTIVATED', 'Activated'
    RETIRED = 'RETIRED', 'Retired'
    SUPERSEDED = 'SUPERSEDED', 'Superseded'


class GovernedRuleMixin(models.Model):
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=RuleLifecycleStatus.choices, default=RuleLifecycleStatus.DRAFT)
    effective_from = models.DateTimeField(null=True, blank=True)
    effective_to = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='created_%(class)ss')
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='reviewed_%(class)ss')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='approved_%(class)ss')
    approved_at = models.DateTimeField(null=True, blank=True)
    retired_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='retired_%(class)ss')
    retired_at = models.DateTimeField(null=True, blank=True)
    change_reason = models.TextField(blank=True)
    source_title = models.CharField(max_length=255, blank=True)
    source_version = models.CharField(max_length=100, blank=True)
    source_date = models.DateField(null=True, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    next_review_date = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        errors = {}
        if self.effective_from and self.effective_to and self.effective_from >= self.effective_to:
            errors['effective_to'] = "'Effective from' must be earlier than 'Effective to'."
        if self.status in (RuleLifecycleStatus.APPROVED, RuleLifecycleStatus.ACTIVE) and not self.approved_by_id:
            errors['approved_by'] = 'Approved and active rules require an approver.'
        if self.status == RuleLifecycleStatus.ACTIVE and not self.approved_at:
            errors['approved_at'] = 'Active rules require an approval timestamp.'
        if self.status == RuleLifecycleStatus.RETIRED and not self.retired_at:
            errors['retired_at'] = 'Retired rules require a retirement timestamp.'
        if getattr(self, 'supersedes_id', None):
            if self.pk and self.supersedes_id == self.pk:
                errors['supersedes'] = 'A rule cannot supersede itself. Select a different previous version.'
            ancestor = self.supersedes
            seen = {self.pk} if self.pk else set()
            while ancestor:
                if ancestor.pk in seen:
                    errors['supersedes'] = 'This selection would create a circular version history. Select an earlier unrelated version.'
                    break
                seen.add(ancestor.pk)
                ancestor = ancestor.supersedes
        if errors:
            raise ValidationError(errors)

    def validate_active_immutability(self, fields):
        if not self.pk:
            return
        previous = self.__class__.objects.filter(pk=self.pk).first()
        if previous and previous.status == RuleLifecycleStatus.ACTIVE:
            changed = [field for field in fields if getattr(previous, field) != getattr(self, field)]
            if changed:
                raise ValidationError({'status': 'Clinically meaningful fields on an active rule require a new version.'})

    @property
    def is_currently_usable(self):
        now = timezone.now()
        return (
            self.is_active and self.status == RuleLifecycleStatus.ACTIVE
            and (self.effective_from is None or self.effective_from <= now)
            and (self.effective_to is None or self.effective_to >= now)
            and self.retired_at is None
        )


class DosageRule(GovernedRuleMixin):
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='dosage_rules')
    dose_unit = models.CharField(max_length=20, choices=DoseUnitChoices.choices)
    min_single_dose = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    max_single_dose = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    max_daily_dose = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    min_frequency_per_day = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_frequency_per_day = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    max_duration_days = models.PositiveIntegerField(null=True, blank=True)
    min_age = models.PositiveIntegerField(null=True, blank=True)
    max_age = models.PositiveIntegerField(null=True, blank=True)
    min_weight = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    max_weight = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    severity = models.CharField(max_length=20, choices=SeverityChoices.choices)
    description = models.CharField(max_length=255)
    explanation = models.TextField()
    recommendation = models.TextField()
    source_reference = models.CharField(max_length=500)
    is_active = models.BooleanField(default=True)
    supersedes = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='superseded_by_versions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['medicine__generic_name', 'dose_unit', '-severity']

    def clean(self):
        super().clean()
        errors = {}
        for low, high, label in (
            ('min_single_dose', 'max_single_dose', 'single dose'),
            ('min_age', 'max_age', 'age'),
            ('min_weight', 'max_weight', 'weight'),
            ('min_frequency_per_day', 'max_frequency_per_day', 'frequency'),
        ):
            low_value, high_value = getattr(self, low), getattr(self, high)
            if low_value is not None and high_value is not None and low_value > high_value:
                errors[low] = f'Minimum {label} cannot be greater than maximum {label}.'
        for field in ('min_single_dose', 'max_single_dose', 'max_daily_dose',
                      'min_frequency_per_day', 'max_frequency_per_day',
                      'min_weight', 'max_weight'):
            value = getattr(self, field)
            if value is not None and value <= 0:
                errors[field] = 'Value must be positive.'
        if self.max_duration_days is not None and self.max_duration_days <= 0:
            errors['max_duration_days'] = 'Maximum duration must be positive.'
        if not (self.source_reference or '').strip():
            errors['source_reference'] = 'A source reference is required before this rule can be activated.'
        if self.medicine_id and self.dose_unit:
            duplicate_fields = (
                'medicine_id', 'dose_unit', 'min_single_dose', 'max_single_dose',
                'max_daily_dose', 'min_frequency_per_day', 'max_frequency_per_day',
                'max_duration_days', 'min_age', 'max_age', 'min_weight', 'max_weight', 'version',
            )
            duplicate = DosageRule.objects.filter(**{field: getattr(self, field) for field in duplicate_fields})
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors['medicine'] = 'A dosage rule already exists with the same medicine, unit, and version.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.validate_active_immutability((
            'medicine_id', 'dose_unit', 'min_single_dose', 'max_single_dose', 'max_daily_dose',
            'min_frequency_per_day', 'max_frequency_per_day', 'max_duration_days', 'min_age',
            'max_age', 'min_weight', 'max_weight', 'severity', 'description', 'explanation',
            'recommendation', 'source_reference', 'source_title', 'source_version', 'source_date', 'source_url',
        ))
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.medicine.generic_name} ({self.dose_unit})'


class DrugInteractionRule(GovernedRuleMixin):
    medicine_a = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='interaction_rules_as_a')
    medicine_b = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='interaction_rules_as_b')
    severity = models.CharField(max_length=20, choices=SeverityChoices.choices)
    description = models.CharField(max_length=255)
    explanation = models.TextField()
    recommendation = models.TextField()
    source_reference = models.CharField(max_length=500)
    is_active = models.BooleanField(default=True)
    supersedes = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='superseded_by_versions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-severity', 'medicine_a__generic_name', 'medicine_b__generic_name']
        constraints = [
            models.UniqueConstraint(fields=['medicine_a', 'medicine_b', 'version'], name='unique_versioned_interaction_pair'),
            models.CheckConstraint(condition=Q(medicine_a_id__lt=F('medicine_b_id')), name='canonical_interaction_pair_order'),
        ]

    def clean(self):
        super().clean()
        if self.medicine_a_id and self.medicine_b_id:
            if self.medicine_a_id == self.medicine_b_id:
                raise ValidationError({'medicine_b': 'Medicine A and Medicine B cannot be the same medicine.'})
            if self.medicine_a_id > self.medicine_b_id:
                self.medicine_a_id, self.medicine_b_id = self.medicine_b_id, self.medicine_a_id
            duplicate = DrugInteractionRule.objects.filter(
                medicine_a_id=self.medicine_a_id,
                medicine_b_id=self.medicine_b_id,
                version=self.version,
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError('A drug interaction rule already exists for these two medicines in this version.')

    def save(self, *args, **kwargs):
        if self.medicine_a_id and self.medicine_b_id and self.medicine_a_id > self.medicine_b_id:
            self.medicine_a_id, self.medicine_b_id = self.medicine_b_id, self.medicine_a_id
        self.validate_active_immutability((
            'medicine_a_id', 'medicine_b_id', 'severity', 'description', 'explanation',
            'recommendation', 'source_reference', 'source_title', 'source_version', 'source_date', 'source_url',
        ))
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.medicine_a.generic_name} + {self.medicine_b.generic_name} ({self.get_severity_display()})'


class Allergen(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AllergyRule(GovernedRuleMixin):
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='allergy_rules')
    allergen = models.ForeignKey(Allergen, on_delete=models.PROTECT, related_name='medicine_rules')
    severity = models.CharField(max_length=20, choices=SeverityChoices.choices)
    description = models.CharField(max_length=255)
    explanation = models.TextField()
    recommendation = models.TextField()
    source_reference = models.CharField(max_length=500)
    is_active = models.BooleanField(default=True)
    supersedes = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='superseded_by_versions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-severity', 'allergen__name', 'medicine__generic_name']
        constraints = [
            models.UniqueConstraint(fields=['medicine', 'allergen', 'version'], name='unique_versioned_medicine_allergen_rule'),
        ]

    def clean(self):
        super().clean()
        if self.medicine_id and self.allergen_id:
            duplicate = AllergyRule.objects.filter(
                medicine_id=self.medicine_id,
                allergen_id=self.allergen_id,
                version=self.version,
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError(
                    'An allergy rule already exists for this medicine and allergen in this version.'
                )

    def save(self, *args, **kwargs):
        self.validate_active_immutability((
            'medicine_id', 'allergen_id', 'severity', 'description', 'explanation',
            'recommendation', 'source_reference', 'source_title', 'source_version', 'source_date', 'source_url',
        ))
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.allergen.name} + {self.medicine.generic_name} ({self.get_severity_display()})'


class ClinicalReview(models.Model):
    transaction = models.OneToOneField(DispensingTransaction, on_delete=models.CASCADE, related_name='clinical_review')
    status = models.CharField(max_length=20, choices=ClinicalCheckStatus.choices, default=ClinicalCheckStatus.NOT_CHECKED)
    medicine_fingerprint = models.CharField(max_length=255, blank=True)
    checked_pairs = models.PositiveIntegerField(default=0)
    checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.transaction.transaction_number}: {self.get_status_display()}'


class ClinicalCheckResult(models.Model):
    transaction = models.ForeignKey(DispensingTransaction, on_delete=models.CASCADE, related_name='clinical_check_results')
    check_type = models.CharField(max_length=30, choices=ClinicalCheckType.choices)
    status = models.CharField(max_length=20, choices=ClinicalCheckStatus.choices, default=ClinicalCheckStatus.NOT_CHECKED)
    input_fingerprint = models.CharField(max_length=500, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['check_type']
        constraints = [
            models.UniqueConstraint(fields=['transaction', 'check_type'], name='unique_transaction_clinical_check'),
        ]

    def __str__(self):
        return f'{self.transaction.transaction_number}: {self.get_check_type_display()} - {self.get_status_display()}'


class ClinicalAlert(models.Model):
    transaction = models.ForeignKey(DispensingTransaction, on_delete=models.CASCADE, related_name='clinical_alerts')
    alert_type = models.CharField(max_length=30, choices=AlertTypeChoices.choices, default=AlertTypeChoices.DRUG_INTERACTION)
    severity = models.CharField(max_length=20, choices=SeverityChoices.choices)
    status = models.CharField(max_length=20, choices=ClinicalCheckStatus.choices, default=ClinicalCheckStatus.WARNING)
    medicine_a = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='clinical_alerts_as_a')
    medicine_b = models.ForeignKey(Medicine, null=True, blank=True, on_delete=models.PROTECT, related_name='clinical_alerts_as_b')
    allergen = models.ForeignKey(Allergen, null=True, blank=True, on_delete=models.PROTECT, related_name='clinical_alerts')
    title = models.CharField(max_length=255)
    description = models.TextField()
    explanation = models.TextField()
    recommendation = models.TextField()
    source_reference = models.CharField(max_length=500)
    rule_reference = models.ForeignKey(DrugInteractionRule, null=True, blank=True, on_delete=models.SET_NULL, related_name='alerts')
    allergy_rule_reference = models.ForeignKey(AllergyRule, null=True, blank=True, on_delete=models.SET_NULL, related_name='alerts')
    dosage_rule_reference = models.ForeignKey(DosageRule, null=True, blank=True, on_delete=models.SET_NULL, related_name='alerts')
    dosage_reason = models.CharField(max_length=40, choices=DosageAlertReason.choices, blank=True)
    snapshot_details = models.JSONField(default=dict, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='acknowledged_clinical_alerts')
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledgement_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['transaction', 'alert_type', 'rule_reference'], name='unique_transaction_rule_alert'),
            models.UniqueConstraint(fields=['transaction', 'alert_type', 'allergy_rule_reference'], name='unique_transaction_allergy_rule_alert'),
        ]

    def __str__(self):
        return self.title


class ClinicalRuleAudit(models.Model):
    rule_type = models.CharField(max_length=40)
    rule_object_id = models.PositiveBigIntegerField()
    rule_version = models.PositiveIntegerField()
    action = models.CharField(max_length=30, choices=RuleAuditAction.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='clinical_rule_audits')
    changed_at = models.DateTimeField(auto_now_add=True)
    change_reason = models.TextField(blank=True)
    before_snapshot = models.JSONField(default=dict, blank=True)
    after_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-changed_at', '-pk']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('Clinical rule audit records are append-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Clinical rule audit records cannot be deleted.')

    def __str__(self):
        return f'{self.rule_type} #{self.rule_object_id} v{self.rule_version}: {self.action}'


class ReviewPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    MODERATE = 'MODERATE', 'Moderate'
    HIGH = 'HIGH', 'High'
    CRITICAL = 'CRITICAL', 'Critical'


class ClinicalRiskModelVersion(models.Model):
    version = models.CharField(max_length=50, unique=True)
    model_type = models.CharField(max_length=100, default='DecisionTreeClassifier')
    artifact_path = models.CharField(max_length=500)
    trained_at = models.DateTimeField()
    dataset_name = models.CharField(max_length=255)
    dataset_version = models.CharField(max_length=100)
    feature_schema = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)
    is_active = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            ClinicalRiskModelVersion.objects.exclude(pk=self.pk).update(is_active=False)

    def __str__(self):
        return f'{self.version} ({self.model_type})'


class ClinicalRiskAssessment(models.Model):
    transaction = models.OneToOneField(DispensingTransaction, on_delete=models.CASCADE, related_name='risk_assessment')
    model_version = models.ForeignKey(ClinicalRiskModelVersion, on_delete=models.PROTECT, related_name='assessments')
    predicted_priority = models.CharField(max_length=20, choices=ReviewPriority.choices)
    final_priority = models.CharField(max_length=20, choices=ReviewPriority.choices)
    prediction_probability = models.DecimalField(max_digits=7, decimal_places=6, null=True, blank=True)
    feature_snapshot = models.JSONField(default=dict)
    decision_path = models.JSONField(default=list)
    explanation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and ClinicalRiskAssessment.objects.filter(pk=self.pk).exists():
            raise ValidationError('Clinical risk assessments are immutable snapshots.')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.transaction}: {self.final_priority}'
