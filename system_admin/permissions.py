# admin_app/permissions.py
from rest_framework.permissions import BasePermission

class IsSuperAdmin(BasePermission):
    """
    Allows access only to superusers or staff with admin privileges.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff
