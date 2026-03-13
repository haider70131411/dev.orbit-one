# admin.py
from django.contrib import admin
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.utils.html import format_html
from .models import ContactMessage

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = [
        'full_name',
        'email',
        'company_name',
        'created_at',
        'replied_status',
        'reply_action'
    ]
    list_filter = ['is_replied', 'created_at']
    search_fields = ['full_name', 'email', 'company_name', 'message']
    readonly_fields = ['created_at', 'replied_at']
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('full_name', 'company_name', 'email',)
        }),
        ('Message Details', {
            'fields': ('message', 'created_at')
        }),
        ('Reply Information', {
            'fields': ('is_replied', 'reply_message', 'replied_at'),
            'classes': ('collapse',)
        }),
    )
    
    def replied_status(self, obj):
        """Display replied status with color"""
        if obj.is_replied:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Replied</span>'
            )
        return format_html(
            '<span style="color: orange; font-weight: bold;">⏳ Pending</span>'
        )
    replied_status.short_description = 'Status'
    
    def reply_action(self, obj):
        """Add reply button"""
        if not obj.is_replied:
            return format_html(
                '<a class="button" href="/admin/shared/contactmessage/{}/change/">Reply</a>',
                obj.pk
            )
        return format_html(
            '<span style="color: gray;">Replied on {}</span>',
            obj.replied_at.strftime('%Y-%m-%d %H:%M') if obj.replied_at else 'N/A'
        )
    reply_action.short_description = 'Action'
    
    def save_model(self, request, obj, form, change):
        """Send email when reply_message is added"""
        if change and obj.reply_message and not obj.is_replied:
            try:
                # Send reply email
                send_mail(
                    subject=f'Re: Your message to {settings.SITE_NAME if hasattr(settings, "SITE_NAME") else "us"}',
                    message=f"Hi {obj.full_name},\n\n{obj.reply_message}\n\nBest regards,\nYour Team",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[obj.email],
                    fail_silently=False,
                )
                
                # Mark as replied
                obj.is_replied = True
                obj.replied_at = timezone.now()
                
                self.message_user(
                    request,
                    f'Reply sent successfully to {obj.email}',
                    level='success'
                )
            except Exception as e:
                self.message_user(
                    request,
                    f'Error sending email: {str(e)}',
                    level='error'
                )
        
        super().save_model(request, obj, form, change)
    
    actions = ['mark_as_replied', 'mark_as_pending']
    
    def mark_as_replied(self, request, queryset):
        """Bulk action to mark as replied"""
        updated = queryset.update(is_replied=True, replied_at=timezone.now())
        self.message_user(request, f'{updated} messages marked as replied.')
    mark_as_replied.short_description = 'Mark selected as replied'
    
    def mark_as_pending(self, request, queryset):
        """Bulk action to mark as pending"""
        updated = queryset.update(is_replied=False, replied_at=None)
        self.message_user(request, f'{updated} messages marked as pending.')
    mark_as_pending.short_description = 'Mark selected as pending'