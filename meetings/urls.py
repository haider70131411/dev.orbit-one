from django.urls import path
from . import views, recording_views

app_name = 'meetings'

urlpatterns = [

    # ADMIN URLS (Authentication Required)
    
    # Meeting CRUD operations
    path('', views.MeetingListView.as_view(), name='meeting-list'),
    path('create/', views.MeetingCreateView.as_view(), name='meeting-create'),
    path('<uuid:pk>/', views.MeetingDetailView.as_view(), name='meeting-detail'),
    
    # Meeting management
    path('<uuid:meeting_id>/participants/', views.meeting_participants_view, name='meeting-participants'),
    path('<uuid:meeting_id>/status/', views.update_meeting_status_view, name='update-meeting-status'),
    path('<uuid:meeting_id>/resend-invitations/', views.resend_invitations_view, name='resend-invitations'),
    path('<uuid:meeting_id>/links/', views.get_meeting_links_view, name='get-meeting-links'),
    path('<uuid:meeting_id>/feedback/', views.MeetingFeedbackView.as_view(), name='meeting-feedback'),  # NEW
    
    # Dashboard
    path('dashboard/', views.meeting_dashboard_view, name='meeting-dashboard'),
    path('not-held/', views.not_held_meetings_view, name='not-held-meetings'),
    
    # PUBLIC URLS (No Authentication Required)
   
    # Meeting info and joining
    path('room/<str:room_id>/info/', views.meeting_info_view, name='meeting-info'),
    path('room/<str:room_id>/join/', views.join_meeting_view, name='join-meeting'),
    path('room/<str:room_id>/leave/', views.leave_meeting_view, name='leave-meeting'),
    path('room/<str:room_id>/status/', views.meeting_status_check_view, name='meeting-status-check'),
    
    # Recording
    path('room/<str:room_id>/recording/config/', recording_views.GetRecordingConfigView.as_view(), name='recording-config'),
    path('room/<str:room_id>/recording/complete/', recording_views.CompleteRecordingUploadView.as_view(), name='recording-complete'),
    path('room/<str:room_id>/recording/upload/', recording_views.UploadRecordingView.as_view(), name='recording-upload'),
    
    # Feedback (public, uses room_id)
    path('room/<str:room_id>/feedback/', views.MeetingFeedbackByRoomView.as_view(), name='meeting-feedback-by-room'),

    # OTP operations
    path('otp/request/', views.request_otp_view, name='request-otp'),
    path('otp/verify/', views.verify_otp_view, name='verify-otp'),

    # WebRTC config
    path('webrtc/config/', views.webrtc_config_view, name='webrtc-config'),
]