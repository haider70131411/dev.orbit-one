from django.contrib import admin
from .models import Company
from accounts.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_type', 'industry', 'get_admin_email')
    list_filter = ('company_type', 'industry')
    search_fields = ('name', 'admin_user__email')
    
    def get_admin_email(self, obj):
        return obj.admin_user.email if hasattr(obj, 'admin_user') else None
    get_admin_email.short_description = 'Admin Email'