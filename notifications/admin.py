# notifications/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Email, EmailCampaign, EmailTemplate, InboxEmail,
    EmailAttachment, AIEmailDraft, EmailAnalytics, Notification
)


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = [
        'subject', 'to_email', 'status', 'company',
        'sent_at', 'opened_badge', 'clicked_badge'
    ]
    list_filter = ['status', 'company', 'sent_at', 'ai_generated']
    search_fields = ['subject', 'to_email', 'from_email']
    readonly_fields = ['tracking_id', 'sent_at', 'opened_at', 'clicked_at', 'created_at']
    
    fieldsets = (
        ('Email Information', {
            'fields': ('company', 'campaign', 'subject', 'status')
        }),
        ('Sender & Recipients', {
            'fields': (
                'from_email', 'from_name', 'to_email', 'to_name',
                'cc_emails', 'bcc_emails'
            )
        }),
        ('Content', {
            'fields': ('html_content', 'plain_content')
        }),
        ('AI Features', {
            'fields': ('ai_generated', 'ai_analysis', 'ai_suggestions'),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('tracking_id', 'sent_at', 'opened_at', 'clicked_at'),
            'classes': ('collapse',)
        }),
        ('Error Handling', {
            'fields': ('error_message', 'retry_count', 'max_retries'),
            'classes': ('collapse',)
        })
    )
    
    def opened_badge(self, obj):
        if obj.opened_at:
            return format_html(
                '<span style="background-color: #48bb78; color: white; '
                'padding: 3px 10px; border-radius: 3px;">✓ Opened</span>'
            )
        return format_html(
            '<span style="background-color: #e2e8f0; color: #4a5568; '
            'padding: 3px 10px; border-radius: 3px;">Not Opened</span>'
        )
    opened_badge.short_description = 'Opened'
    
    def clicked_badge(self, obj):
        if obj.clicked_at:
            return format_html(
                '<span style="background-color: #4299e1; color: white; '
                'padding: 3px 10px; border-radius: 3px;">✓ Clicked</span>'
            )
        return format_html(
            '<span style="background-color: #e2e8f0; color: #4a5568; '
            'padding: 3px 10px; border-radius: 3px;">Not Clicked</span>'
        )
    clicked_badge.short_description = 'Clicked'


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'company', 'status', 'total_recipients',
        'sent_count', 'open_rate_display', 'created_at'
    ]
    list_filter = ['status', 'company', 'created_at']
    search_fields = ['name', 'subject']
    readonly_fields = [
        'total_recipients', 'sent_count', 'failed_count',
        'opened_count', 'clicked_count', 'sent_at', 'created_at'
    ]
    
    fieldsets = (
        ('Campaign Information', {
            'fields': ('company', 'name', 'subject', 'status')
        }),
        ('Recipients', {
            'fields': ('recipient_type', 'recipient_role', 'recipients')
        }),
        ('Content', {
            'fields': ('template', 'html_content', 'plain_content')
        }),
        ('AI Analysis', {
            'fields': ('ai_generated', 'ai_analysis'),
            'classes': ('collapse',)
        }),
        ('Scheduling', {
            'fields': ('scheduled_at', 'sent_at')
        }),
        ('Statistics', {
            'fields': (
                'total_recipients', 'sent_count', 'failed_count',
                'opened_count', 'clicked_count'
            ),
            'classes': ('collapse',)
        })
    )
    
    def open_rate_display(self, obj):
        if obj.sent_count > 0:
            rate = (obj.opened_count / obj.sent_count) * 100
            color = '#48bb78' if rate > 20 else '#f6ad55' if rate > 10 else '#fc8181'
            return format_html(
                '<span style="background-color: {}; color: white; '
                'padding: 3px 10px; border-radius: 3px;">{:.1f}%</span>',
                color, rate
            )
        return '-'
    open_rate_display.short_description = 'Open Rate'


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'template_type', 'company', 'is_active',
        'is_default', 'created_at'
    ]
    list_filter = ['template_type', 'is_active', 'is_default', 'company']
    search_fields = ['name', 'subject']
    
    fieldsets = (
        ('Template Information', {
            'fields': ('company', 'name', 'template_type', 'subject')
        }),
        ('Content', {
            'fields': ('html_content',)
        }),
        ('AI Metadata', {
            'fields': ('ai_tone', 'ai_summary'),
            'classes': ('collapse',)
        }),
        ('Settings', {
            'fields': ('is_active', 'is_default')
        })
    )


