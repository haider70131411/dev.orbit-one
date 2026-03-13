# meetings/serializers.py
from rest_framework import serializers
from .models import Meeting, MeetingOTP, MeetingParticipant
from companies.models import CompanyPerson
from django.utils import timezone as django_timezone  # Rename to avoid conflict
from datetime import datetime, timedelta
from .models import MeetingFeedback
from zoneinfo import ZoneInfo


class MeetingCreateSerializer(serializers.ModelSerializer):
    interviewer_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        min_length=1,
        max_length=4
    )
    
    # Accept date and time from frontend
    scheduled_date = serializers.DateField(write_only=True)
    scheduled_time = serializers.TimeField(write_only=True)
    timezone = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = Meeting
        fields = [
            'title',
            'description',
            'interviewer_ids',
            'interviewee_name',
            'interviewee_email',
            'interviewee_phone',
            'scheduled_date',
            'scheduled_time',
            'duration_minutes',
            'timezone',
            'enable_recording'
        ]

    def validate_interviewer_ids(self, value):
        """Validate that all interviewers belong to the company"""
        request = self.context.get('request')
        if not request or not request.user.company:
            raise serializers.ValidationError("Company not found")

        valid_interviewers = CompanyPerson.objects.filter(
            id__in=value,
            company=request.user.company
        )

        if len(value) != valid_interviewers.count():
            raise serializers.ValidationError("One or more interviewers not found in your company")

        return value

    def validate_timezone(self, value):
        """Validate timezone string"""
        try:
            ZoneInfo(value)
            return value
        except Exception:
            raise serializers.ValidationError("Invalid timezone")
        
    def validate(self, data):
        """Validate datetime combination and check conflicts"""
        scheduled_date = data.get('scheduled_date')
        scheduled_time = data.get('scheduled_time')
        duration_minutes = data.get('duration_minutes', 60)
        timezone_str = data.get('timezone', 'UTC')
        interviewer_ids = self.initial_data.get('interviewer_ids', [])

        if not interviewer_ids:
            raise serializers.ValidationError("At least one interviewer must be selected")

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
            
            # Convert to UTC for comparison
            utc_tz = ZoneInfo('UTC')
            utc_datetime = user_datetime.astimezone(utc_tz)
            
            # Check if in the past - USE django_timezone
            if utc_datetime <= django_timezone.now():
                raise serializers.ValidationError("Meeting time must be in the future")
            
            # Store the UTC datetime for use in create()
            data['scheduled_datetime_utc'] = utc_datetime
            
            # Check interviewer conflicts
            self.check_interviewer_conflicts(
                utc_datetime=utc_datetime,
                duration_minutes=duration_minutes,
                interviewer_ids=interviewer_ids,
                exclude_meeting_id=self.instance.id if self.instance else None
            )

        return data

    def create(self, validated_data):
        interviewer_ids = validated_data.pop('interviewer_ids')
        
        # Remove the separate date/time/timezone fields
        validated_data.pop('scheduled_date')
        validated_data.pop('scheduled_time')
        timezone_str = validated_data.pop('timezone')
        
        # Get the UTC datetime we calculated in validate()
        scheduled_datetime_utc = validated_data.pop('scheduled_datetime_utc')
        
        interviewers = CompanyPerson.objects.filter(id__in=interviewer_ids)

        # Create meeting with UTC datetime
        meeting = Meeting.objects.create(
            company=self.context['request'].user.company,
            scheduled_datetime=scheduled_datetime_utc,
            user_timezone=timezone_str,  # Store user's timezone for display
            **validated_data
        )

        # Add all interviewers to the meeting
        meeting.interviewers.set(interviewers)

        # Send invitation emails
        meeting.send_meeting_invitations()

        return meeting

    def check_interviewer_conflicts(self, utc_datetime, duration_minutes, interviewer_ids, exclude_meeting_id=None):
        """Check if any interviewers are already booked in overlapping meetings"""
        meeting_end_utc = utc_datetime + timedelta(minutes=duration_minutes)
        
        conflicts = []
        
        for interviewer_id in interviewer_ids:
            # Get all scheduled/in-progress meetings for this interviewer
            existing_meetings = Meeting.objects.filter(
                interviewers__id=interviewer_id,
                status__in=['scheduled', 'in_progress'],
            )

            if exclude_meeting_id:
                existing_meetings = existing_meetings.exclude(id=exclude_meeting_id)
            
            for meeting in existing_meetings:
                existing_start_utc = meeting.scheduled_datetime
                existing_end_utc = meeting.scheduled_end_datetime
                
                # Check for overlap
                if utc_datetime < existing_end_utc and existing_start_utc < meeting_end_utc:
                    interviewer = CompanyPerson.objects.filter(id=interviewer_id).first()
                    
                    # Convert to user's timezone for display
                    existing_start_display = meeting.get_scheduled_datetime_in_timezone()
                    existing_end_display = existing_start_display + timedelta(minutes=meeting.duration_minutes)
                    
                    conflicts.append(
                        f"{interviewer.name if interviewer else 'Unknown'} (ID {interviewer_id}) is already booked "
                        f"from {existing_start_display.strftime('%I:%M %p')} to {existing_end_display.strftime('%I:%M %p')} "
                        f"{existing_start_display.strftime('%Z')} ({meeting.title})."
                    )
        
        if conflicts:
            raise serializers.ValidationError({"interviewer_conflicts": conflicts})


