# meetings/models.py
from django.db import models
from django.utils import timezone
from companies.models import Company, CompanyPerson
from django.core.mail import send_mail
from django.conf import settings
import uuid
import random
import string
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo

class Meeting(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('not_held', 'Not Held'),
    ]

    # Basic meeting info
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Company and participants
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='meetings')
    interviewers = models.ManyToManyField(CompanyPerson, related_name='meetings')

    # Interviewee details
    interviewee_name = models.CharField(max_length=100)
    interviewee_email = models.EmailField()
    interviewee_phone = models.CharField(max_length=20, blank=True)

    # Meeting scheduling - FIXED: Store as timezone-aware datetime
    scheduled_datetime = models.DateTimeField()  # Store in UTC in DB
    duration_minutes = models.PositiveIntegerField(default=60)
    user_timezone = models.CharField(max_length=50, default='UTC')  # User's display timezone

    # Meeting room/link
    meeting_room_id = models.CharField(max_length=100, unique=True, blank=True)
    join_url = models.URLField(blank=True)

    # Recording
    enable_recording = models.BooleanField(default=False)
    recording_file = models.FileField(upload_to='recordings/', blank=True, null=True)
    recording_status = models.CharField(
        max_length=20, 
        choices=[
            ('pending', 'Pending'), 
            ('recording', 'Recording'), 
            ('uploading', 'Uploading'), 
            ('completed', 'Completed'), 
            ('failed', 'Failed')
        ],
        default='pending'
    )
    recording_by = models.CharField(max_length=100, blank=True, null=True, help_text="ID of the participant currently recording")

    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_datetime']
        indexes = [
            models.Index(fields=['company', 'status', 'scheduled_datetime'], name='meetings_co_status_sched_idx'),
            models.Index(fields=['company', 'scheduled_datetime'], name='meetings_co_scheduled_idx'),
            models.Index(fields=['status', 'scheduled_datetime'], name='meetings_status_scheduled_idx'),
            models.Index(fields=['meeting_room_id'], name='meetings_room_id_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.meeting_room_id:
            self.meeting_room_id = self.generate_room_id()
        if not self.join_url:
            self.join_url = f"{settings.FRONTEND_URL}/meeting/join/{self.meeting_room_id}"
        super().save(*args, **kwargs)

    def generate_room_id(self):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    
    def get_interviewee_join_url(self):
        """Generate interviewee-specific join URL with pre-filled data"""
        from urllib.parse import urlencode
        base_url = f"{settings.FRONTEND_URL}/meeting/join/{self.meeting_room_id}"
        params = urlencode({
            'type': 'interviewee',
            'email': self.interviewee_email,
            'name': self.interviewee_name
        })
        return f"{base_url}?{params}"
    
    def get_interviewer_join_url(self, interviewer):
        """Generate interviewer-specific join URL with pre-filled data"""
        from urllib.parse import urlencode
        base_url = f"{settings.FRONTEND_URL}/meeting/join/{self.meeting_room_id}"
        params = urlencode({
            'type': 'interviewer',
            'email': interviewer.email,
            'name': interviewer.name
        })
        return f"{base_url}?{params}"

    def get_scheduled_datetime_in_timezone(self, tz_string=None):
        """
        Convert scheduled_datetime to user's timezone.
        If tz_string not provided, use the meeting's user_timezone.
        """
        target_tz = tz_string or self.user_timezone
        try:
            user_tz = ZoneInfo(target_tz)
            return self.scheduled_datetime.astimezone(user_tz)
        except Exception:
            # Fallback to UTC if timezone is invalid
            return self.scheduled_datetime

    @property
    def scheduled_date(self):
        """Return date in user's timezone for backward compatibility"""
        dt = self.get_scheduled_datetime_in_timezone()
        return dt.date()

    @property
    def scheduled_time(self):
        """Return time in user's timezone for backward compatibility"""
        dt = self.get_scheduled_datetime_in_timezone()
        return dt.time()

    @property
    def scheduled_end_datetime(self):
        """Return end datetime in UTC"""
        return self.scheduled_datetime + timedelta(minutes=self.duration_minutes)

    @property
    def is_upcoming(self):
        """Check if meeting is in the future"""
        return self.scheduled_datetime > timezone.now()

    @property
    def is_today(self):
        """Check if meeting is today in user's timezone"""
        user_dt = self.get_scheduled_datetime_in_timezone()
        user_today = timezone.now().astimezone(ZoneInfo(self.user_timezone)).date()
        return user_dt.date() == user_today

    @property
    def is_within_join_window(self):
        """Check if meeting can be joined (15 mins before to 30 mins after start)"""
        now = timezone.now()
        join_start = self.scheduled_datetime - timedelta(minutes=15)
        join_end = self.scheduled_datetime + timedelta(minutes=30)
        return join_start <= now <= join_end

    def send_meeting_invitations(self):
        """Send meeting invitation emails to all participants"""
        # Import here to avoid circular imports
        from .utils import EmailService
        import logging
        
        logger = logging.getLogger(__name__)
        
        email_service = EmailService(self.company)
        
        # Email to interviewee
        try:
            logger.info(f"Sending interviewee invitation for meeting: {self.title}")
            email_service.send_interviewee_invitation(self)
        except Exception as e:
            logger.error(f"Failed to send interviewee invitation: {str(e)}", exc_info=True)
        
        # Emails to all interviewers
        interviewers = self.interviewers.all()
        logger.info(f"Sending invitations to {interviewers.count()} interviewer(s) for meeting: {self.title}")
        
        for interviewer in interviewers:
            try:
                logger.info(f"Processing interviewer invitation for: {interviewer.name} ({interviewer.email})")
                result = email_service.send_interviewer_invitation(self, interviewer)
                if not result:
                    logger.warning(f"Failed to send invitation to interviewer {interviewer.name} ({interviewer.email})")
            except Exception as e:
                logger.error(f"Exception sending invitation to interviewer {interviewer.name} ({interviewer.email}): {str(e)}", exc_info=True)

    def check_and_mark_not_held(self):
        """
        Check if meeting end time has passed and meeting is not in_progress or completed.
        If so, mark it as not_held.
        Returns True if status was updated, False otherwise.
        """
        now = timezone.now()
        end_time = self.scheduled_end_datetime
        
        # Only update if:
        # 1. End time has passed
        # 2. Status is 'scheduled' (not in_progress, completed, or cancelled)
        if now > end_time and self.status == 'scheduled':
            self.status = 'not_held'
            self.save(update_fields=['status'])
            return True
        return False

    @classmethod
    def mark_expired_meetings_not_held(cls, queryset=None):
        """
        Mark meetings that have passed their end time and are still 'scheduled' as 'not_held'.
        Optionally filter by queryset (e.g., for a specific company).
        Returns count of meetings updated.
        """
        if queryset is None:
            queryset = cls.objects.all()
        
        now = timezone.now()
        
        # Get meetings that are scheduled and their start time has passed
        candidates = queryset.filter(
            status='scheduled',
            scheduled_datetime__lt=now
        )
        
        # Check each meeting to see if end time has passed
        updated_count = 0
        meetings_to_update = []
        
        for meeting in candidates:
            end_time = meeting.scheduled_end_datetime
            if now > end_time:
                meetings_to_update.append(meeting.id)
        
        # Bulk update in one query
        if meetings_to_update:
            updated_count = queryset.filter(id__in=meetings_to_update).update(status='not_held')
        
        return updated_count

    def __str__(self):
        user_dt = self.get_scheduled_datetime_in_timezone()
        return f"{self.title} - {user_dt.strftime('%Y-%m-%d %H:%M %Z')}"


class MeetingOTP(models.Model):
    """OTP model for interviewee authentication ONLY"""
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='otps')
    email = models.EmailField()
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.otp_code:
            self.otp_code = self.generate_otp()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    def generate_otp(self):
        return ''.join(random.choices(string.digits, k=6))

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired

    def send_otp_email(self):
        """Send OTP to interviewee email"""
        from .utils import EmailService
        
        email_service = EmailService(self.meeting.company)
        email_service.send_otp_email(self)

    def verify(self, provided_otp):
        """Verify the provided OTP"""
        if not self.is_valid:
            return False, "OTP is expired or already used"
        
        if self.otp_code != provided_otp:
            return False, "Invalid OTP"
        
        self.is_used = True
        self.verified_at = timezone.now()
        self.save()
        return True, "OTP verified successfully"

    def __str__(self):
        return f"OTP for {self.meeting.title} - {self.email}"


class MeetingParticipant(models.Model):
    """Track meeting participants and their join/leave times"""
    PARTICIPANT_TYPES = [
        ('interviewer', 'Interviewer'),
        ('interviewee', 'Interviewee'),
    ]

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='participants')
    participant_type = models.CharField(max_length=20, choices=PARTICIPANT_TYPES)
    name = models.CharField(max_length=100)
    email = models.EmailField()

    # Join/Leave tracking
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)

    # Connection info
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_currently_in_meeting(self):
        return self.joined_at is not None and self.left_at is None

    @property
    def session_duration(self):
        if self.joined_at:
            end_time = self.left_at or timezone.now()
            return end_time - self.joined_at
        return None

    def join_meeting(self, ip_address=None, user_agent=None):
        """Mark participant as joined"""
        self.joined_at = timezone.now()
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.save()

    def leave_meeting(self):
        """Mark participant as left"""
        self.left_at = timezone.now()
        self.save()

    def __str__(self):
        return f"{self.name} ({self.participant_type}) - {self.meeting.title}"


class MeetingFeedback(models.Model):
    """Feedback provided by interviewers after a meeting"""
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='feedbacks')
    interviewer = models.ForeignKey(CompanyPerson, on_delete=models.CASCADE, related_name='given_feedbacks')
    
    # Scores (1-5 scale)
    rating = models.PositiveSmallIntegerField(default=0, help_text="Overall rating (1-5)")
    behavioral_score = models.PositiveSmallIntegerField(default=0, help_text="Behavioral score (1-5)")
    technical_score = models.PositiveSmallIntegerField(default=0, help_text="Technical score (1-5)")
    
    feedback_text = models.TextField(blank=True, help_text="Detailed feedback/remarks")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # Ensure one feedback per interviewer per meeting
        constraints = [
            models.UniqueConstraint(fields=['meeting', 'interviewer'], name='unique_interviewer_meeting_feedback')
        ]

    def __str__(self):
        return f"Feedback for {self.meeting.title} by {self.interviewer.name}"