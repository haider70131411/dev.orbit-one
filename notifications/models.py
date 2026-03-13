# notification/models.py
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from companies.models import Company, CompanyPerson
import json


class EmailTemplate(models.Model):
    """Reusable email templates with company branding"""
    TEMPLATE_TYPES = (
        ('invitation', 'Interview Invitation'),
        ('reminder', 'Interview Reminder'),
        ('feedback', 'Interview Feedback'),
        ('rejection', 'Rejection Letter'),
        ('offer', 'Job Offer'),
        ('welcome', 'Welcome Email'),
        ('notification', 'General Notification'),
        ('custom', 'Custom Template'),
    )
    
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='email_templates'
    )
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    subject = models.CharField(max_length=200)
    html_content = models.TextField(help_text="HTML email content with {{variables}}")
    
    # AI-generated metadata
    ai_tone = models.CharField(max_length=50, blank=True, help_text="e.g., professional, friendly, formal")
    ai_summary = models.TextField(blank=True, help_text="AI-generated summary of template")
    
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['company', 'name']
    
    def __str__(self):
        return f"{self.company.name} - {self.name}"
    
    def render(self, context):
        """Render template with context"""
        from django.template import Template, Context
        template = Template(self.html_content)
        return template.render(Context(context))


class EmailCampaign(models.Model):
    """Email campaigns for bulk sending"""
    CAMPAIGN_STATUS = (
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('paused', 'Paused'),
        ('failed', 'Failed'),
    )
    
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='email_campaigns'
    )
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)
    
    # Recipients
    recipient_type = models.CharField(
        max_length=20,
        choices=[
            ('all', 'All Company People'),
            ('role', 'Specific Role'),
            ('custom', 'Custom Selection'),
        ],
        default='custom'
    )
    recipient_role = models.CharField(max_length=20, blank=True, null=True)
    recipients = models.ManyToManyField(
        CompanyPerson, 
        related_name='email_campaigns',
        blank=True
    )
    
    # Content
    template = models.ForeignKey(
        EmailTemplate, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    html_content = models.TextField()
    plain_content = models.TextField(blank=True)
    
    # AI metadata
    ai_generated = models.BooleanField(default=False)
    ai_analysis = models.JSONField(default=dict, blank=True, help_text="AI analysis results")
    
    # Scheduling - Store as timezone-aware datetime (UTC in DB)
    status = models.CharField(max_length=20, choices=CAMPAIGN_STATUS, default='draft')
    scheduled_at = models.DateTimeField(null=True, blank=True)  # Store in UTC in DB
    user_timezone = models.CharField(max_length=50, default='UTC')  # User's display timezone
    sent_at = models.DateTimeField(null=True, blank=True)
    
    # Statistics
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    opened_count = models.IntegerField(default=0)
    clicked_count = models.IntegerField(default=0)
    
    created_by = models.ForeignKey(
        'accounts.User', 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='created_campaigns'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} - {self.get_status_display()}"
    
    def get_recipients_list(self):
        """Get list of recipients based on recipient_type"""
        if self.recipient_type == 'all':
            return self.company.people.all()
        elif self.recipient_type == 'role':
            return self.company.people.filter(role=self.recipient_role)
        else:
            return self.recipients.all()
    
    def get_scheduled_at_in_timezone(self, tz_string=None):
        """
        Convert scheduled_at to user's timezone.
        If tz_string not provided, use the campaign's user_timezone.
        """
        if not self.scheduled_at:
            return None
        
        target_tz = tz_string or self.user_timezone
        try:
            from zoneinfo import ZoneInfo
            user_tz = ZoneInfo(target_tz)
            return self.scheduled_at.astimezone(user_tz)
        except Exception:
            # Fallback to UTC if timezone is invalid
            return self.scheduled_at
    
    @property
    def scheduled_date(self):
        """Return date in user's timezone"""
        if not self.scheduled_at:
            return None
        dt = self.get_scheduled_at_in_timezone()
        return dt.date() if dt else None
    
    @property
    def scheduled_time(self):
        """Return time in user's timezone"""
        if not self.scheduled_at:
            return None
        dt = self.get_scheduled_at_in_timezone()
        return dt.time() if dt else None
    
    @property
    def is_scheduled(self):
        """Check if campaign is scheduled for future"""
        if not self.scheduled_at:
            return False
        from django.utils import timezone
        return self.scheduled_at > timezone.now()
    
    def update_statistics(self):
        """Update campaign statistics"""
        emails = self.emails.all()
        self.total_recipients = emails.count()
        self.sent_count = emails.filter(status='sent').count()
        self.failed_count = emails.filter(status='failed').count()
        self.opened_count = emails.filter(opened_at__isnull=False).count()
        self.clicked_count = emails.filter(clicked_at__isnull=False).count()
        self.save(update_fields=[
            'total_recipients', 'sent_count', 'failed_count', 
            'opened_count', 'clicked_count'
        ])


class Email(models.Model):
    """Individual email records"""
    EMAIL_STATUS = (
        ('draft', 'Draft'),
        ('queued', 'Queued'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('bounced', 'Bounced'),
    )
    
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='emails'
    )
    campaign = models.ForeignKey(
        EmailCampaign, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='emails'
    )
    
    # Sender & Recipient
    from_email = models.EmailField()
    from_name = models.CharField(max_length=100, blank=True)
    to_email = models.EmailField()
    to_name = models.CharField(max_length=100, blank=True)
    cc_emails = models.JSONField(default=list, blank=True)
    bcc_emails = models.JSONField(default=list, blank=True)
    
    # Content
    subject = models.CharField(max_length=200)
    html_content = models.TextField()
    plain_content = models.TextField(blank=True)
    
    # AI Features
    ai_generated = models.BooleanField(default=False)
    ai_analysis = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Sentiment, tone, readability scores"
    )
    ai_suggestions = models.JSONField(default=list, blank=True)
    
    # Tracking
    status = models.CharField(max_length=20, choices=EMAIL_STATUS, default='draft')
    tracking_id = models.UUIDField(unique=True, null=True, blank=True)
    
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    
    # Error handling
    error_message = models.TextField(blank=True)
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    # Metadata
    created_by = models.ForeignKey(
        'accounts.User', 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='sent_emails'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['to_email', '-created_at']),
            models.Index(fields=['tracking_id']),
        ]
    
    def __str__(self):
        return f"{self.subject} to {self.to_email}"
    
    def mark_as_opened(self):
        """Mark email as opened"""
        if not self.opened_at:
            from django.utils import timezone
            self.opened_at = timezone.now()
            self.save(update_fields=['opened_at'])
            # Also update status if still queued/sending
            if self.status in ['queued', 'sending', 'sent']:
                self.save(update_fields=['opened_at', 'status'])
            if self.campaign:
                self.campaign.update_statistics()
    
    def mark_as_clicked(self):
        """Mark email as clicked"""
        if not self.clicked_at:
            self.clicked_at = timezone.now()
            self.save(update_fields=['clicked_at'])
            if self.campaign:
                self.campaign.update_statistics()
    
    def mark_as_bounced(self, reason=""):
        """Mark email as bounced"""
        self.status = 'bounced'
        self.bounced_at = timezone.now()
        self.error_message = reason
        self.save(update_fields=['status', 'bounced_at', 'error_message'])
        if self.campaign:
            self.campaign.update_statistics()