class MeetingSerializer(serializers.ModelSerializer):
    interviewer_names = serializers.SerializerMethodField()
    interviewer_emails = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.name', read_only=True)
    
    # Return date/time in user's timezone
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()
    scheduled_datetime_utc = serializers.DateTimeField(source='scheduled_datetime', read_only=True)
    timezone = serializers.CharField(source='user_timezone', read_only=True)
    
    is_upcoming = serializers.BooleanField(read_only=True)
    is_today = serializers.BooleanField(read_only=True)

    class Meta:
        model = Meeting
        fields = [
            'id',
            'title',
            'description',
            'status',
            'interviewer_names',
            'interviewer_emails',
            'interviewee_name',
            'interviewee_email',
            'interviewee_phone',
            'scheduled_date',
            'scheduled_time',
            'scheduled_datetime_utc',
            'duration_minutes',
            'timezone',
            'meeting_room_id',
            'join_url',
            'company_name',
            'is_upcoming',
            'is_today',
            'enable_recording',
            'recording_file',
            'recording_status',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id',
            'meeting_room_id',
            'join_url',
            'status',
            'created_at',
            'updated_at'
        ]

    def get_interviewer_names(self, obj):
        return [i.name for i in obj.interviewers.all()]

    def get_interviewer_emails(self, obj):
        return [i.email for i in obj.interviewers.all()]
    
    def get_scheduled_date(self, obj):
        """Return date in user's timezone"""
        return obj.scheduled_date
    
    def get_scheduled_time(self, obj):
        """Return time in user's timezone"""
        return obj.scheduled_time.strftime('%H:%M:%S')


class MeetingListSerializer(serializers.ModelSerializer):
    """Simplified serializer for listing meetings"""
    interviewer_names = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.name', read_only=True)
    is_upcoming = serializers.BooleanField(read_only=True)
    is_today = serializers.BooleanField(read_only=True)
    
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()
    timezone = serializers.CharField(source='user_timezone', read_only=True)

    class Meta:
        model = Meeting
        fields = [
            'id',
            'title',
            'status',
            'interviewer_names',
            'interviewee_name',
            'interviewee_email',
            'scheduled_date',
            'scheduled_time',
            'duration_minutes',
            'timezone',
            'company_name',
            'is_upcoming',
            'is_today',
            # Include recording fields so dashboard / list views know if a recording exists
            'enable_recording',
            'recording_file',
            'recording_status',
            'created_at'
        ]

    def get_interviewer_names(self, obj):
        # OPTIMIZED: Use prefetched data instead of querying again
        if hasattr(obj, '_prefetched_objects_cache') and 'interviewers' in obj._prefetched_objects_cache:
            return [i.name for i in obj._prefetched_objects_cache['interviewers']]
        return [i.name for i in obj.interviewers.all()]
    
    def get_scheduled_date(self, obj):
        return obj.scheduled_date
    
    def get_scheduled_time(self, obj):
        return obj.scheduled_time.strftime('%H:%M:%S')


