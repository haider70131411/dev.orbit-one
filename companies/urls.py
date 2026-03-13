from django.urls import path
from .views import (
    # SMTP Configuration views
    CompanyCreateView,CompanyDetailView,
    CompanyPersonCreateView,
    CompanyPersonListView,
    CompanyPersonDetailView,
    SMTPConfigurationCreateView, SMTPConfigurationDetailView,
    test_smtp_configuration, get_smtp_presets,
    CompanyAdminActionView, # Import Admin View
)


urlpatterns = [
    path('', CompanyCreateView.as_view(), name='company-create'),
    path('my/', CompanyDetailView.as_view(), name='company-detail'),
    # path('my/interviewers/', InterviewerListView.as_view(), name='interviewer-list'),
    # path('my/interviewers/create/', InterviewerCreateView.as_view(), name='interviewer-create'),
    # path('my/interviewers/<int:pk>/', InterviewerDetailView.as_view(), name='interviewer-detail'),  # For retrieve/update/delete
    path('my/people/', CompanyPersonListView.as_view(), name='company-person-list'),
    path('my/people/create/', CompanyPersonCreateView.as_view(), name='company-person-create'),
    path('my/people/<int:pk>/', CompanyPersonDetailView.as_view(), name='company-person-detail'),


    # SMTP Configuration URLs
    path('my/smtp/', SMTPConfigurationDetailView.as_view(), name='smtp-detail'),
    path('my/smtp/create/', SMTPConfigurationCreateView.as_view(), name='smtp-create'),
    path('my/smtp/test/', test_smtp_configuration, name='smtp-test'),
    path('smtp/presets/', get_smtp_presets, name='smtp-presets'),
    
    # Admin Action
    path('admin/company/<int:pk>/verify/', CompanyAdminActionView.as_view(), name='company-admin-verify'),
]

