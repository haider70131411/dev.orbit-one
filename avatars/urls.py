from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AvatarViewSet, AvatarUploadUrlView, AvatarDirectCreateView

# Create router
router = DefaultRouter()
router.register(r'', AvatarViewSet, basename='avatar')

# URL patterns
urlpatterns = [
    path('upload-url/', AvatarUploadUrlView.as_view(), name='avatar-upload-url'),
    path('direct-create/', AvatarDirectCreateView.as_view(), name='avatar-direct-create'),
    path('', include(router.urls)),
]

# Available endpoints:
# GET  /api/avatars/                      - List all active avatars
# GET  /api/avatars/{id}/                 - Get avatar details
# GET  /api/avatars/{id}/download_vrm/    - Get VRM download URL
# GET  /api/avatars/count/                - Get total count of avatars
# GET  /api/avatars/?search=term          - Search avatars
# POST /api/avatars/upload-url/           - Get signed R2 upload URL (admin)
# POST /api/avatars/direct-create/        - Create avatar from direct-upload URLs (admin)