class OTPRequestSerializer(serializers.Serializer):
    meeting_room_id = serializers.CharField(max_length=100)
    email = serializers.EmailField()

    def validate(self, data):
        """Validate meeting and email - ONLY FOR INTERVIEWEE"""
        try:
            meeting = Meeting.objects.get(meeting_room_id=data['meeting_room_id'])
            
            # Check if email is the interviewee
            if meeting.interviewee_email != data['email']:
                raise serializers.ValidationError("OTP is only required for interviewees")
            
            # Check if meeting is within join window
            if not meeting.is_within_join_window:
                raise serializers.ValidationError(
                    "Meeting can only be joined 15 minutes before to 30 minutes after scheduled time"
                )
            
            data['meeting'] = meeting
            return data
            
        except Meeting.DoesNotExist:
            raise serializers.ValidationError("Invalid meeting room ID")


class OTPVerifySerializer(serializers.Serializer):
    meeting_room_id = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, data):
        """Validate OTP"""
        try:
            meeting = Meeting.objects.get(meeting_room_id=data['meeting_room_id'])

            # Get the latest valid OTP for this meeting and email
            otp_obj = MeetingOTP.objects.filter(
                meeting=meeting,
                email=data['email'],
                is_used=False
            ).order_by('-created_at').first()

            if not otp_obj:
                raise serializers.ValidationError("No valid OTP found. Please request a new OTP")

            # Verify OTP
            is_valid, message = otp_obj.verify(data['otp_code'])
            if not is_valid:
                raise serializers.ValidationError(message)

            data['meeting'] = meeting
            data['otp_obj'] = otp_obj
            return data

        except Meeting.DoesNotExist:
            raise serializers.ValidationError("Invalid meeting room ID")


class MeetingJoinSerializer(serializers.Serializer):
    """Serializer for joining a meeting"""
    participant_type = serializers.ChoiceField(choices=['interviewer', 'interviewee'])
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()


class MeetingParticipantSerializer(serializers.ModelSerializer):
    session_duration = serializers.SerializerMethodField()
    is_currently_in_meeting = serializers.BooleanField(read_only=True)

    class Meta:
        model = MeetingParticipant
        fields = [
            'id',
            'participant_type',
            'name',
            'email',
            'joined_at',
            'left_at',
            'session_duration',
            'is_currently_in_meeting',
            'created_at'
        ]

    def get_session_duration(self, obj):
        """Return session duration in seconds"""
        duration = obj.session_duration
        return duration.total_seconds() if duration else None


class MeetingDetailSerializer(serializers.ModelSerializer):
    """Detailed meeting serializer with participants"""
    interviewer_ids = serializers.SerializerMethodField()
    interviewer_names = serializers.SerializerMethodField()
    interviewer_emails = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.name', read_only=True)
    participants = MeetingParticipantSerializer(many=True, read_only=True)
    
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()
    scheduled_datetime_utc = serializers.DateTimeField(source='scheduled_datetime', read_only=True)
    timezone = serializers.CharField(source='user_timezone', read_only=True)
    
    is_upcoming = serializers.BooleanField(read_only=True)
    is_today = serializers.BooleanField(read_only=True)

    class Meta:
        model = Meeting
        fields = [
            'id',
            'title',
            'description',
            'status',
            'interviewer_ids',
            'interviewer_names',
            'interviewer_emails',
            'interviewee_name',
            'interviewee_email',
            'interviewee_phone',
            'scheduled_date',
            'scheduled_time',
            'scheduled_datetime_utc',
            'duration_minutes',
            'timezone',
            'meeting_room_id',
            'join_url',
            'company_name',
            'is_upcoming',
            'is_today',
            'participants',
            'created_at',
            'updated_at'
        ]

    def get_interviewer_names(self, obj):
        # OPTIMIZED: Use prefetched data instead of querying again
        if hasattr(obj, '_prefetched_objects_cache') and 'interviewers' in obj._prefetched_objects_cache:
            return [i.name for i in obj._prefetched_objects_cache['interviewers']]
        return [i.name for i in obj.interviewers.all()]

    def get_interviewer_emails(self, obj):
        # OPTIMIZED: Use prefetched data instead of querying again
        if hasattr(obj, '_prefetched_objects_cache') and 'interviewers' in obj._prefetched_objects_cache:
            return [i.email for i in obj._prefetched_objects_cache['interviewers']]
        return [i.email for i in obj.interviewers.all()]
    
    def get_scheduled_date(self, obj):
        return obj.scheduled_date
    
    def get_scheduled_time(self, obj):
        return obj.scheduled_time.strftime('%H:%M:%S')

    def get_interviewer_ids(self, obj):
        # OPTIMIZED: Use prefetched data instead of querying again
        if hasattr(obj, '_prefetched_objects_cache') and 'interviewers' in obj._prefetched_objects_cache:
            return [i.id for i in obj._prefetched_objects_cache['interviewers']]
        return list(obj.interviewers.values_list('id', flat=True))

class MeetingUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating meetings"""
    interviewer_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        min_length=1,
        max_length=5
    )
    
    # Accept date and time from frontend
    scheduled_date = serializers.DateField(required=False)
    scheduled_time = serializers.TimeField(required=False)
    timezone = serializers.CharField(required=False)
    
    # Option to resend invitations after update
    resend_invitations = serializers.BooleanField(write_only=True, default=False)

    class Meta:
        model = Meeting
        fields = [
            'title',
            'description',
            'interviewer_ids',
            'interviewee_name',
            'interviewee_email',
            'interviewee_phone',
            'scheduled_date',
            'scheduled_time',
            'duration_minutes',
            'timezone',
            'resend_invitations'
        ]

    def validate_interviewer_ids(self, value):
        """Validate that all interviewers belong to the company"""
        request = self.context.get('request')
        if not request or not request.user.company:
            raise serializers.ValidationError("Company not found")

        valid_interviewers = CompanyPerson.objects.filter(
            id__in=value,
            company=request.user.company
        )

        if len(value) != valid_interviewers.count():
            raise serializers.ValidationError("One or more interviewers not found in your company")

        return value

    def validate_timezone(self, value):
        """Validate timezone string"""
        try:
            ZoneInfo(value)
            return value
        except Exception:
            raise serializers.ValidationError("Invalid timezone")
        
    def validate(self, data):
        """Validate datetime combination and check conflicts"""
        # Check if datetime fields are being updated
        scheduled_date = data.get('scheduled_date')
        scheduled_time = data.get('scheduled_time')
        timezone_str = data.get('timezone')
        
        # Get current values from instance if not provided
        if self.instance:
            if not scheduled_date:
                scheduled_date = self.instance.scheduled_date
            if not scheduled_time:
                scheduled_time = self.instance.scheduled_time
            if not timezone_str:
                timezone_str = self.instance.user_timezone
        
        duration_minutes = data.get('duration_minutes', self.instance.duration_minutes if self.instance else 60)
        interviewer_ids = self.initial_data.get('interviewer_ids')
        
        # If interviewer_ids not provided, use existing ones
        if not interviewer_ids and self.instance:
            interviewer_ids = list(self.instance.interviewers.values_list('id', flat=True))

        if scheduled_date and scheduled_time and timezone_str:
            # Combine date and time
            naive_datetime = datetime.combine(scheduled_date, scheduled_time)
            
            # Convert to user's timezone first, then to UTC for storage
            try:
                user_tz = ZoneInfo(timezone_str)
            except Exception as e:
                raise serializers.ValidationError(f"Invalid timezone: {str(e)}")
            
            # Create timezone-aware datetime in user's timezone
            user_datetime = naive_datetime.replace(tzinfo=user_tz)
            
            # Convert to UTC for comparison
            utc_tz = ZoneInfo('UTC')
            utc_datetime = user_datetime.astimezone(utc_tz)
            
            # Check if in the past
            if utc_datetime <= django_timezone.now():
                raise serializers.ValidationError("Meeting time must be in the future")
            
            # Store the UTC datetime for use in update()
            data['scheduled_datetime_utc'] = utc_datetime
            
            # Check interviewer conflicts (exclude current meeting)
            self.check_interviewer_conflicts(
                utc_datetime=utc_datetime,
                duration_minutes=duration_minutes,
                interviewer_ids=interviewer_ids,
                exclude_meeting_id=self.instance.id if self.instance else None
            )

        return data

    def update(self, instance, validated_data):
        """Update meeting and optionally resend invitations"""
        interviewer_ids = validated_data.pop('interviewer_ids', None)
        resend_invitations = validated_data.pop('resend_invitations', False)
        
        # Track if critical fields changed
        critical_fields_changed = False
        datetime_changed = False
        
        # Check if datetime changed
        if 'scheduled_datetime_utc' in validated_data:
            new_datetime = validated_data.pop('scheduled_datetime_utc')
            if new_datetime != instance.scheduled_datetime:
                instance.scheduled_datetime = new_datetime
                critical_fields_changed = True
                datetime_changed = True
        
        # Remove the separate date/time/timezone fields if present
        validated_data.pop('scheduled_date', None)
        validated_data.pop('scheduled_time', None)
        timezone_str = validated_data.pop('timezone', None)
        
        if timezone_str and timezone_str != instance.user_timezone:
            instance.user_timezone = timezone_str
            critical_fields_changed = True
        
        # Check if other critical fields changed
        if 'interviewee_email' in validated_data and validated_data['interviewee_email'] != instance.interviewee_email:
            critical_fields_changed = True
        
        # Reset status to 'scheduled' if:
        # 1. Datetime changed (rescheduled), OR
        # 2. Current status is a terminal state (not_held, completed, cancelled)
        # But don't change if status is 'in_progress' (meeting is currently happening)
        if datetime_changed or instance.status in ['not_held', 'completed', 'cancelled']:
            if instance.status != 'in_progress':
                instance.status = 'scheduled'
        
        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()

        # Update interviewers if provided
        if interviewer_ids is not None:
            old_interviewer_ids = set(instance.interviewers.values_list('id', flat=True))
            new_interviewer_ids = set(interviewer_ids)
            
            if old_interviewer_ids != new_interviewer_ids:
                critical_fields_changed = True
                interviewers = CompanyPerson.objects.filter(id__in=interviewer_ids)
                instance.interviewers.set(interviewers)

        # Resend invitations if requested or if critical fields changed
        if resend_invitations or critical_fields_changed:
            instance.send_meeting_invitations()

        return instance

    def check_interviewer_conflicts(self, utc_datetime, duration_minutes, interviewer_ids, exclude_meeting_id=None):
        """Check if any interviewers are already booked in overlapping meetings"""
        meeting_end_utc = utc_datetime + timedelta(minutes=duration_minutes)
        
        conflicts = []
        
        for interviewer_id in interviewer_ids:
            # Get all scheduled/in-progress meetings for this interviewer
            existing_meetings = Meeting.objects.filter(
                interviewers__id=interviewer_id,
                status__in=['scheduled', 'in_progress'],
            )
            
            # Exclude current meeting if updating
            if exclude_meeting_id:
                existing_meetings = existing_meetings.exclude(id=exclude_meeting_id)
            
            for meeting in existing_meetings:
                existing_start_utc = meeting.scheduled_datetime
                existing_end_utc = meeting.scheduled_end_datetime
                
                # Check for overlap
                if utc_datetime < existing_end_utc and existing_start_utc < meeting_end_utc:
                    interviewer = CompanyPerson.objects.filter(id=interviewer_id).first()
                    
                    # Convert to user's timezone for display
                    existing_start_display = meeting.get_scheduled_datetime_in_timezone()
                    existing_end_display = existing_start_display + timedelta(minutes=meeting.duration_minutes)
                    
                    conflicts.append(
                        f"{interviewer.name if interviewer else 'Unknown'} (ID {interviewer_id}) is already booked "
                        f"from {existing_start_display.strftime('%I:%M %p')} to {existing_end_display.strftime('%I:%M %p')} "
                        f"{existing_start_display.strftime('%Z')} ({meeting.title})."
                    )
        
        if conflicts:
            raise serializers.ValidationError({"interviewer_conflicts": conflicts})


class MeetingFeedbackSerializer(serializers.ModelSerializer):
    interviewer_name = serializers.CharField(source='interviewer.name', read_only=True)
    interviewer_avatar = serializers.SerializerMethodField()
    
    class Meta:
        model = MeetingFeedback
        fields = [
            'id',
            'interviewer',
            'interviewer_name',
            'interviewer_avatar',
            'rating',
            'behavioral_score',
            'technical_score',
            'feedback_text',
            'created_at'
        ]
        read_only_fields = ['interviewer', 'created_at']

    def get_interviewer_avatar(self, obj):
        if obj.interviewer.avatar and obj.interviewer.avatar.preview_image_url:
            return obj.interviewer.avatar.preview_image_url
        return None

    def create(self, validated_data):
        # Auto-assign meeting and interviewer from context
        request = self.context.get('request')
        view = self.context.get('view')
        
        if not request or not view:
            raise serializers.ValidationError("Invalid context")
            
        # Get meeting from URL
        meeting_id = view.kwargs.get('meeting_id') # Assumes URL is meetings/<id>/feedback
        # Note: If we use a different URL structure, we might need to adjust this
        # Actually safer to pass meeting_id in validated_data or from view logic
        
        # We'll rely on the View to pass 'meeting' and 'interviewer' via save()
        # but ModelSerializer.create() expects validated_data to have everything needed for model.
        # So the View should perform perform_create(serializer) and pass meeting/interviewer.
        
        return MeetingFeedback.objects.create(**validated_data)


# Update MeetingDetailSerializer to include feedbacks
class MeetingDetailSerializer(serializers.ModelSerializer):
    """Detailed meeting serializer with participants and feedbacks"""
    interviewer_ids = serializers.SerializerMethodField()
    interviewer_names = serializers.SerializerMethodField()
    interviewer_emails = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='company.name', read_only=True)
    participants = MeetingParticipantSerializer(many=True, read_only=True)
    feedbacks = MeetingFeedbackSerializer(many=True, read_only=True) # Add feedbacks
    
    scheduled_date = serializers.SerializerMethodField()
    scheduled_time = serializers.SerializerMethodField()
    scheduled_datetime_utc = serializers.DateTimeField(source='scheduled_datetime', read_only=True)
    timezone = serializers.CharField(source='user_timezone', read_only=True)
    
    is_upcoming = serializers.BooleanField(read_only=True)
    is_today = serializers.BooleanField(read_only=True)

    class Meta:
        model = Meeting
        fields = [
            'id',
            'title',
            'description',
            'status',
            'interviewer_ids',
            'interviewer_names',
            'interviewer_emails',
            'interviewee_name',
            'interviewee_email',
            'interviewee_phone',
            'scheduled_date',
            'scheduled_time',
            'scheduled_datetime_utc',
            'duration_minutes',
            'timezone',
            'meeting_room_id',
            'join_url',
            'company_name',
            'is_upcoming',
            'is_today',
            'participants',
            'feedbacks', # Added fields
            'enable_recording',
            'recording_file',
            'recording_status',
            'created_at',
            'updated_at'
        ]

    def get_interviewer_names(self, obj):
        # OPTIMIZED: Use prefetched data instead of querying again
        if hasattr(obj, '_prefetched_objects_cache') and 'interviewers' in obj._prefetched_objects_cache:
            return [i.name for i in obj._prefetched_objects_cache['interviewers']]
        return [i.name for i in obj.interviewers.all()]

    def get_interviewer_emails(self, obj):
        # OPTIMIZED: Use prefetched data instead of querying again
        if hasattr(obj, '_prefetched_objects_cache') and 'interviewers' in obj._prefetched_objects_cache:
            return [i.email for i in obj._prefetched_objects_cache['interviewers']]
        return [i.email for i in obj.interviewers.all()]
    
    def get_scheduled_date(self, obj):
        return obj.scheduled_date
    
    def get_scheduled_time(self, obj):
        return obj.scheduled_time.strftime('%H:%M:%S')

    def get_interviewer_ids(self, obj):
        # OPTIMIZED: Use prefetched data instead of querying again
        if hasattr(obj, '_prefetched_objects_cache') and 'interviewers' in obj._prefetched_objects_cache:
            return [i.id for i in obj._prefetched_objects_cache['interviewers']]
        return list(obj.interviewers.values_list('id', flat=True))