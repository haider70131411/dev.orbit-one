# notifications/serializers.py
from rest_framework import serializers
from .models import (
    Email, EmailCampaign, EmailTemplate, InboxEmail,
    EmailAttachment, AIEmailDraft, EmailAnalytics, Notification
)
from companies.models import CompanyPerson
from django.utils import timezone as django_timezone
from datetime import datetime
from zoneinfo import ZoneInfo


class EmailAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailAttachment
        fields = ['id', 'filename', 'content_type', 'file_size', 'file', 'created_at']
        read_only_fields = ['file_size', 'created_at']


class EmailSerializer(serializers.ModelSerializer):
    attachments = EmailAttachmentSerializer(many=True, read_only=True)
    from_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Email
        fields = [
            'id', 'from_email', 'from_name', 'from_display',
            'to_email', 'to_name', 'cc_emails', 'bcc_emails',
            'subject', 'html_content', 'plain_content',
            'status', 'sent_at', 'opened_at', 'clicked_at',
            'attachments', 'ai_analysis', 'error_message',
            'created_at'
        ]
        read_only_fields = ['status', 'sent_at', 'opened_at', 'clicked_at', 'created_at']
    
    def get_from_display(self, obj):
        if obj.from_name:
            return f"{obj.from_name} <{obj.from_email}>"
        return obj.from_email


class SendEmailSerializer(serializers.Serializer):
    """Serializer for sending single emails"""
    to_email = serializers.EmailField()
    to_name = serializers.CharField(required=False, allow_blank=True)
    subject = serializers.CharField(max_length=200)
    content = serializers.CharField()
    use_template = serializers.BooleanField(default=False)
    template_id = serializers.IntegerField(required=False, allow_null=True)
    cc_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        default=list
    )
    bcc_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        default=list
    )
    
    def validate(self, data):
        if data.get('use_template') and not data.get('template_id'):
            raise serializers.ValidationError(
                "template_id is required when use_template is True"
            )
        return data


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            'id', 'name', 'template_type', 'subject', 'html_content',
            'ai_tone', 'ai_summary', 'is_active', 'is_default',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class EmailCampaignSerializer(serializers.ModelSerializer):
    recipients_count = serializers.SerializerMethodField()
    open_rate_percent = serializers.SerializerMethodField()
    click_rate_percent = serializers.SerializerMethodField()
    
    # Return date/time in user's timezone (like meetings)
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()
    scheduled_at_utc = serializers.DateTimeField(source='scheduled_at', read_only=True)
    timezone = serializers.CharField(source='user_timezone', read_only=True)
    is_scheduled = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = EmailCampaign
        fields = [
            'id', 'name', 'subject', 'recipient_type', 'recipient_role',
            'html_content', 'plain_content', 'status', 
            'scheduled_date', 'scheduled_time', 'scheduled_at_utc', 'timezone', 'is_scheduled',
            'sent_at', 'total_recipients', 'sent_count', 'failed_count',
            'opened_count', 'clicked_count', 'recipients_count',
            'open_rate_percent', 'click_rate_percent', 'ai_analysis',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'status', 'sent_at', 'total_recipients', 'sent_count',
            'failed_count', 'opened_count', 'clicked_count',
            'created_at', 'updated_at'
        ]
    
    def get_recipients_count(self, obj):
        return obj.get_recipients_list().count()
    
    def get_open_rate_percent(self, obj):
        if obj.sent_count > 0:
            return round((obj.opened_count / obj.sent_count) * 100, 2)
        return 0.0
    
    def get_click_rate_percent(self, obj):
        if obj.sent_count > 0:
            return round((obj.clicked_count / obj.sent_count) * 100, 2)
        return 0.0
    
    def get_scheduled_date(self, obj):
        """Return date in user's timezone"""
        return obj.scheduled_date
    
    def get_scheduled_time(self, obj):
        """Return time in user's timezone"""
        return obj.scheduled_time


