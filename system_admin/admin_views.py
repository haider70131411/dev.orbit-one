# system_admin/admin_views.py
# Admin dashboard API views - Overview, Companies, Meetings (global scope)

from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.mail import send_mail

from system_admin.permissions import IsSuperAdmin
from system_admin.serializers import (
    AdminCompanyListSerializer,
    AdminCompanyDetailSerializer,
    AdminMeetingListSerializer,
    AdminMeetingDetailSerializer,
)
from companies.models import Company
from meetings.models import Meeting
from accounts.models import User
from avatars.models import Avatar
from notifications.models import Email, EmailAnalytics
from shared.models import ContactMessage, SupportThread, SupportMessage
from notifications.utils import notify_support_reply
from shared.serializers import (
    ContactMessageDetailSerializer,
    SupportThreadSerializer,
    SupportThreadListSerializer,
    SupportMessageSerializer,
)


class AdminOverviewView(APIView):
    """GET /api/system/overview/ - Global dashboard stats for super admins"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Users
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()

        # Companies
        companies_qs = Company.objects.all()
        total_companies = companies_qs.count()
        pending_companies = companies_qs.filter(status='pending').count()
        approved_companies = companies_qs.filter(status='approved').count()
        rejected_companies = companies_qs.filter(status='rejected').count()

        # Meetings
        meetings_qs = Meeting.objects.all()
        total_meetings = meetings_qs.count()
        today_meetings = meetings_qs.filter(scheduled_datetime__date=today_start.date()).count()
        in_progress_meetings = meetings_qs.filter(status='in_progress').count()
        scheduled_meetings = meetings_qs.filter(status='scheduled').count()
        completed_meetings = meetings_qs.filter(status='completed').count()

        # Avatars
        total_avatars = Avatar.objects.filter(is_active=True).count()

        # Email stats (today)
        today_emails_sent = Email.objects.filter(
            status='sent',
            sent_at__gte=today_start
        ).count()
        today_emails_failed = Email.objects.filter(
            status='failed',
            created_at__gte=today_start
        ).count()

        # Recent analytics (last 7 days aggregate)
        from datetime import timedelta
        from django.db.models import Sum
        week_ago = today_start - timedelta(days=7)
        recent_analytics = EmailAnalytics.objects.filter(
            date__gte=week_ago.date()
        ).aggregate(
            total_sent=Sum('emails_sent'),
            total_opened=Sum('emails_opened'),
            total_clicked=Sum('emails_clicked'),
        )

        data = {
            'users': {
                'total': total_users,
                'active': active_users,
            },
            'companies': {
                'total': total_companies,
                'pending': pending_companies,
                'approved': approved_companies,
                'rejected': rejected_companies,
            },
            'meetings': {
                'total': total_meetings,
                'today': today_meetings,
                'in_progress': in_progress_meetings,
                'scheduled': scheduled_meetings,
                'completed': completed_meetings,
            },
            'avatars': total_avatars,
            'emails': {
                'today_sent': today_emails_sent,
                'today_failed': today_emails_failed,
                'week_sent': recent_analytics.get('total_sent', 0) or 0,
                'week_opened': recent_analytics.get('total_opened', 0) or 0,
                'week_clicked': recent_analytics.get('total_clicked', 0) or 0,
            },
        }
        return Response(data)


class AdminCompanyListView(ListAPIView):
    """GET /api/system/companies/ - List all companies (super admin only)"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = AdminCompanyListSerializer
    queryset = Company.objects.all().select_related('admin_user').annotate(
        meetings_count=Count('meetings')
    ).order_by('-created_at')

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(support_email__icontains=search)
            )
        return qs


class AdminCompanyDetailView(RetrieveAPIView):
    """GET /api/system/companies/<id>/ - Company detail (super admin only)"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = AdminCompanyDetailSerializer
    queryset = Company.objects.all()
    lookup_url_kwarg = 'id'
    lookup_field = 'id'


class AdminMeetingListView(ListAPIView):
    """GET /api/system/meetings/ - List all meetings (super admin only)"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = AdminMeetingListSerializer
    queryset = Meeting.objects.all().select_related('company').prefetch_related('interviewers').order_by('-scheduled_datetime')

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        company_id = self.request.query_params.get('company_id')
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs


