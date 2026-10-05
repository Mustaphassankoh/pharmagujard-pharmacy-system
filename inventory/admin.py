from django.contrib import admin
from .models import MedicineBatch, StockTransaction
from pharmacy_system.currency import format_currency

@admin.register(MedicineBatch)
class MedicineBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'medicine', 'quantity_remaining', 'quantity_received', 'cost_price_display', 'selling_price_display', 'date_received', 'expiry_date', 'is_active', 'status')
    list_filter = ('is_active', 'date_received', 'expiry_date', 'medicine__category')
    search_fields = ('batch_number', 'medicine__generic_name', 'medicine__brand_name')
    readonly_fields = ('quantity_remaining', 'created_at', 'updated_at')
    fieldsets = (
        ('Batch Identity', {'fields': (('medicine', 'batch_number'), 'is_active')}),
        ('Stock', {'fields': (('quantity_received', 'quantity_remaining'),)}),
        ('Pricing', {'fields': (('cost_price', 'selling_price'),)}),
        ('Dates', {'fields': (('date_received', 'expiry_date'),)}),
        ('Audit Information', {'fields': (('created_at', 'updated_at'),), 'classes': ('collapse',)}),
    )

    @admin.display(description='Cost Price (SLE)', ordering='cost_price')
    def cost_price_display(self, obj):
        return format_currency(obj.cost_price)

    @admin.display(description='Selling Price (SLE)', ordering='selling_price')
    def selling_price_display(self, obj):
        return format_currency(obj.selling_price)
    def get_readonly_fields(self, request, obj=None):
        if obj: # editing an existing object
            return self.readonly_fields + ('quantity_received',)
        return self.readonly_fields

@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('batch', 'user', 'transaction_type', 'quantity', 'created_at')
    list_filter = ('transaction_type', 'created_at', 'user')
    search_fields = ('batch__batch_number', 'batch__medicine__generic_name', 'user__username')
    readonly_fields = ('batch', 'user', 'transaction_type', 'quantity', 'previous_quantity', 'new_quantity', 'notes', 'created_at')

    def has_add_permission(self, request):
        return False  
    def has_change_permission(self, request, obj=None):
        return False    
    def has_delete_permission(self, request, obj=None):
        return False
