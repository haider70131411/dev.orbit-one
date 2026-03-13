# notifications/permissions.py
from rest_framework import permissions


class IsCompanyAdmin(permissions.BasePermission):
    """
    Permission to check if user is company admin
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            hasattr(request.user, 'company') and
            request.user.is_company_admin
        )


