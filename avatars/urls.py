from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AvatarViewSet

# Create router
router = DefaultRouter()
router.register(r'', AvatarViewSet, basename='avatar')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
]

# Available endpoints:
# GET  /api/avatars/              - List all active avatars
# GET  /api/avatars/{id}/         - Get avatar details
# GET  /api/avatars/{id}/download_vrm/ - Get VRM download URL
# GET  /api/avatars/count/        - Get total count of avatars
# GET  /api/avatars/?search=term  - Search avatars