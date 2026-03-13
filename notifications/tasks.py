# notifications/tasks.py
from celery import shared_task
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
import logging
from django.db.models import F

logger = logging.getLogger(__name__)


@shared_task
def fetch_inbox_emails():
    """Fetch emails for all companies"""
    from companies.models import Company
    from .services import InboxService
    
    companies = Company.objects.filter(smtp_config__isnull=False)
    
    for company in companies:
        try:
            inbox_service = InboxService(company)
            inbox_service.fetch_emails(limit=50)
            logger.info(f"Fetched emails for {company.name}")
        except Exception as e:
            logger.error(f"Failed to fetch emails for {company.name}: {str(e)}")


@shared_task
def generate_daily_analytics():
    """Generate daily email analytics for all companies"""
    from companies.models import Company
    from .models import Email, InboxEmail, EmailAnalytics
    
    yesterday = timezone.now().date() - timedelta(days=1)
    
    companies = Company.objects.all()
    
    for company in companies:
        try:
            emails = Email.objects.filter(
                company=company,
                created_at__date=yesterday
            )
            
            analytics, created = EmailAnalytics.objects.get_or_create(
                company=company,
                date=yesterday,
                defaults={
                    'emails_sent': emails.filter(status='sent').count(),
                    'emails_failed': emails.filter(status='failed').count(),
                    'emails_opened': emails.filter(opened_at__isnull=False).count(),
                    'emails_clicked': emails.filter(clicked_at__isnull=False).count(),
                    'emails_bounced': emails.filter(status='bounced').count(),
                    'emails_received': InboxEmail.objects.filter(
                        company=company,
                        received_at__date=yesterday
                    ).count()
                }
            )
            
            # Calculate rates
            if analytics.emails_sent > 0:
                analytics.open_rate = (analytics.emails_opened / analytics.emails_sent) * 100
                analytics.click_rate = (analytics.emails_clicked / analytics.emails_sent) * 100
                analytics.bounce_rate = (analytics.emails_bounced / analytics.emails_sent) * 100
                analytics.save()
            
            logger.info(f"Generated analytics for {company.name}")
            
        except Exception as e:
            logger.error(f"Failed to generate analytics for {company.name}: {str(e)}")


@shared_task
def retry_failed_emails():
    """Retry failed emails that haven't exceeded max retries"""
    from .models import Email
    from .services import send_email_task
    
    failed_emails = Email.objects.filter(
        status='failed',
        retry_count__lt=F('max_retries')
    )
    
    for email in failed_emails:
        send_email_task.delay(email.id)
        logger.info(f"Retrying email {email.id}")


@shared_task
def cleanup_old_emails():
    """Archive or delete old emails based on retention policy"""
    from .models import Email, InboxEmail
    
    # Delete sent emails older than 1 year
    cutoff_date = timezone.now() - timedelta(days=365)
    
    old_sent = Email.objects.filter(
        sent_at__lt=cutoff_date,
        status='sent'
    )
    count = old_sent.count()
    old_sent.delete()
    
    logger.info(f"Deleted {count} old sent emails")
    
    # Archive inbox emails older than 6 months
    archive_cutoff = timezone.now() - timedelta(days=180)
    
    old_inbox = InboxEmail.objects.filter(
        received_at__lt=archive_cutoff,
        is_archived=False
    )
    old_inbox.update(is_archived=True)
    
    logger.info(f"Archived {old_inbox.count()} old inbox emails")


@shared_task
def send_scheduled_campaigns():
    """Send campaigns that are scheduled for now"""
    from .models import EmailCampaign
    from .services import EmailService
    
    now = timezone.now()
    
    campaigns = EmailCampaign.objects.filter(
        status='scheduled',
        scheduled_at__lte=now
    )
    
    for campaign in campaigns:
        try:
            email_service = EmailService(campaign.company)
            email_service.send_campaign_emails(campaign.id)
            logger.info(f"Sent scheduled campaign: {campaign.name}")
        except Exception as e:
            logger.error(f"Failed to send campaign {campaign.id}: {str(e)}")


@shared_task
def analyze_inbox_with_ai():
    """Analyze unread inbox emails with AI"""
    from .models import InboxEmail
    from .services import AIEmailAssistant
    
    unread_emails = InboxEmail.objects.filter(
        is_read=False,
        ai_summary=''
    )[:50]  # Process 50 at a time
    
    for email in unread_emails:
        try:
            ai_assistant = AIEmailAssistant(email.company, None)
            
            # Generate summary
            summary = ai_assistant.summarize_email(
                email.plain_content or email.html_content
            )
            
            # Analyze sentiment
            analysis = ai_assistant.analyze_email(
                email.plain_content or email.html_content
            )
            
            if analysis['success']:
                email.ai_summary = summary
                email.ai_sentiment = analysis['analysis'].get('sentiment', '')
                email.ai_priority = analysis['analysis'].get('priority', 0)
                email.ai_category = analysis['analysis'].get('category', '')
                email.save()
                
            logger.info(f"Analyzed email {email.id}")
            
        except Exception as e:
            logger.error(f"Failed to analyze email {email.id}: {str(e)}")


@shared_task
def send_recording_ready_notification(meeting_id):
    """Notify company admins that a meeting recording is ready"""
    from meetings.models import Meeting
    from .models import Notification
    
    try:
        meeting = Meeting.objects.get(id=meeting_id)
        
        # Create notification for company admins
        Notification.objects.create(
            company=meeting.company,
            notification_type='recording_ready',
            title=f"Meeting Recording Ready: {meeting.title}",
            message=f"The recording for meeting '{meeting.title}' is now available for viewing.",
            action_url=f"/dashboard/meetings/"
        )
        logger.info(f"Notification sent for meeting {meeting.id} recording ready")
    except Meeting.DoesNotExist:
        logger.error(f"Meeting {meeting_id} not found for recording ready notification")
    except Exception as e:
        logger.error(f"Error sending recording ready notification for meeting {meeting_id}: {str(e)}")
