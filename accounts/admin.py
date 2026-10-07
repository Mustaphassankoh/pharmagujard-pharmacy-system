from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Pharmacy, User


class PharmacyScopedAdminMixin:
    pharmacy_lookup = 'pharmacy'

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.pharmacy_id:
            return queryset
        if self.pharmacy_lookup == 'pharmacy' and not any(
            field.name == 'pharmacy' for field in self.model._meta.fields
        ):
            return queryset
        return queryset.filter(**{self.pharmacy_lookup: request.user.pharmacy})

    def save_model(self, request, obj, form, change):
        if hasattr(obj, 'pharmacy_id') and not obj.pharmacy_id and not request.user.is_superuser:
            obj.pharmacy = request.user.pharmacy
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser and any(field.name == 'pharmacy' for field in self.model._meta.fields):
            return fields + ('pharmacy',)
        return fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        related_model = db_field.remote_field.model
        if not request.user.is_superuser:
            field_names = {field.name for field in related_model._meta.fields}
            if 'pharmacy' in field_names:
                kwargs['queryset'] = related_model.objects.filter(pharmacy_id=request.user.pharmacy_id)
            elif related_model is request.user.__class__:
                kwargs['queryset'] = related_model.objects.filter(pharmacy_id=request.user.pharmacy_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Pharmacy)
class PharmacyAdmin(admin.ModelAdmin):
    list_display = ('name', 'license_number', 'email', 'phone', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'license_number', 'email', 'phone')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.pharmacy_id:
            return queryset
        return queryset.filter(pk=request.user.pharmacy_id)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'full_name', 'pharmacy', 'role', 'is_active']
    list_filter = UserAdmin.list_filter + ('pharmacy', 'role')
    fieldsets = UserAdmin.fieldsets + (
        ('PharmaGuard Profile', {'fields': (('full_name', 'role'), 'pharmacy')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('PharmaGuard Profile', {'fields': (('full_name', 'role'), 'pharmacy')}),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser or not request.user.pharmacy_id:
            return queryset
        return queryset.filter(pharmacy=request.user.pharmacy)

admin.site.register(User, CustomUserAdmin)
