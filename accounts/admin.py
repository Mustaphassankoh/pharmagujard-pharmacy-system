from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ['username', 'email', 'full_name', 'role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('PharmaGuard Profile', {'fields': (('full_name', 'role'),)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('PharmaGuard Profile', {'fields': (('full_name', 'role'),)}),
    )

admin.site.register(User, CustomUserAdmin)