class CreateCampaignSerializer(serializers.ModelSerializer):
    recipient_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True
    )
    
    # Accept date and time from frontend (like meetings)
    scheduled_date = serializers.DateField(write_only=True, required=False, allow_null=True)
    scheduled_time = serializers.TimeField(write_only=True, required=False, allow_null=True)
    timezone = serializers.CharField(write_only=True, required=False, default='UTC')
    
    class Meta:
        model = EmailCampaign
        fields = [
            'name', 'subject', 'recipient_type', 'recipient_role',
            'html_content', 'plain_content', 
            'scheduled_date', 'scheduled_time', 'timezone',
            'recipient_ids', 'template'
        ]
    
    def validate_timezone(self, value):
        """Validate timezone string"""
        try:
            ZoneInfo(value)
            return value
        except Exception:
            raise serializers.ValidationError("Invalid timezone")
    
    def validate(self, data):
        """Validate datetime combination and convert to UTC"""
        scheduled_date = data.get('scheduled_date')
        scheduled_time = data.get('scheduled_time')
        timezone_str = data.get('timezone', 'UTC')
        
        # If both date and time are provided, convert to UTC
        if scheduled_date and scheduled_time:
            # Combine date and time
            naive_datetime = datetime.combine(scheduled_date, scheduled_time)
            
            # Convert to user's timezone first, then to UTC for storage
            try:
                user_tz = ZoneInfo(timezone_str)
            except Exception as e:
                raise serializers.ValidationError(f"Invalid timezone: {str(e)}")
            
            # Create timezone-aware datetime in user's timezone
            user_datetime = naive_datetime.replace(tzinfo=user_tz)
            
            # Convert to UTC for storage
            utc_tz = ZoneInfo('UTC')
            utc_datetime = user_datetime.astimezone(utc_tz)
            
            # Check if in the past
            if utc_datetime <= django_timezone.now():
                raise serializers.ValidationError("Scheduled time must be in the future")
            
            # Store the UTC datetime and timezone
            data['scheduled_at'] = utc_datetime
            data['user_timezone'] = timezone_str
            
            # Remove the separate date/time fields
            data.pop('scheduled_date', None)
            data.pop('scheduled_time', None)
            data.pop('timezone', None)
        elif scheduled_date or scheduled_time:
            # If only one is provided, it's invalid
            raise serializers.ValidationError("Both scheduled_date and scheduled_time must be provided together")
        # If neither is provided, campaign is not scheduled (draft)
        
        return data
    
    def create(self, validated_data):
        recipient_ids = validated_data.pop('recipient_ids', [])
        # Remove write-only fields that shouldn't be passed to model
        validated_data.pop('scheduled_date', None)
        validated_data.pop('scheduled_time', None)
        validated_data.pop('timezone', None)
        
        campaign = EmailCampaign.objects.create(**validated_data)
        
        if recipient_ids:
            recipients = CompanyPerson.objects.filter(
                id__in=recipient_ids,
                company=campaign.company
            )
            campaign.recipients.set(recipients)
        
        return campaign


class InboxEmailSerializer(serializers.ModelSerializer):
    from_display = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()
    attachments = EmailAttachmentSerializer(many=True, read_only=True)
    
    class Meta:
        model = InboxEmail
        fields = [
            'id', 'message_id', 'from_email', 'from_name', 'from_display',
            'to_email', 'subject', 'preview', 'html_content', 'plain_content',
            'received_at', 'is_read', 'is_starred', 'is_archived',
            'ai_summary', 'ai_category', 'ai_sentiment', 'ai_priority',
            'thread_id', 'attachments', 'created_at'
        ]
        read_only_fields = ['message_id', 'received_at', 'created_at']
    
    def get_from_display(self, obj):
        if obj.from_name:
            return f"{obj.from_name} <{obj.from_email}>"
        return obj.from_email
    
    def get_preview(self, obj):
        content = obj.plain_content or obj.html_content
        return content[:150] + '...' if len(content) > 150 else content


class AIGenerateEmailSerializer(serializers.Serializer):
    """Serializer for AI email generation"""
    prompt = serializers.CharField()
    tone = serializers.ChoiceField(
        choices=['professional', 'casual', 'formal', 'friendly', 'persuasive'],
        default='professional'
    )
    context = serializers.DictField(required=False, default=dict)


class AIAnalyzeEmailSerializer(serializers.Serializer):
    """Serializer for AI email analysis"""
    content = serializers.CharField()


class AIEmailDraftSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIEmailDraft
        fields = [
            'id', 'prompt', 'subject', 'content', 'tone',
            'model_used', 'tokens_used', 'generation_time',
            'was_used', 'user_rating', 'created_at'
        ]
        read_only_fields = [
            'model_used', 'tokens_used', 'generation_time', 'created_at'
        ]


class EmailAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailAnalytics
        fields = [
            'date', 'emails_sent', 'emails_failed', 'emails_opened',
            'emails_clicked', 'emails_bounced', 'emails_received',
            'open_rate', 'click_rate', 'bounce_rate'
        ]


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for dashboard/system notifications"""
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'action_url',
            'is_read',
            'created_at',
            'time_ago',
        ]
        read_only_fields = ['id', 'created_at', 'time_ago']
    
    def get_time_ago(self, obj):
        """Calculate human-readable time ago"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        diff = now - obj.created_at
        
        if diff < timedelta(minutes=1):
            return "Just now"
        elif diff < timedelta(hours=1):
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes}m ago"
        elif diff < timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}h ago"
        elif diff < timedelta(days=7):
            days = diff.days
            return f"{days}d ago"
        else:
            return obj.created_at.strftime("%b %d")
