from django.contrib import admin
from django.utils.html import format_html
from django.utils.text import slugify
from .models import DispensingTransaction, DispensingItem, ExternalPrescription, Consultation
from pharmacy_system.currency import format_currency
from accounts.admin import PharmacyScopedAdminMixin


class ExternalPrescriptionInline(admin.StackedInline):
    model = ExternalPrescription
    extra = 0
    readonly_fields = ('prescription_source', 'prescriber_name', 'facility_name', 'prescription_date', 'reference_number', 'notes', 'created_at', 'updated_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ConsultationInline(admin.StackedInline):
    model = Consultation
    extra = 0
    readonly_fields = (
        'age', 'sex', 'weight', 'symptoms', 'symptom_duration',
        'known_allergies', 'current_medications', 'pregnancy_status', 'notes',
        'created_at', 'updated_at'
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class DispensingItemInline(admin.TabularInline):
    model = DispensingItem
    extra = 0
    readonly_fields = ('medicine', 'batch', 'quantity', 'dose', 'frequency', 'duration', 'instructions', 'unit_price_display', 'line_total_display', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Unit Price (SLE)')
    def unit_price_display(self, obj):
        return format_currency(obj.unit_price)

    @admin.display(description='Line Total (SLE)')
    def line_total_display(self, obj):
        return format_currency(obj.line_total)


@admin.register(DispensingTransaction)
class DispensingTransactionAdmin(PharmacyScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        'transaction_number', 'pharmacy', 'user', 'transaction_type', 'status_badge',
        'total_amount_display', 'created_at', 'completed_at',
    )
    list_filter = ('status', 'transaction_type', 'created_at')
    search_fields = ('transaction_number', 'user__username', 'user__full_name')
    ordering = ('-created_at',)
    readonly_fields = (
        'transaction_number', 'pharmacy', 'user', 'transaction_type', 'status',
        'subtotal_display', 'total_amount_display', 'created_at', 'completed_at',
    )
    inlines = [ExternalPrescriptionInline, ConsultationInline, DispensingItemInline]

    @admin.display(description='Subtotal (SLE)', ordering='subtotal')
    def subtotal_display(self, obj):
        return format_currency(obj.subtotal)

    @admin.display(description='Total Amount (SLE)', ordering='total_amount')
    def total_amount_display(self, obj):
        return format_currency(obj.total_amount)

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        return format_html(
            '<span class="status-badge status-{}">{}</span>',
            slugify(obj.status),
            obj.get_status_display(),
        )

    def has_add_permission(self, request):
        # Transactions must be created through the dispensing workflow, not admin
        return False

    def has_change_permission(self, request, obj=None):
        # Prevent editing completed/cancelled records
        if obj and obj.status != 'DRAFT':
            return False
        return False  # No editing via admin at all — use the workflow

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DispensingItem)
class DispensingItemAdmin(PharmacyScopedAdminMixin, admin.ModelAdmin):
    pharmacy_lookup = 'transaction__pharmacy'
    list_display = (
        'transaction', 'medicine', 'batch', 'quantity', 'dose', 'unit_price_display', 'line_total_display', 'created_at',
    )
    list_filter = ('transaction__status', 'created_at')
    search_fields = (
        'transaction__transaction_number',
        'medicine__generic_name',
        'batch__batch_number',
    )
    ordering = ('-created_at',)
    readonly_fields = ('transaction', 'medicine', 'batch', 'quantity', 'dose', 'frequency', 'duration', 'instructions', 'unit_price_display', 'line_total_display', 'created_at')

    @admin.display(description='Unit Price (SLE)', ordering='unit_price')
    def unit_price_display(self, obj):
        return format_currency(obj.unit_price)

    @admin.display(description='Line Total (SLE)', ordering='line_total')
    def line_total_display(self, obj):
        return format_currency(obj.line_total)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExternalPrescription)
class ExternalPrescriptionAdmin(PharmacyScopedAdminMixin, admin.ModelAdmin):
    pharmacy_lookup = 'transaction__pharmacy'
    list_display = ('transaction', 'prescriber_name', 'facility_name', 'prescription_source', 'prescription_date', 'created_at')
    search_fields = ('transaction__transaction_number', 'prescriber_name', 'facility_name', 'reference_number')
    readonly_fields = ('transaction', 'prescription_source', 'prescriber_name', 'facility_name', 'prescription_date', 'reference_number', 'notes', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Consultation)
class ConsultationAdmin(PharmacyScopedAdminMixin, admin.ModelAdmin):
    pharmacy_lookup = 'transaction__pharmacy'
    list_display = ('transaction', 'sex', 'age', 'pregnancy_status', 'created_at')
    search_fields = ('transaction__transaction_number', 'symptoms', 'symptom_duration', 'notes')
    readonly_fields = (
        'transaction', 'age', 'sex', 'weight', 'symptoms', 'symptom_duration',
        'known_allergies', 'current_medications', 'pregnancy_status', 'notes',
        'created_at', 'updated_at'
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