@admin.register(InboxEmail)
class InboxEmailAdmin(admin.ModelAdmin):
    list_display = [
        'subject', 'from_email', 'company', 'received_at',
        'read_badge', 'starred_badge', 'ai_priority'
    ]
    list_filter = [
        'is_read', 'is_starred', 'is_archived',
        'company', 'received_at'
    ]
    search_fields = ['subject', 'from_email', 'to_email']
    readonly_fields = ['message_id', 'received_at', 'created_at']
    
    fieldsets = (
        ('Email Information', {
            'fields': (
                'company', 'message_id', 'subject',
                'from_email', 'from_name', 'to_email'
            )
        }),
        ('Content', {
            'fields': ('html_content', 'plain_content')
        }),
        ('Status', {
            'fields': ('is_read', 'is_starred', 'is_archived', 'received_at')
        }),
        ('AI Analysis', {
            'fields': (
                'ai_summary', 'ai_category', 'ai_sentiment', 'ai_priority'
            ),
            'classes': ('collapse',)
        }),
        ('Threading', {
            'fields': ('thread_id', 'in_reply_to'),
            'classes': ('collapse',)
        })
    )
    
    def read_badge(self, obj):
        if obj.is_read:
            return format_html(
                '<span style="color: #48bb78;">✓ Read</span>'
            )
        return format_html(
            '<span style="color: #f6ad55; font-weight: bold;">● Unread</span>'
        )
    read_badge.short_description = 'Read Status'
    
    def starred_badge(self, obj):
        if obj.is_starred:
            return format_html('<span style="color: #f6ad55;">★</span>')
        return format_html('<span style="color: #e2e8f0;">☆</span>')
    starred_badge.short_description = 'Star'


@admin.register(AIEmailDraft)
class AIEmailDraftAdmin(admin.ModelAdmin):
    list_display = [
        'subject', 'user', 'company', 'tone',
        'was_used', 'user_rating', 'created_at'
    ]
    list_filter = ['tone', 'was_used', 'user_rating', 'company']
    search_fields = ['subject', 'prompt']
    readonly_fields = [
        'model_used', 'tokens_used', 'generation_time', 'created_at'
    ]
    
    fieldsets = (
        ('Draft Information', {
            'fields': ('company', 'user', 'subject', 'tone')
        }),
        ('Generation', {
            'fields': ('prompt', 'context', 'content')
        }),
        ('AI Metadata', {
            'fields': ('model_used', 'tokens_used', 'generation_time'),
            'classes': ('collapse',)
        }),
        ('User Feedback', {
            'fields': ('was_used', 'user_rating')
        })
    )


@admin.register(EmailAnalytics)
class EmailAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        'company', 'date', 'emails_sent', 'open_rate',
        'click_rate', 'bounce_rate'
    ]
    list_filter = ['company', 'date']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Analytics Information', {
            'fields': ('company', 'date')
        }),
        ('Email Counts', {
            'fields': (
                'emails_sent', 'emails_failed', 'emails_opened',
                'emails_clicked', 'emails_bounced', 'emails_received'
            )
        }),
        ('Rates', {
            'fields': ('open_rate', 'click_rate', 'bounce_rate')
        })
    )


@admin.register(EmailAttachment)
class EmailAttachmentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'content_type', 'file_size_display', 'created_at']
    list_filter = ['content_type', 'created_at']
    search_fields = ['filename']
    
    def file_size_display(self, obj):
        size = obj.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    file_size_display.short_description = 'File Size'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for dashboard notifications"""
    list_display = [
        'title', 'company', 'notification_type', 'is_read',
        'created_at', 'read_badge'
    ]
    list_filter = ['notification_type', 'is_read', 'company', 'created_at']
    search_fields = ['title', 'message']
    readonly_fields = ['created_at', 'read_at']
    
    fieldsets = (
        ('Notification Information', {
            'fields': ('company', 'notification_type', 'title', 'message')
        }),
        ('Action', {
            'fields': ('action_url', 'related_object_type', 'related_object_id')
        }),
        ('Status', {
            'fields': ('is_read', 'read_at', 'created_at')
        })
    )
    
    def read_badge(self, obj):
        if obj.is_read:
            return format_html(
                '<span style="color: #48bb78;">✓ Read</span>'
            )
        return format_html(
            '<span style="color: #f6ad55; font-weight: bold;">● Unread</span>'
        )
    read_badge.short_description = 'Read Status'