class InboxEmail(models.Model):
    """Store received emails via IMAP/POP3"""
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='inbox_emails'
    )
    
    # Email headers
    message_id = models.CharField(max_length=255, unique=True)
    from_email = models.EmailField()
    from_name = models.CharField(max_length=100, blank=True)
    to_email = models.EmailField()
    subject = models.CharField(max_length=500)
    
    # Content
    html_content = models.TextField(blank=True)
    plain_content = models.TextField(blank=True)
    
    # Metadata
    received_at = models.DateTimeField()
    is_read = models.BooleanField(default=False)
    is_starred = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    
    # AI Analysis
    ai_summary = models.TextField(blank=True, help_text="AI-generated summary")
    ai_category = models.CharField(max_length=50, blank=True)
    ai_sentiment = models.CharField(max_length=20, blank=True)
    ai_priority = models.IntegerField(default=0, help_text="0-10 priority score")
    
    # Threading
    thread_id = models.CharField(max_length=255, blank=True)
    in_reply_to = models.CharField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['company', '-received_at']),
            models.Index(fields=['message_id']),
            models.Index(fields=['thread_id']),
        ]
    
    def __str__(self):
        return f"{self.subject} from {self.from_email}"


class EmailAttachment(models.Model):
    """Email attachments"""
    email = models.ForeignKey(
        Email, 
        on_delete=models.CASCADE, 
        related_name='attachments',
        null=True,
        blank=True
    )
    inbox_email = models.ForeignKey(
        InboxEmail, 
        on_delete=models.CASCADE, 
        related_name='attachments',
        null=True,
        blank=True
    )
    
    file = models.FileField(upload_to='email_attachments/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    file_size = models.IntegerField(help_text="Size in bytes")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['filename']
    
    def __str__(self):
        return self.filename


class AIEmailDraft(models.Model):
    """AI-generated email drafts"""
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='ai_drafts'
    )
    user = models.ForeignKey(
        'accounts.User', 
        on_delete=models.CASCADE,
        related_name='ai_drafts'
    )
    
    # Generation parameters
    prompt = models.TextField(help_text="User's prompt for AI")
    context = models.JSONField(default=dict, blank=True, help_text="Additional context")
    
    # Generated content
    subject = models.CharField(max_length=200)
    content = models.TextField()
    tone = models.CharField(max_length=50)
    
    # AI metadata
    model_used = models.CharField(max_length=50, default='gpt-4')
    tokens_used = models.IntegerField(default=0)
    generation_time = models.FloatField(help_text="Time in seconds")
    
    # User feedback
    was_used = models.BooleanField(default=False)
    user_rating = models.IntegerField(null=True, blank=True, help_text="1-5 rating")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Draft: {self.subject[:50]}"


