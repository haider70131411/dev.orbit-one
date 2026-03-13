from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EmailViewSet, EmailCampaignViewSet, EmailTemplateViewSet,
    InboxViewSet, AIEmailViewSet, EmailAnalyticsViewSet,
    EmailTrackingView, EmailLinkTrackingView,
    notification_list_view, notification_unread_count_view,
    notification_mark_read_view, notification_mark_all_read_view,
    notification_delete_view
)

router = DefaultRouter()
router.register(r'emails', EmailViewSet, basename='email')
router.register(r'campaigns', EmailCampaignViewSet, basename='campaign')
router.register(r'templates', EmailTemplateViewSet, basename='template')
router.register(r'inbox', InboxViewSet, basename='inbox')
router.register(r'ai', AIEmailViewSet, basename='ai-email')
router.register(r'analytics', EmailAnalyticsViewSet, basename='analytics')

app_name = 'notifications'

urlpatterns = [
    path('', include(router.urls)),
    
    # Tracking endpoints (no auth required)
    path('track/open/<uuid:tracking_id>/', EmailTrackingView.as_view(), name='track-open'),
    path('track/click/<uuid:tracking_id>/', EmailLinkTrackingView.as_view(), name='track-click'),
    
    # Dashboard notification endpoints
    path('dashboard/', notification_list_view, name='notification-list'),
    path('dashboard/unread-count/', notification_unread_count_view, name='notification-unread-count'),
    path('dashboard/<int:notification_id>/mark-read/', notification_mark_read_view, name='notification-mark-read'),
    path('dashboard/mark-all-read/', notification_mark_all_read_view, name='notification-mark-all-read'),
    path('dashboard/<int:notification_id>/delete/', notification_delete_view, name='notification-delete'),
]