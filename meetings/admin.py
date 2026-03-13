from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import Meeting, MeetingOTP, MeetingParticipant


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'company', 'get_interviewers', 'interviewee_name',
        'get_scheduled_date', 'get_scheduled_time', 'get_end_time', 'status',
        'get_participant_count', 'created_at'
    ]

    def get_interviewers(self, obj):
        interviewers = obj.interviewers.all()
        if interviewers:
            names = ", ".join([i.name for i in interviewers[:3]])
            if interviewers.count() > 3:
                names += f" (+{interviewers.count() - 3} more)"
            return names
        return "-"
    get_interviewers.short_description = 'Interviewers'

    def get_scheduled_date(self, obj):
        return obj.scheduled_date
    get_scheduled_date.short_description = "Scheduled Date"
    get_scheduled_date.admin_order_field = 'scheduled_datetime'

    def get_scheduled_time(self, obj):
        return obj.scheduled_time
    get_scheduled_time.short_description = "Scheduled Time"

    def get_end_time(self, obj):
        end_time = obj.scheduled_end_datetime
        user_end_time = end_time.astimezone(obj.get_scheduled_datetime_in_timezone().tzinfo)
        return user_end_time.strftime('%H:%M')
    get_end_time.short_description = "End Time"

    def get_participant_count(self, obj):
        total = obj.participants.count()
        active = obj.participants.filter(
            joined_at__isnull=False,
            left_at__isnull=True
        ).count()
        if active > 0:
            return format_html(
                '<span style="color: green;">{}</span> / {}',
                active, total
            )
        return f"0 / {total}"
    get_participant_count.short_description = "Active / Total"

    list_filter = [
        'status', 'scheduled_datetime', 'company', 'created_at',
        ('scheduled_datetime', admin.DateFieldListFilter)
    ]

    search_fields = [
        'title', 'interviewee_name', 'interviewee_email',
        'interviewers__name', 'company__name', 'meeting_room_id'
    ]

    readonly_fields = [
        'id', 'meeting_room_id', 'join_url', 'created_at', 'updated_at',
        'get_scheduled_end_datetime_display'
    ]

    ordering = ['-scheduled_datetime']

    actions = [
        'mark_as_completed', 'mark_as_cancelled', 'mark_as_not_held',
        'resend_invitations'
    ]

    def mark_as_completed(self, request, queryset):
        count = queryset.update(status='completed')
        self.message_user(request, f'{count} meeting(s) marked as completed.')
    mark_as_completed.short_description = "Mark selected meetings as completed"

    def mark_as_cancelled(self, request, queryset):
        count = queryset.update(status='cancelled')
        self.message_user(request, f'{count} meeting(s) marked as cancelled.')
    mark_as_cancelled.short_description = "Mark selected meetings as cancelled"

    def mark_as_not_held(self, request, queryset):
        count = queryset.update(status='not_held')
        self.message_user(request, f'{count} meeting(s) marked as not held.')
    mark_as_not_held.short_description = "Mark selected meetings as not held"

    def resend_invitations(self, request, queryset):
        count = 0
        for meeting in queryset:
            try:
                meeting.send_meeting_invitations()
                count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f'Failed to resend invitations for {meeting.title}: {str(e)}',
                    level='ERROR'
                )
        self.message_user(request, f'Invitations resent for {count} meeting(s).')
    resend_invitations.short_description = "Resend invitations for selected meetings"

    def get_scheduled_end_datetime_display(self, obj):
        if obj.scheduled_datetime:
            end_time = obj.scheduled_end_datetime
            user_end_time = obj.get_scheduled_datetime_in_timezone(end_time)
            return format_html(
                '<strong>{}</strong> ({} minutes)',
                user_end_time.strftime('%Y-%m-%d %H:%M %Z'),
                obj.duration_minutes
            )
        return "-"
    get_scheduled_end_datetime_display.short_description = "End Date & Time"

    fieldsets = (
        ('Meeting Information', {
            'fields': ('title', 'description', 'status')
        }),
        ('Participants', {
            'fields': (
                'company', 'interviewers',
                'interviewee_name', 'interviewee_email', 'interviewee_phone'
            )
        }),
        ('Schedule', {
            'fields': (
                'scheduled_datetime',
                'get_scheduled_end_datetime_display',
                'duration_minutes', 'user_timezone'
            )
        }),
        ('Meeting Room', {
            'fields': ('meeting_room_id', 'join_url'),
            'classes': ('collapse',)
        }),
        ('Tracking', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('company').prefetch_related('interviewers', 'participants')


@admin.register(MeetingOTP)
class MeetingOTPAdmin(admin.ModelAdmin):
    list_display = [
        'meeting', 'email', 'otp_code', 'is_used', 'is_expired',
        'created_at', 'expires_at', 'verified_at'
    ]
    list_filter = ['is_used', 'created_at', 'expires_at']
    search_fields = ['meeting__title', 'email', 'otp_code']
    readonly_fields = ['created_at', 'verified_at', 'expires_at']
    ordering = ['-created_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('meeting')


@admin.register(MeetingParticipant)
class MeetingParticipantAdmin(admin.ModelAdmin):
    list_display = [
        'meeting', 'participant_type', 'name', 'email',
        'joined_at', 'left_at', 'get_session_duration', 'is_currently_in_meeting_display'
    ]
    list_filter = [
        'participant_type', 'joined_at', 'left_at',
        ('joined_at', admin.DateFieldListFilter)
    ]
    search_fields = ['name', 'email', 'meeting__title', 'meeting__meeting_room_id']
    readonly_fields = ['created_at', 'joined_at', 'left_at', 'ip_address', 'user_agent']
    ordering = ['-joined_at']
    
    def get_session_duration(self, obj):
        duration = obj.session_duration
        if duration:
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        return "-"
    get_session_duration.short_description = "Session Duration"

    def is_currently_in_meeting_display(self, obj):
        if obj.is_currently_in_meeting:
            return format_html('<span style="color: green; font-weight: bold;">● Active</span>')
        else:
            return format_html('<span style="color: gray;">○ Inactive</span>')
    is_currently_in_meeting_display.short_description = "Status"
    is_currently_in_meeting_display.admin_order_field = 'left_at'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('meeting')