class EmailAnalytics(models.Model):
    """Daily email analytics aggregation"""
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        related_name='email_analytics'
    )
    date = models.DateField()
    
    # Counts
    emails_sent = models.IntegerField(default=0)
    emails_failed = models.IntegerField(default=0)
    emails_opened = models.IntegerField(default=0)
    emails_clicked = models.IntegerField(default=0)
    emails_bounced = models.IntegerField(default=0)
    emails_received = models.IntegerField(default=0)
    
    # Rates (percentages)
    open_rate = models.FloatField(default=0.0)
    click_rate = models.FloatField(default=0.0)
    bounce_rate = models.FloatField(default=0.0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
        unique_together = ['company', 'date']
    
    def __str__(self):
        return f"{self.company.name} - {self.date}"


class Notification(models.Model):
    """Dashboard/System notifications for companies"""
    NOTIFICATION_TYPES = (
        ('meeting_starting', 'Meeting Starting Soon'),
        ('meeting_started', 'Meeting Started'),
        ('meeting_ended', 'Meeting Ended'),
        ('meeting_cancelled', 'Meeting Cancelled'),
        ('meeting_rescheduled', 'Meeting Rescheduled'),
        ('meeting_invitation', 'New Meeting Invitation'),
        ('avatar_added', 'New Avatar Added'),
        ('avatar_updated', 'Avatar Updated'),
        ('email_sent', 'Email Campaign Sent'),
        ('email_completed', 'Email Campaign Completed'),
        ('feedback_received', 'New Feedback Received'),
        ('feedback_submitted', 'Feedback Submitted'),
        ('company_approved', 'Company Approved'),
        ('company_rejected', 'Company Rejected'),
        ('interviewer_added', 'New Interviewer Added'),
        ('recording_ready', 'Meeting Recording Ready'),
        ('support_reply', 'Support Chat Reply'),
        ('system', 'System Notification'),
    )
    
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    
    notification_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES
    )
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Optional: link to related object
    related_object_type = models.CharField(max_length=50, null=True, blank=True)
    related_object_id = models.IntegerField(null=True, blank=True)
    
    # Optional: action URL
    action_url = models.CharField(max_length=500, null=True, blank=True)
    
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', '-created_at']),
            models.Index(fields=['company', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.company.name}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()
