from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils.text import slugify

from .models import (
    Allergen, AllergyRule, ClinicalAlert, ClinicalCheckResult, ClinicalReview,
    DrugInteractionRule, DosageRule, ClinicalRuleAudit, RuleLifecycleStatus,
    ClinicalRiskModelVersion, ClinicalRiskAssessment,
)
from .governance import (
    activate_rule, approve_rule, record_rule_audit, retire_rule,
    submit_rule_for_review,
)
from .forms import (
    AllergenAdminForm, AllergyRuleAdminForm, ClinicalRiskModelVersionAdminForm,
    DosageRuleAdminForm, DrugInteractionRuleAdminForm,
)


RULE_GOVERNANCE_FIELDS = (
    ('version', 'status'), ('effective_from', 'effective_to'),
    ('supersedes', 'next_review_date'), 'change_reason', 'is_active',
)
RULE_AUDIT_FIELDS = (
    ('created_by', 'reviewed_by'), ('approved_by', 'retired_by'),
    ('reviewed_at', 'approved_at'), 'retired_at', ('created_at', 'updated_at'),
)
RULE_SOURCE_FIELDS = (
    'source_reference', ('source_title', 'source_version'),
    ('source_date', 'source_url'),
)


class ClinicalKnowledgeAdmin(admin.ModelAdmin):
    actions = ('submit_selected_for_review', 'approve_selected', 'activate_selected', 'retire_selected')

    def _is_clinical_admin(self, request):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'ADMIN'

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        return self._badge(obj.status, obj.get_status_display())

    @admin.display(description='Severity', ordering='severity')
    def severity_badge(self, obj):
        return self._badge(obj.severity, obj.get_severity_display())

    @staticmethod
    def _badge(value, label):
        return format_html(
            '<span class="status-badge status-{}">{}</span>',
            slugify(value),
            label,
        )

    def has_view_permission(self, request, obj=None):
        return self._is_clinical_admin(request)

    def has_add_permission(self, request):
        return self._is_clinical_admin(request)

    def has_change_permission(self, request, obj=None):
        return self._is_clinical_admin(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        before = None
        if change:
            before = obj.__class__.objects.filter(pk=obj.pk).first()
            from .governance import rule_snapshot
            before = rule_snapshot(before) if before else {}
        super().save_model(request, obj, form, change)
        record_rule_audit(obj, 'UPDATED' if change else 'CREATED', request.user, obj.change_reason, before)

    def get_readonly_fields(self, request, obj=None):
        governance = ('version', 'status', 'created_by', 'reviewed_by', 'reviewed_at', 'approved_by', 'approved_at', 'retired_by', 'retired_at', 'supersedes')
        model_fields = {field.name for field in obj._meta.fields} if obj else {field.name for field in self.model._meta.fields}
        governance = tuple(field for field in governance if field in model_fields)
        timestamps = tuple(field for field in ('created_at', 'updated_at') if field in model_fields)
        if obj and obj.status == RuleLifecycleStatus.ACTIVE:
            return tuple(field.name for field in obj._meta.fields if field.name not in ('effective_to', 'next_review_date', 'change_reason'))
        return governance + timestamps

    def _run_action(self, request, queryset, service, reason):
        successes = 0
        for rule in queryset:
            try:
                service(rule, request.user, reason)
                successes += 1
            except ValidationError as exc:
                self.message_user(request, f'{rule}: {exc}', level=messages.ERROR)
        if successes:
            self.message_user(request, f'{successes} rule(s) updated.', level=messages.SUCCESS)

    @admin.action(description='Submit selected rules for review')
    def submit_selected_for_review(self, request, queryset):
        self._run_action(request, queryset, submit_rule_for_review, 'Submitted through Django admin.')

    @admin.action(description='Approve selected rules')
    def approve_selected(self, request, queryset):
        self._run_action(request, queryset, approve_rule, 'Approved through Django admin.')

    @admin.action(description='Activate selected rules')
    def activate_selected(self, request, queryset):
        self._run_action(request, queryset, activate_rule, 'Activated through Django admin.')

    @admin.action(description='Retire selected rules')
    def retire_selected(self, request, queryset):
        self._run_action(request, queryset, retire_rule, 'Retired through Django admin.')


@admin.register(DrugInteractionRule)
class DrugInteractionRuleAdmin(ClinicalKnowledgeAdmin):
    form = DrugInteractionRuleAdminForm
    list_display = ('medicine_a', 'medicine_b', 'version', 'status_badge', 'severity_badge', 'effective_from', 'effective_to', 'created_by', 'approved_by', 'is_currently_usable')
    list_filter = ('status', 'version', 'severity', 'is_active')
    search_fields = ('medicine_a__generic_name', 'medicine_b__generic_name', 'description', 'source_reference')
    fieldsets = (
        ('Rule Definition', {'fields': (('medicine_a', 'medicine_b'), 'severity')}),
        ('Clinical Information', {'fields': ('description', 'explanation', 'recommendation')}),
        ('Source Information', {'fields': RULE_SOURCE_FIELDS}),
        ('Governance', {'fields': RULE_GOVERNANCE_FIELDS}),
        ('Audit Information', {'fields': RULE_AUDIT_FIELDS, 'classes': ('collapse',)}),
    )


@admin.register(Allergen)
class AllergenAdmin(ClinicalKnowledgeAdmin):
    form = AllergenAdminForm
    list_display = ('name', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    fieldsets = (
        ('Allergen Details', {'fields': ('name', 'description', 'is_active')}),
        ('Audit Information', {'fields': (('created_at', 'updated_at'),), 'classes': ('collapse',)}),
    )


@admin.register(AllergyRule)
class AllergyRuleAdmin(ClinicalKnowledgeAdmin):
    form = AllergyRuleAdminForm
    list_display = ('allergen', 'medicine', 'version', 'status_badge', 'severity_badge', 'effective_from', 'effective_to', 'created_by', 'approved_by', 'is_currently_usable')
    list_filter = ('status', 'version', 'severity', 'is_active', 'allergen')
    search_fields = ('allergen__name', 'medicine__generic_name', 'description', 'source_reference')
    fieldsets = (
        ('Rule Definition', {'fields': (('medicine', 'allergen'), 'severity')}),
        ('Clinical Information', {'fields': ('description', 'explanation', 'recommendation')}),
        ('Source Information', {'fields': RULE_SOURCE_FIELDS}),
        ('Governance', {'fields': RULE_GOVERNANCE_FIELDS}),
        ('Audit Information', {'fields': RULE_AUDIT_FIELDS, 'classes': ('collapse',)}),
    )


@admin.register(DosageRule)
class DosageRuleAdmin(ClinicalKnowledgeAdmin):
    form = DosageRuleAdminForm
    list_display = ('medicine', 'dose_unit', 'version', 'status_badge', 'severity_badge', 'effective_from', 'effective_to', 'created_by', 'approved_by', 'is_currently_usable')
    list_filter = ('status', 'version', 'dose_unit', 'severity', 'is_active')
    search_fields = ('medicine__generic_name', 'medicine__brand_name', 'description', 'source_reference')
    fieldsets = (
        ('Rule Definition', {'fields': (('medicine', 'dose_unit'), 'severity')}),
        ('Dose Limits', {'fields': (
            ('min_single_dose', 'max_single_dose'),
            ('min_frequency_per_day', 'max_frequency_per_day'),
            ('max_daily_dose', 'max_duration_days'),
        )}),
        ('Patient Context', {'fields': (('min_age', 'max_age'), ('min_weight', 'max_weight'))}),
        ('Clinical Information', {'fields': ('description', 'explanation', 'recommendation')}),
        ('Source Information', {'fields': RULE_SOURCE_FIELDS}),
        ('Governance', {'fields': RULE_GOVERNANCE_FIELDS}),
        ('Audit Information', {'fields': RULE_AUDIT_FIELDS, 'classes': ('collapse',)}),
    )


@admin.register(ClinicalReview)
class ClinicalReviewAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'status_badge', 'checked_pairs', 'checked_at')
    readonly_fields = ('transaction', 'status', 'medicine_fingerprint', 'checked_pairs', 'checked_at', 'created_at', 'updated_at')

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        return ClinicalKnowledgeAdmin._badge(obj.status, obj.get_status_display())

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClinicalCheckResult)
class ClinicalCheckResultAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'check_type', 'status_badge', 'checked_at')
    list_filter = ('check_type', 'status')
    readonly_fields = [field.name for field in ClinicalCheckResult._meta.fields]

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        return ClinicalKnowledgeAdmin._badge(obj.status, obj.get_status_display())

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClinicalAlert)
class ClinicalAlertAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'alert_type', 'severity_badge', 'medicine_a', 'medicine_b', 'allergen', 'acknowledged_at')
    list_filter = ('alert_type', 'severity')
    readonly_fields = [field.name for field in ClinicalAlert._meta.fields]

    @admin.display(description='Severity', ordering='severity')
    def severity_badge(self, obj):
        return ClinicalKnowledgeAdmin._badge(obj.severity, obj.get_severity_display())

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClinicalRuleAudit)
class ClinicalRuleAuditAdmin(admin.ModelAdmin):
    list_display = ('rule_type', 'rule_object_id', 'rule_version', 'action', 'changed_by', 'changed_at')
    list_filter = ('rule_type', 'action', 'rule_version')
    search_fields = ('rule_type', 'change_reason')
    readonly_fields = [field.name for field in ClinicalRuleAudit._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClinicalRiskModelVersion)
