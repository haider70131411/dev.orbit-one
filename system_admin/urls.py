# admin_app/urls.py
from django.urls import path
from system_admin import views
from system_admin.admin_views import (
    AdminOverviewView,
    AdminCompanyListView,
    AdminCompanyDetailView,
    AdminMeetingListView,
    AdminMeetingDetailView,
    AdminContactMessageListView,
    AdminContactMessageReplyView,
    AdminSupportThreadListView,
    AdminSupportThreadDetailView,
    AdminSupportUnreadCountView,
    AdminSupportMessageCreateView,
)

urlpatterns = [
    # Overview
    path('overview/', AdminOverviewView.as_view(), name='admin-overview'),
    # Companies (global)
    path('companies/', AdminCompanyListView.as_view(), name='admin-company-list'),
    path('companies/<int:id>/', AdminCompanyDetailView.as_view(), name='admin-company-detail'),
    # Meetings (global)
    path('meetings/', AdminMeetingListView.as_view(), name='admin-meeting-list'),
    path('meetings/<uuid:id>/', AdminMeetingDetailView.as_view(), name='admin-meeting-detail'),
    # Contact messages (Contact Us)
    path('contact-messages/', AdminContactMessageListView.as_view(), name='admin-contactmessage-list'),
    path('contact-messages/<int:id>/reply/', AdminContactMessageReplyView.as_view(), name='admin-contactmessage-reply'),
    # Support chat (company owners)
    path('support/unread-count/', AdminSupportUnreadCountView.as_view(), name='admin-support-unread-count'),
    path('support/threads/', AdminSupportThreadListView.as_view(), name='admin-support-thread-list'),
    path('support/threads/<int:id>/', AdminSupportThreadDetailView.as_view(), name='admin-support-thread-detail'),
    path('support/threads/<int:id>/messages/', AdminSupportMessageCreateView.as_view(), name='admin-support-message-create'),
    # Users
    path('users/', views.AdminUserListView.as_view(), name='admin-user-list'),
    path('users/<int:id>/', views.AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('users/create/', views.AdminUserCreateView.as_view(), name='admin-user-create'),
    path('users/<int:id>/update/', views.AdminUserUpdateView.as_view(), name='admin-user-update'),
    path('users/<int:id>/deactivate/', views.AdminDeactivateUserView.as_view(), name='admin-user-deactivate'),
    path('users/<int:id>/reactivate/', views.AdminReactivateUserView.as_view(), name='admin-user-reactivate'),
    path('users/<int:id>/delete/', views.AdminDeleteUserView.as_view(), name='admin-user-delete'),
    path('users/<int:id>/force-password-reset/', views.AdminForcePasswordResetView.as_view(), name='admin-force-password-reset'),
    path('users/<int:id>/set-password/', views.AdminSetPasswordView.as_view(), name='admin-set-password'),
]

