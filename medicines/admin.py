from django.contrib import admin
from .models import MedicineCategory, Medicine


@admin.register(MedicineCategory)
class MedicineCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('name',)
    fieldsets = (
        ('Category Details', {'fields': ('name', 'description', 'is_active')}),
    )


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = (
        'generic_name',
        'brand_name',
        'category',
        'dosage_form',
        'strength',
        'unit',
        'minimum_stock_level',
        'is_active',
        'updated_at'
    )
    list_filter = (
        'is_active',
        'dosage_form',
        'category',
        'unit',
    )
    search_fields = (
        'generic_name',
        'brand_name',
        'strength',
        'category__name'
    )
    ordering = ('generic_name', 'brand_name')
    autocomplete_fields = ('category',)
    fieldsets = (
        ('Medicine Identity', {'fields': (('generic_name', 'brand_name'), 'category')}),
        ('Formulation', {'fields': (('dosage_form', 'strength'), 'unit')}),
        ('Inventory Settings', {'fields': ('minimum_stock_level', 'is_active')}),
        ('Notes', {'fields': ('description',)}),
    )
