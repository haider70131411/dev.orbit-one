from django.urls import path
from .views import (
    ContactMessageCreateView,
    contact_message_create,
    SupportThreadListView,
    SupportThreadCreateView,
    SupportThreadDetailView,
    SupportMessageCreateView,
)

urlpatterns = [
    path('contact/', ContactMessageCreateView.as_view(), name='contact-create'),
    path('support/threads/', SupportThreadListView.as_view(), name='support-thread-list'),
    path('support/threads/create/', SupportThreadCreateView.as_view(), name='support-thread-create'),
    path('support/threads/<int:thread_id>/', SupportThreadDetailView.as_view(), name='support-thread-detail'),
    path('support/threads/<int:thread_id>/messages/', SupportMessageCreateView.as_view(), name='support-message-create'),
]