class AdminMeetingDetailView(RetrieveAPIView):
    """GET /api/system/meetings/<uuid>/ - Meeting detail (super admin only)"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = AdminMeetingDetailSerializer
    queryset = Meeting.objects.all().select_related('company').prefetch_related('interviewers', 'participants', 'feedbacks')
    lookup_url_kwarg = 'id'
    lookup_field = 'id'


class AdminContactMessageListView(ListAPIView):
    """
    GET /api/system/contact-messages/ - List all contact-us messages
    Optional filters:
      ?is_replied=true/false
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = ContactMessageDetailSerializer
    queryset = ContactMessage.objects.all().order_by('-created_at')

    def get_queryset(self):
        qs = super().get_queryset()
        is_replied = self.request.query_params.get('is_replied')
        if is_replied is not None:
            value = str(is_replied).lower() in ['true', '1', 'yes']
            qs = qs.filter(is_replied=value)
        return qs


class AdminContactMessageReplyView(APIView):
    """
    POST /api/system/contact-messages/<id>/reply/
    Body: { "reply_message": "..." }
    Marks message as replied, stores reply text, sends reply email.
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, id):
        contact = get_object_or_404(ContactMessage, id=id)
        reply_message = (request.data.get('reply_message') or '').strip()

        if not reply_message:
            return Response(
                {"error": "reply_message is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update model fields
        contact.reply_message = reply_message
        contact.is_replied = True
        contact.replied_at = timezone.now()
        contact.save(update_fields=['reply_message', 'is_replied', 'replied_at'])

        # Send email response to the sender
        try:
            subject = "Re: Your contact request"
            body = (
                f"Hi {contact.full_name},\n\n"
                f"Thank you for reaching out to us. Here is our response to your message:\n\n"
                f"Your original message:\n{contact.message}\n\n"
                f"Our reply:\n{reply_message}\n\n"
                f"Best regards,\nOrbitOne Support"
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=None,  # uses DEFAULT_FROM_EMAIL
                recipient_list=[contact.email],
                fail_silently=False,
            )
        except Exception:
            # Log in real app; do not fail the API because of email issues
            pass

        serializer = ContactMessageDetailSerializer(contact)
        return Response(serializer.data, status=status.HTTP_200_OK)


# --- Support Chat (admin) ---

class AdminSupportThreadListView(ListAPIView):
    """GET /api/system/support/threads/ - List all support threads"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = SupportThreadListSerializer
    queryset = SupportThread.objects.all().select_related('user', 'company').prefetch_related('messages').order_by('-updated_at')

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs


class AdminSupportThreadDetailView(RetrieveAPIView):
    """GET /api/system/support/threads/<id>/ - Thread detail with messages"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    serializer_class = SupportThreadSerializer
    queryset = SupportThread.objects.all().prefetch_related('messages')
    lookup_url_kwarg = 'id'
    lookup_field = 'id'

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Mark user messages as read when admin views the thread
        instance.messages.filter(sender_type='user', is_read=False).update(is_read=True)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class AdminSupportUnreadCountView(APIView):
    """GET /api/system/support/unread-count/ - Count of unread messages from company admins"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        count = SupportMessage.objects.filter(sender_type='user', is_read=False).count()
        return Response({'unread_count': count})


class AdminSupportMessageCreateView(APIView):
    """POST /api/system/support/threads/<id>/messages/ - Admin reply"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, id):
        thread = get_object_or_404(SupportThread, id=id)
        msg_text = (request.data.get('message') or '').strip()
        if not msg_text:
            return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)
        SupportMessage.objects.create(thread=thread, sender_type='admin', message=msg_text)
        # Mark user messages as read
        thread.messages.filter(sender_type='user').update(is_read=True)
        thread.save()
        # Notify company admin of admin reply
        if thread.company:
            preview = msg_text[:80] + '...' if len(msg_text) > 80 else msg_text
            notify_support_reply(thread.company, thread.id, preview=preview)
        serializer = SupportThreadSerializer(thread)
        return Response(serializer.data, status=status.HTTP_200_OK)
