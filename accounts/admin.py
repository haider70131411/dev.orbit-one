from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_company_admin')
    list_filter = (
        'is_staff', 
        'is_superuser', 
        'is_active',
        ('company', admin.EmptyFieldListFilter),  # Correct way to filter by null company
    )
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Company', {'fields': ('company',)}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )
    
    def is_company_admin(self, obj):
        return obj.company is not None
    is_company_admin.boolean = True
    is_company_admin.short_description = 'Company Admin'