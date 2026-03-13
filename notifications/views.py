# Notifications/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone
from django.shortcuts import redirect
from django.db import models
from datetime import timedelta
from .models import (
    Email, EmailCampaign, EmailTemplate, InboxEmail,
    AIEmailDraft, EmailAnalytics, Notification
)
from .serializers import (
    EmailSerializer, EmailCampaignSerializer, EmailTemplateSerializer,
    InboxEmailSerializer, AIEmailDraftSerializer, EmailAnalyticsSerializer,
    SendEmailSerializer, CreateCampaignSerializer, AIGenerateEmailSerializer,
    AIAnalyzeEmailSerializer, NotificationSerializer
)
from .services import EmailService, AIEmailAssistant, InboxService
from .permissions import IsCompanyAdmin
import logging

logger = logging.getLogger(__name__)


class EmailViewSet(viewsets.ModelViewSet):
    """ViewSet for managing sent emails"""
    serializer_class = EmailSerializer
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def check_smtp_config(self):
        """Check if company has SMTP configuration"""
        if not self.request.user.company.has_smtp_config():
            return Response(
                {
                    'error': 'SMTP configuration not found',
                    'message': 'To use this feature, please create SMTP configuration first.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        return None
    
    def get_queryset(self):
        queryset = Email.objects.filter(
            company=self.request.user.company
        ).select_related('campaign', 'company').prefetch_related('attachments')
        
        # Add metadata about SMTP status
        if not self.request.user.company.has_smtp_config():
            # Still return queryset but frontend can check for SMTP warning
            pass
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """List emails with SMTP status check"""
        response = super().list(request, *args, **kwargs)
        
        # Add SMTP status to response metadata
        if not request.user.company.has_smtp_config():
            response.data['smtp_warning'] = {
                'message': 'To send emails, please create SMTP configuration first.',
                'has_smtp': False
            }
        else:
            response.data['smtp_warning'] = {
                'has_smtp': True
            }
        
        return response
    
    @action(detail=False, methods=['post'])
    def send(self, request):
        """Send a single email"""
        # Check SMTP configuration
        smtp_check = self.check_smtp_config()
        if smtp_check:
            return smtp_check
        
        serializer = SendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            email_service = EmailService(request.user.company)
            
            # Get content
            if serializer.validated_data.get('use_template'):
                template = get_object_or_404(
                    EmailTemplate,
                    id=serializer.validated_data['template_id'],
                    company=request.user.company
                )
                html_content = email_service.create_branded_html(
                    template.html_content
                )
            else:
                html_content = email_service.create_branded_html(
                    serializer.validated_data['content']
                )
            
            # Send email
            email = email_service.send_single_email(
                to_email=serializer.validated_data['to_email'],
                to_name=serializer.validated_data.get('to_name', ''),
                subject=serializer.validated_data['subject'],
                html_content=html_content,
                cc=serializer.validated_data.get('cc_emails', []),
                bcc=serializer.validated_data.get('bcc_emails', []),
                created_by=request.user
            )
            
            return Response(
                EmailSerializer(email).data,
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            logger.error(f"Email send failed: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get email statistics"""
        queryset = self.get_queryset()
        
        stats = {
            'total': queryset.count(),
            'sent': queryset.filter(status='sent').count(),
            'failed': queryset.filter(status='failed').count(),
            'opened': queryset.filter(opened_at__isnull=False).count(),
            'clicked': queryset.filter(clicked_at__isnull=False).count(),
        }
        
        # Calculate rates
        if stats['sent'] > 0:
            stats['open_rate'] = round((stats['opened'] / stats['sent']) * 100, 2)
            stats['click_rate'] = round((stats['clicked'] / stats['sent']) * 100, 2)
        else:
            stats['open_rate'] = 0.0
            stats['click_rate'] = 0.0
        
        return Response(stats)


class EmailCampaignViewSet(viewsets.ModelViewSet):
    """ViewSet for managing email campaigns"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateCampaignSerializer
        return EmailCampaignSerializer
    
    def get_queryset(self):
        return EmailCampaign.objects.filter(
            company=self.request.user.company
        ).select_related('company').prefetch_related('recipients')
    
    def list(self, request, *args, **kwargs):
        """List campaigns with SMTP status check"""
        response = super().list(request, *args, **kwargs)
        
        # Add SMTP status to response metadata
        if not request.user.company.has_smtp_config():
            response.data['smtp_warning'] = {
                'message': 'To send campaigns, please create SMTP configuration first.',
                'has_smtp': False
            }
        else:
            response.data['smtp_warning'] = {
                'has_smtp': True
            }
        
        return response
    
    def perform_create(self, serializer):
        serializer.save(
            company=self.request.user.company,
            created_by=self.request.user
        )
    
    def check_smtp_config(self):
        """Check if company has SMTP configuration"""
        if not self.request.user.company.has_smtp_config():
            return Response(
                {
                    'error': 'SMTP configuration not found',
                    'message': 'To use this feature, please create SMTP configuration first.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        return None
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Send campaign emails"""
        # Check SMTP configuration
        smtp_check = self.check_smtp_config()
        if smtp_check:
            return smtp_check
        
        campaign = self.get_object()
        
        if campaign.status not in ['draft', 'failed']:
            return Response(
                {'error': 'Campaign already sent or in progress'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            email_service = EmailService(request.user.company)
            email_service.send_campaign_emails(campaign.id)
            
            return Response(
                {'message': 'Campaign sending initiated'},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Campaign send failed: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause campaign"""
        campaign = self.get_object()
        campaign.status = 'paused'
        campaign.save()
        return Response({'message': 'Campaign paused'})
    
    @action(detail=True, methods=['get'])
    def emails(self, request, pk=None):
        """Get all emails in campaign"""
        campaign = self.get_object()
        emails = campaign.emails.all()
        serializer = EmailSerializer(emails, many=True)
        return Response(serializer.data)


class EmailTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing email templates"""
    serializer_class = EmailTemplateSerializer
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get_queryset(self):
        return EmailTemplate.objects.filter(
            company=self.request.user.company
        )
    
    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
    
    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        """Preview template with sample data - returns complete email with base_email.html wrapper"""
        template = self.get_object()
        
        # Sample context for template rendering
        context = {
            'person': {
                'name': 'John Doe',
                'email': 'john@example.com'
            },
            'company': request.user.company
        }
        
        # First, render the template content with sample data
        rendered_content = template.render(context)
        
        # Then wrap it in base_email.html to show complete preview
        # This is how it will look when actually sent
        try:
            email_service = EmailService(request.user.company)
            complete_preview = email_service.create_branded_html(rendered_content)
        except ValueError:
            # If SMTP not configured, still show preview but without EmailService
            # Use render_to_string directly
            from django.template.loader import render_to_string
            from django.utils import timezone
            preview_context = {
                'company': request.user.company,
                'content': rendered_content,
                'logo_url': request.user.company.logo.url if request.user.company.logo else None,
                'company_address': f"{request.user.company.address_street}, {request.user.company.address_city}" if request.user.company.address_street else None,
                'current_year': timezone.now().year,
                'subject': template.subject,
                'unsubscribe_url': '#'
            }
            complete_preview = render_to_string('emails/base_email.html', preview_context)
        
        return Response({
            'preview': complete_preview,
            'subject': template.subject
        })


class InboxViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for inbox emails"""
    serializer_class = InboxEmailSerializer
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def check_smtp_config(self):
        """Check if company has SMTP configuration"""
        if not self.request.user.company.has_smtp_config():
            return Response(
                {
                    'error': 'SMTP configuration not found',
                    'message': 'To use this feature, please create SMTP configuration first.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        return None
    
    def get_queryset(self):
        queryset = InboxEmail.objects.filter(
            company=self.request.user.company
        ).select_related('company').prefetch_related('attachments')
        
        # Filters
        if self.request.query_params.get('unread') == 'true':
            queryset = queryset.filter(is_read=False)
        if self.request.query_params.get('starred') == 'true':
            queryset = queryset.filter(is_starred=True)
        if self.request.query_params.get('archived') == 'true':
            queryset = queryset.filter(is_archived=True)
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """List inbox emails with SMTP status check"""
        response = super().list(request, *args, **kwargs)
        
        # Add SMTP status to response metadata
        if not request.user.company.has_smtp_config():
            response.data['smtp_warning'] = {
                'message': 'To fetch emails, please create SMTP configuration first.',
                'has_smtp': False
            }
        else:
            response.data['smtp_warning'] = {
                'has_smtp': True
            }
        
        return response
    
    @action(detail=False, methods=['post'])
    def fetch(self, request):
        """Fetch new emails from server"""
        # Check SMTP configuration
        smtp_check = self.check_smtp_config()
        if smtp_check:
            return smtp_check
        
        try:
            inbox_service = InboxService(request.user.company)
            inbox_service.fetch_emails()
            
            return Response(
                {'message': 'Emails fetched successfully'},
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Inbox fetch failed: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark email as read"""
        email = self.get_object()
        email.is_read = True
        email.save()
        return Response({'message': 'Marked as read'})
    
    @action(detail=True, methods=['post'])
    def mark_unread(self, request, pk=None):
        """Mark email as unread"""
        email = self.get_object()
        email.is_read = False
        email.save()
        return Response({'message': 'Marked as unread'})
    
    @action(detail=True, methods=['post'])
    def toggle_star(self, request, pk=None):
        """Toggle star status"""
        email = self.get_object()
        email.is_starred = not email.is_starred
        email.save()
        return Response({'is_starred': email.is_starred})
    
    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive email"""
        email = self.get_object()
        email.is_archived = True
        email.save()
        return Response({'message': 'Email archived'})


class AIEmailViewSet(viewsets.ViewSet):
    """ViewSet for AI email assistance"""
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    @action(detail=False, methods=['post'])
    def generate(self, request):
        """Generate email content using AI"""
        serializer = AIGenerateEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            ai_assistant = AIEmailAssistant(
                request.user.company,
                request.user
            )
            
            result = ai_assistant.generate_email(
                prompt=serializer.validated_data['prompt'],
                context=serializer.validated_data.get('context'),
                tone=serializer.validated_data['tone']
            )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"AI generation failed: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def analyze(self, request):
        """Analyze email content"""
        serializer = AIAnalyzeEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            ai_assistant = AIEmailAssistant(
                request.user.company,
                request.user
            )
            
            result = ai_assistant.analyze_email(
                serializer.validated_data['content']
            )
            
            if result['success']:
                return Response(result, status=status.HTTP_200_OK)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"AI analysis failed: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def drafts(self, request):
        """Get AI-generated drafts"""
        drafts = AIEmailDraft.objects.filter(
            company=request.user.company,
            user=request.user
        )[:20]
        
        serializer = AIEmailDraftSerializer(drafts, many=True)
        return Response(serializer.data)


class EmailAnalyticsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for email analytics"""
    serializer_class = EmailAnalyticsSerializer
    permission_classes = [IsAuthenticated, IsCompanyAdmin]
    
    def get_queryset(self):
        return EmailAnalytics.objects.filter(
            company=self.request.user.company
        ).order_by('-date')
    
    @action(detail=False, methods=['get'])
    
    def summary(self, request):
        """Get analytics summary"""
        days = int(request.query_params.get('days', 30))
        start_date = timezone.now().date() - timedelta(days=days)
        
        analytics = EmailAnalytics.objects.filter(
            company=request.user.company,
            date__gte=start_date
        ).aggregate(
            total_sent=models.Sum('emails_sent'),
            total_opened=models.Sum('emails_opened'),
            total_clicked=models.Sum('emails_clicked'),
            total_failed=models.Sum('emails_failed'),
            total_bounced=models.Sum('emails_bounced'),
            avg_open_rate=models.Avg('open_rate'),
            avg_click_rate=models.Avg('click_rate')
        )
        
        return Response(analytics)


# Tracking views (no authentication required)
from django.views import View
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class EmailTrackingView(View):
    """Track email opens - No authentication required"""
    
    def get(self, request, tracking_id):
        logger.info(f"Tracking pixel accessed for tracking_id: {tracking_id} from IP: {request.META.get('REMOTE_ADDR', 'unknown')}")
        try:
            email = Email.objects.get(tracking_id=tracking_id)
            logger.info(f"Email found: ID={email.id}, to={email.to_email}, opened_at={email.opened_at}, status={email.status}")
            
            # Mark as opened (only if not already opened to avoid duplicate updates)
            if not email.opened_at:
                email.mark_as_opened()
                # Refresh from DB to get updated timestamp
                email.refresh_from_db()
                logger.info(f"✅ Email {email.id} marked as opened via tracking pixel at {email.opened_at}")
            else:
                logger.info(f"Email {email.id} already opened at {email.opened_at}")
        except Email.DoesNotExist:
            logger.warning(f"❌ Tracking pixel accessed for non-existent email: {tracking_id}")
        except Exception as e:
            logger.error(f"❌ Error tracking email open: {str(e)}", exc_info=True)
        
        # Return 1x1 transparent pixel (GIF)
        pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
        response = HttpResponse(pixel, content_type='image/gif')
        # Add cache headers to prevent caching
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        # Allow CORS for email clients
        response['Access-Control-Allow-Origin'] = '*'
        return response


@method_decorator(csrf_exempt, name='dispatch')
class EmailLinkTrackingView(View):
    """Track email link clicks - No authentication required"""
    
    def get(self, request, tracking_id):
        try:
            email = Email.objects.get(tracking_id=tracking_id)
            # Mark as clicked (only if not already clicked to avoid duplicate updates)
            if not email.clicked_at:
                email.mark_as_clicked()
                logger.info(f"Email {email.id} marked as clicked via tracking link")
            
            # Redirect to actual URL
            url = request.GET.get('url', '/')
            # Validate URL to prevent open redirects
            if url.startswith('http://') or url.startswith('https://'):
                return redirect(url)
            else:
                # Relative URL or invalid - redirect to home
                return redirect('/')
            
        except Email.DoesNotExist:
            logger.warning(f"Tracking link accessed for non-existent email: {tracking_id}")
            return redirect('/')
        except Exception as e:
            logger.error(f"Error tracking email click: {str(e)}")
            # Still redirect even if tracking fails
            url = request.GET.get('url', '/')
            if url.startswith('http://') or url.startswith('https://'):
                return redirect(url)
            return redirect('/')


# Dashboard Notification Views
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination

class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_list_view(request):
    """Get all notifications for the company"""
    try:
        company = request.user.company
        notifications = Notification.objects.filter(company=company)
        
        # Filter by read status if specified
        is_read = request.query_params.get('is_read')
        if is_read is not None:
            notifications = notifications.filter(is_read=is_read.lower() == 'true')
        
        paginator = NotificationPagination()
        page = paginator.paginate_queryset(notifications, request)
        
        serializer = NotificationSerializer(page if page is not None else notifications, many=True)
        return paginator.get_paginated_response(serializer.data) if page is not None else Response({
            'count': notifications.count(),
            'next': None,
            'previous': None,
            'results': serializer.data
        })
    
    except Exception as e:
        logger.error(f"Error fetching notifications: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_unread_count_view(request):
    """Get count of unread notifications"""
    try:
        company = request.user.company
        count = Notification.objects.filter(
            company=company,
            is_read=False
        ).count()
        
        return Response({'unread_count': count})
    
    except Exception as e:
        logger.error(f"Error fetching unread count: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def notification_mark_read_view(request, notification_id):
    """Mark a notification as read"""
    try:
        company = request.user.company
        notification = Notification.objects.get(
            id=notification_id,
            company=company
        )
        notification.mark_as_read()
        
        serializer = NotificationSerializer(notification)
        return Response(serializer.data)
    
    except Notification.DoesNotExist:
        return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def notification_mark_all_read_view(request):
    """Mark all notifications as read"""
    try:
        company = request.user.company
        updated = Notification.objects.filter(
            company=company,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())
        
        return Response({'marked_read': updated})
    
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def notification_delete_view(request, notification_id):
    """Delete a notification"""
    try:
        company = request.user.company
        notification = Notification.objects.get(
            id=notification_id,
            company=company
        )
        notification.delete()
        
        return Response({'message': 'Notification deleted'})
    
    except Notification.DoesNotExist:
        return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