class ClinicalRiskModelVersionAdmin(ClinicalKnowledgeAdmin):
    form = ClinicalRiskModelVersionAdminForm
    list_display = ('version', 'model_type', 'dataset_name', 'trained_at', 'is_active')
    list_filter = ('is_active', 'model_type')
    readonly_fields = ('trained_at', 'dataset_name', 'dataset_version', 'feature_schema', 'metrics', 'created_at')

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields
    fieldsets = (
        ('Model Identity', {'fields': (('version', 'model_type'), 'artifact_path', 'is_active')}),
        ('Training Data', {'fields': (('dataset_name', 'dataset_version'), 'trained_at')}),
        ('Technical Evidence', {'fields': ('feature_schema', 'metrics')}),
        ('Notes and Audit', {'fields': ('notes', 'created_at')}),
    )


@admin.register(ClinicalRiskAssessment)
class ClinicalRiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'model_version', 'predicted_priority_badge', 'final_priority_badge', 'created_at')
    readonly_fields = [field.name for field in ClinicalRiskAssessment._meta.fields]
    @admin.display(description='Predicted priority', ordering='predicted_priority')
    def predicted_priority_badge(self, obj):
        return ClinicalKnowledgeAdmin._badge(obj.predicted_priority, obj.get_predicted_priority_display())
    @admin.display(description='Final priority', ordering='final_priority')
    def final_priority_badge(self, obj):
        return ClinicalKnowledgeAdmin._badge(obj.final_priority, obj.get_final_priority_display())
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
