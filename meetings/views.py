# meetings/views.py
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, NotFound
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q
from django.conf import settings

from .models import Meeting, MeetingOTP, MeetingParticipant
from .serializers import (
    MeetingCreateSerializer,
    MeetingSerializer,
    MeetingListSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    MeetingJoinSerializer,
    MeetingDetailSerializer,
    MeetingParticipantSerializer,
    MeetingUpdateSerializer
)

from notifications.utils import (
    notify_meeting_invitation, 
    notify_meeting_started, 
    notify_meeting_ended, 
    notify_meeting_cancelled,
    notify_feedback_received
)
import logging

logger = logging.getLogger(__name__)


# ============= ADMIN VIEWS (CRUD) =============

class MeetingCreateView(generics.CreateAPIView):
    """Create a new meeting (Admin only)"""
    serializer_class = MeetingCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if not self.request.user.company:
            raise ValidationError("You must have a company to create meetings")
        meeting = serializer.save()
        logger.info(f"Meeting created: {meeting.id} by user {self.request.user.email}")
        
        # Trigger notification
        try:
            notify_meeting_invitation(meeting, meeting.interviewee_name)
        except Exception as e:
            logger.error(f"Failed to create notification for meeting invitation: {str(e)}")
            
        return meeting


class MeetingListView(generics.ListAPIView):
    """List all meetings for the company (Admin only)"""
    serializer_class = MeetingListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.company:
            return Meeting.objects.none()

        company_queryset = Meeting.objects.filter(company=self.request.user.company)
        
        # Check and mark expired meetings as not_held before filtering
        # Only run this check periodically, not on every request (optimized)
        # The Celery task handles this, but we check here as fallback
        # Only check if there are scheduled meetings to avoid unnecessary work
        if company_queryset.filter(status='scheduled').exists():
            Meeting.mark_expired_meetings_not_held(queryset=company_queryset.filter(status='scheduled'))

        # Optimize queries: select_related for company, prefetch_related for interviewers with avatars
        queryset = company_queryset.select_related('company').prefetch_related(
            'interviewers',
            'interviewers__avatar'
        )

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by date range (in UTC)
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(scheduled_datetime__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_datetime__date__lte=date_to)

        # Filter upcoming meetings
        if self.request.query_params.get('upcoming') == 'true':
            queryset = queryset.filter(scheduled_datetime__gte=timezone.now())

        # Search by title or interviewee name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(interviewee_name__icontains=search) |
                Q(interviewee_email__icontains=search)
            )

        return queryset.order_by('-scheduled_datetime')


class MeetingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update, or delete a specific meeting (Admin only)"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if not self.request.user.company:
            return Meeting.objects.none()
        # Optimize queries: select_related for company, prefetch_related for related objects
        return Meeting.objects.filter(company=self.request.user.company).select_related('company').prefetch_related(
            'interviewers',
            'interviewers__avatar',
            'participants'
        )

    def get_serializer_class(self):
        """Use different serializers for different methods"""
        if self.request.method in ['PUT', 'PATCH']:
            return MeetingUpdateSerializer
        return MeetingDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        """Override retrieve to check and mark meeting as not_held if needed"""
        instance = self.get_object()
        # Check and update status if meeting end time has passed
        instance.check_and_mark_not_held()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_update(self, serializer):
        meeting = serializer.save()
        logger.info(f"Meeting updated: {meeting.id} by user {self.request.user.email}")
        return meeting

    def perform_destroy(self, instance):
        logger.info(f"Meeting deleted: {instance.id}")
        instance.delete()

# ============= PUBLIC VIEWS (Meeting Info & Join) =============

@api_view(['GET'])
@permission_classes([])
def meeting_info_view(request, room_id):
    """Get public meeting information by room ID with query params support"""
    try:
        # Optimize: prefetch interviewers with avatars to avoid N+1 queries
        meeting = Meeting.objects.select_related('company').prefetch_related(
            'interviewers',
            'interviewers__avatar'
        ).get(meeting_room_id=room_id)

        # Get query parameters
        participant_type = request.query_params.get('type')
        email = request.query_params.get('email')
        name = request.query_params.get('name')

        # Get interviewer details with avatars
        interviewers_data = []
        for interviewer in meeting.interviewers.all():
            interviewer_info = {
                'name': interviewer.name,
                'email': interviewer.email,
                'role': interviewer.role if hasattr(interviewer, 'role') else 'interviewer'
            }
            
            # Add avatar info if exists
            if interviewer.avatar:
                # Use cached URLs with fallback
                vrm_url = interviewer.avatar.vrm_file_url or (
                    interviewer.avatar.vrm_file.url if interviewer.avatar.vrm_file else None
                )
                preview_url = interviewer.avatar.preview_image_url or (
                    interviewer.avatar.preview_image.url if interviewer.avatar.preview_image else None
                )
                # Make absolute if relative
                if vrm_url and not vrm_url.startswith('http') and request:
                    vrm_url = request.build_absolute_uri(vrm_url)
                if preview_url and not preview_url.startswith('http') and request:
                    preview_url = request.build_absolute_uri(preview_url)
                
                interviewer_info['avatar'] = {
                    'id': interviewer.avatar.id,
                    'name': interviewer.avatar.name,
                    'vrm_url': vrm_url,
                    'preview_url': preview_url
                }
            
            interviewers_data.append(interviewer_info)

        # Validate participant if query params provided
        is_valid_participant = False
        auto_send_otp = False
        
        if participant_type and email:
            if participant_type == 'interviewee':
                is_valid_participant = (email == meeting.interviewee_email)
                auto_send_otp = is_valid_participant  # Auto-send OTP for valid interviewees
            elif participant_type == 'interviewer':
                is_valid_participant = meeting.interviewers.filter(email=email).exists()

        # Return basic meeting info
        response_data = {
            'id': str(meeting.id),
            'title': meeting.title,
            'description': meeting.description,
            'scheduled_date': meeting.scheduled_date,
            'scheduled_time': meeting.scheduled_time.strftime('%H:%M:%S'),
            'duration_minutes': meeting.duration_minutes,
            'timezone': meeting.user_timezone,
            'company_name': meeting.company.name,
            'company_logo': meeting.company.logo.url if hasattr(meeting.company, 'logo') and meeting.company.logo else None,
            'status': meeting.status,
            'is_upcoming': meeting.is_upcoming,
            'is_today': meeting.is_today,
            'is_within_join_window': meeting.is_within_join_window,
            'interviewers': interviewers_data,
            'interviewer_count': meeting.interviewers.count(),
            'enable_recording': meeting.enable_recording,
            'prefilled_data': {
                'type': participant_type,
                'email': email,
                'name': name,
                'is_valid_participant': is_valid_participant
            }
        }

        # Auto-send OTP for interviewees if within join window AND meeting is active
        # Do not send again if a valid OTP was already sent for this meeting+email
        is_active_status = meeting.status in ['scheduled', 'in_progress']
        if auto_send_otp and meeting.is_within_join_window and is_active_status:
            try:
                existing_valid_otp = MeetingOTP.objects.filter(
                    meeting=meeting,
                    email=email,
                    is_used=False,
                    expires_at__gt=timezone.now()
                ).first()

                if existing_valid_otp:
                    response_data['otp_sent'] = True
                    response_data['otp_message'] = 'OTP was already sent to your email. Please check your inbox.'
                    response_data['otp_already_sent'] = True
                    logger.info(f"OTP already sent for {email} - meeting {meeting.meeting_room_id}, not sending again")
                else:
                    # Invalidate old OTPs
                    MeetingOTP.objects.filter(
                        meeting=meeting,
                        email=email,
                        is_used=False
                    ).update(is_used=True)

                    # Create new OTP
                    otp_obj = MeetingOTP.objects.create(
                        meeting=meeting,
                        email=email
                    )
                    otp_obj.send_otp_email()
                    response_data['otp_sent'] = True
                    response_data['otp_message'] = 'OTP has been sent to your email'
                    logger.info(f"Auto-sent OTP to {email} for meeting {meeting.meeting_room_id}")
            except Exception as e:
                logger.error(f"Failed to auto-send OTP: {str(e)}")
                response_data['otp_sent'] = False
                response_data['otp_error'] = str(e)

        return Response(response_data)
    except Meeting.DoesNotExist:
        raise NotFound("Meeting not found")


@api_view(['POST'])
@permission_classes([])
def request_otp_view(request):
    """
    Request OTP for INTERVIEWEE ONLY to join meeting.
    If a valid OTP was already sent for this meeting+email (not used, not expired),
    we do not send again - just return success.
    """
    serializer = OTPRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    meeting = serializer.validated_data['meeting']
    email = serializer.validated_data['email']

    # If we already sent a valid OTP (not used, not expired), do not send again
    existing_valid_otp = MeetingOTP.objects.filter(
        meeting=meeting,
        email=email,
        is_used=False,
        expires_at__gt=timezone.now()
    ).first()

    if existing_valid_otp:
        logger.info(f"OTP already sent for {email} - meeting {meeting.meeting_room_id}, not sending again")
        return Response({
            'message': 'OTP already sent to your email. Please check your inbox.',
            'expires_in_minutes': 10,
            'already_sent': True
        })

    # Invalidate any old unused OTPs (expired or not)
    MeetingOTP.objects.filter(
        meeting=meeting,
        email=email,
        is_used=False
    ).update(is_used=True)

    # Create NEW OTP
    otp_obj = MeetingOTP.objects.create(
        meeting=meeting,
        email=email
    )
    
    # Send OTP email
    try:
        otp_obj.send_otp_email()
        logger.info(f"OTP sent to {email} for meeting {meeting.meeting_room_id}")
        return Response({
            'message': 'OTP sent to your email successfully',
            'expires_in_minutes': 10
        })
    except Exception as e:
        logger.error(f"Failed to send OTP: {str(e)}")
        return Response(
            {'error': f'Failed to send OTP: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])
def verify_otp_view(request):
    """Verify OTP and get meeting access token (INTERVIEWEE ONLY)"""
    serializer = OTPVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    meeting = serializer.validated_data['meeting']
    email = serializer.validated_data['email']

    logger.info(f"OTP verified successfully for {email} - meeting {meeting.meeting_room_id}")

    return Response({
        'message': 'OTP verified successfully',
        'meeting_access': {
            'room_id': meeting.meeting_room_id,
            'join_url': meeting.join_url,
            'participant_type': 'interviewee',
            'meeting_id': str(meeting.id),
            'interviewee_name': meeting.interviewee_name
        }
    })


@api_view(['POST'])
@permission_classes([])
def join_meeting_view(request, room_id):
    """
    Join a meeting room.
    - INTERVIEWEE: Must verify OTP first
    - INTERVIEWER: No OTP required, just validate email
    """
    try:
        # Optimize: prefetch interviewers with avatars to avoid N+1 queries
        meeting = Meeting.objects.select_related('company').prefetch_related(
            'interviewers',
            'interviewers__avatar'
        ).get(meeting_room_id=room_id)
    except Meeting.DoesNotExist:
        raise NotFound("Meeting room not found")

    serializer = MeetingJoinSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    participant_type = serializer.validated_data['participant_type']
    name = serializer.validated_data['name']
    email = serializer.validated_data['email']

    # Validate participant based on type
    avatar_data = None
    
    if participant_type == 'interviewer':
        # INTERVIEWER: Check if email exists in meeting's interviewers
        interviewer = meeting.interviewers.filter(email=email).first()
        if not interviewer:
            return Response(
                {'error': 'Invalid interviewer email'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get avatar data
        if interviewer.avatar:
            # Use cached URLs with fallback
            vrm_url = interviewer.avatar.vrm_file_url or (
                interviewer.avatar.vrm_file.url if interviewer.avatar.vrm_file else None
            )
            preview_url = interviewer.avatar.preview_image_url or (
                interviewer.avatar.preview_image.url if interviewer.avatar.preview_image else None
            )
            # Make absolute if relative
            if vrm_url and not vrm_url.startswith('http'):
                vrm_url = request.build_absolute_uri(vrm_url)
            if preview_url and not preview_url.startswith('http'):
                preview_url = request.build_absolute_uri(preview_url)
            
            avatar_data = {
                'id': interviewer.avatar.id,
                'name': interviewer.avatar.name,
                'vrm_url': vrm_url,
                'preview_url': preview_url
            }
    
    elif participant_type == 'interviewee':
        # INTERVIEWEE: Must have verified OTP
        if email != meeting.interviewee_email:
            return Response(
                {'error': 'Invalid interviewee email'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if OTP was verified recently (within last 30 minutes)
        recent_verified_otp = MeetingOTP.objects.filter(
            meeting=meeting,
            email=email,
            is_used=True,
            verified_at__isnull=False,
            verified_at__gte=timezone.now() - timezone.timedelta(minutes=30)
        ).exists()
        
        if not recent_verified_otp:
            return Response(
                {'error': 'OTP verification required. Please request and verify OTP first'},
                status=status.HTTP_403_FORBIDDEN
            )

    # Check meeting status
    # Check meeting status
    if meeting.status == 'cancelled':
        return Response(
            {'error': 'This meeting has been cancelled'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if meeting.status == 'completed':
        return Response(
            {'error': 'This meeting has been completed'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if meeting.status == 'not_held':
        return Response(
            {'error': 'This meeting was not held'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if meeting is within join window
    if not meeting.is_within_join_window:
        return Response(
            {'error': 'Meeting can only be joined 15 minutes before to 30 minutes after scheduled time'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get client IP and User Agent
    ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0] or \
                 request.META.get('REMOTE_ADDR')
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    # Create or get participant record
    participant, created = MeetingParticipant.objects.get_or_create(
        meeting=meeting,
        participant_type=participant_type,
        email=email,
        defaults={'name': name}
    )

    # Join the meeting if not already in
    if not participant.is_currently_in_meeting:
        participant.join_meeting(ip_address=ip_address, user_agent=user_agent)
        logger.info(f"{participant_type} {name} joined meeting {meeting.meeting_room_id}")

    # Update meeting status if needed
        meeting.status = 'in_progress'
        meeting.save()
        logger.info(f"Meeting {meeting.meeting_room_id} status changed to in_progress")
        
        # Trigger notification
        try:
            notify_meeting_started(meeting)
        except Exception as e:
            logger.error(f"Failed to create notification for meeting started: {str(e)}")

    # Determine WebSocket protocol based on request
    ws_protocol = 'wss' if request.is_secure() else 'ws'

    response_data = {
        'message': f'{participant_type.title()} joined successfully',
        'meeting': {
            'id': str(meeting.id),
            'title': meeting.title,
            'room_id': meeting.meeting_room_id,
            'status': meeting.status,
            'participant_type': participant_type,
            'participant_name': name,
            'company_name': meeting.company.name,
            'company_logo': request.build_absolute_uri(meeting.company.logo.url) if hasattr(meeting.company, 'logo') and meeting.company.logo else None,
            'enable_recording': meeting.enable_recording
        },
        'participant_id': participant.id,
        'avatar': avatar_data,
        'websocket_url': f"{ws_protocol}://{request.get_host()}/ws/meeting/{room_id}/"
    }

    # If interviewer, include their CompanyPerson ID for feedback submission
    if participant_type == 'interviewer':
        # We need to fetch the interviewer object again or find it from earlier
        # In the earlier code block: interviewer = meeting.interviewers.filter(email=email).first()
        # But that variable scope might be limited to the if block.
        # Let's re-fetch to be safe and simple, or improved slightly:
        interviewer_obj = meeting.interviewers.filter(email=email).first()
        if interviewer_obj:
            response_data['interviewer_id'] = interviewer_obj.id

    return Response(response_data)


@api_view(['POST'])
@permission_classes([])
def leave_meeting_view(request, room_id):
    """Leave a meeting room"""
    try:
        meeting = Meeting.objects.get(meeting_room_id=room_id)
    except Meeting.DoesNotExist:
        raise NotFound("Meeting room not found")

    participant_id = request.data.get('participant_id')
    if not participant_id:
        return Response(
            {'error': 'Participant ID required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        participant = MeetingParticipant.objects.get(
            id=participant_id,
            meeting=meeting
        )

        if participant.is_currently_in_meeting:
            participant.leave_meeting()
            logger.info(f"{participant.participant_type} {participant.name} left meeting {meeting.meeting_room_id}")
            
            # Don't automatically mark meeting as completed when interviewers leave
            # Meeting will only be marked as completed when the scheduled end time is reached
            # (handled by the Celery task: close_expired_in_progress_meetings)
            # This allows the meeting to remain active until its scheduled end time
            
            return Response({
                'message': f'{participant.participant_type.title()} left successfully',
                'session_duration_seconds': participant.session_duration.total_seconds() if participant.session_duration else 0,
                'meeting_status': meeting.status
            })
        else:
            return Response(
                {'error': 'Participant is not currently in meeting'},
                status=status.HTTP_400_BAD_REQUEST
            )

    except MeetingParticipant.DoesNotExist:
        return Response(
            {'error': 'Participant not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ============= UTILITY VIEWS =============

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def meeting_participants_view(request, meeting_id):
    """Get current participants in a meeting (Admin only)"""
    if not request.user.company:
        return Response(
            {'error': 'Company required'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        meeting = Meeting.objects.get(
            id=meeting_id,
            company=request.user.company
        )

        participants = MeetingParticipant.objects.filter(meeting=meeting).order_by('-joined_at')
        serializer = MeetingParticipantSerializer(participants, many=True)

        return Response({
            'meeting_id': str(meeting.id),
            'meeting_title': meeting.title,
            'participants': serializer.data,
            'total_participants': participants.count(),
            'active_participants': participants.filter(
                joined_at__isnull=False,
                left_at__isnull=True
            ).count()
        })

    except Meeting.DoesNotExist:
        raise NotFound("Meeting not found")


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_meeting_status_view(request, meeting_id):
    """Update meeting status (Admin only)"""
    if not request.user.company:
        return Response(
            {'error': 'Company required'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        meeting = Meeting.objects.get(
            id=meeting_id,
            company=request.user.company
        )

        new_status = request.data.get('status')
        if new_status not in ['scheduled', 'in_progress', 'completed', 'cancelled', 'not_held']:
            return Response(
                {'error': 'Invalid status'},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = meeting.status
        meeting.status = new_status
        meeting.save()

        logger.info(f"Meeting {meeting.id} status changed from {old_status} to {new_status}")
        
        # Trigger notifications for status changes
        try:
            if new_status == 'completed' and old_status != 'completed':
                notify_meeting_ended(meeting)
            elif new_status == 'cancelled' and old_status != 'cancelled':
                notify_meeting_cancelled(meeting)
        except Exception as e:
            logger.error(f"Failed to create notification for meeting status change: {str(e)}")

        return Response({
            'message': f'Meeting status updated to {new_status}',
            'meeting_id': str(meeting.id),
            'status': meeting.status
        })

    except Meeting.DoesNotExist:
        raise NotFound("Meeting not found")


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resend_invitations_view(request, meeting_id):
    """Resend meeting invitations (Admin only)"""
    if not request.user.company:
        return Response(
            {'error': 'Company required'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        meeting = Meeting.objects.get(
            id=meeting_id,
            company=request.user.company
        )

        # Resend invitations
        meeting.send_meeting_invitations()
        logger.info(f"Invitations resent for meeting {meeting.id}")

        return Response({
            'message': 'Meeting invitations sent successfully',
            'meeting_id': str(meeting.id),
            'sent_to': {
                'interviewee': meeting.interviewee_email,
                'interviewers': list(meeting.interviewers.values_list('email', flat=True))
            }
        })

    except Meeting.DoesNotExist:
        raise NotFound("Meeting not found")


# ============= DASHBOARD VIEWS =============

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def meeting_dashboard_view(request):
    """Get meeting dashboard data for admin"""
    if not request.user.company:
        return Response(
            {'error': 'Company required'},
            status=status.HTTP_403_FORBIDDEN
        )

    company = request.user.company
    now = timezone.now()

    # Check and mark expired meetings as not_held before getting statistics
    # Only check scheduled meetings to avoid unnecessary work
    company_queryset = Meeting.objects.filter(company=company, status='scheduled')
    if company_queryset.exists():
        Meeting.mark_expired_meetings_not_held(queryset=company_queryset)

    # OPTIMIZED: Use single aggregation query instead of multiple count queries
    from django.db.models import Count, Q
    
    # Get all statistics in one query using aggregation
    stats = Meeting.objects.filter(company=company).aggregate(
        total_meetings=Count('id'),
        upcoming_meetings=Count('id', filter=Q(scheduled_datetime__gte=now, status='scheduled')),
        completed_meetings=Count('id', filter=Q(status='completed')),
        in_progress_meetings=Count('id', filter=Q(status='in_progress')),
        not_held_meetings=Count('id', filter=Q(status='not_held'))
    )
    
    # Today's meetings count (separate because it needs date filtering)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timezone.timedelta(days=1)
    
    today_meetings_count = Meeting.objects.filter(
        company=company,
        scheduled_datetime__gte=today_start,
        scheduled_datetime__lt=today_end
    ).exclude(status__in=['completed', 'not_held']).count()

    # Get today's meetings (exclude completed and not_held meetings)
    # Optimize: prefetch related data to avoid N+1 queries
    todays_meetings = Meeting.objects.filter(
        company=company,
        scheduled_datetime__gte=today_start,
        scheduled_datetime__lt=today_end
    ).exclude(status__in=['completed', 'not_held']).select_related('company').prefetch_related(
        'interviewers',
        'interviewers__avatar'
    ).order_by('scheduled_datetime')
    todays_meetings_serializer = MeetingListSerializer(todays_meetings, many=True, context={'request': request})
    
    # Get IDs of today's meetings to exclude from recent meetings
    todays_meeting_ids = list(todays_meetings.values_list('id', flat=True))

    # Get recent meetings (exclude today's meetings to avoid duplication)
    # Optimize: prefetch related data to avoid N+1 queries
    recent_meetings = Meeting.objects.filter(
        company=company
    ).exclude(id__in=todays_meeting_ids).select_related('company').prefetch_related(
        'interviewers',
        'interviewers__avatar'
    ).order_by('-created_at')[:5]
    recent_meetings_serializer = MeetingListSerializer(recent_meetings, many=True, context={'request': request})

    return Response({
        'statistics': {
            'total_meetings': stats['total_meetings'],
            'upcoming_meetings': stats['upcoming_meetings'],
            'today_meetings': today_meetings_count,
            'completed_meetings': stats['completed_meetings'],
            'in_progress_meetings': stats['in_progress_meetings'],
            'not_held_meetings': stats['not_held_meetings']
        },
        'todays_meetings': todays_meetings_serializer.data,
        'recent_meetings': recent_meetings_serializer.data
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def not_held_meetings_view(request):
    """Get all meetings that are not held (Admin only)"""
    if not request.user.company:
        return Response(
            {'error': 'Company required'},
            status=status.HTTP_403_FORBIDDEN
        )

    company = request.user.company
    
    # Check and mark expired meetings as not_held before getting the list
    # Only check scheduled meetings to avoid unnecessary work
    company_queryset = Meeting.objects.filter(company=company, status='scheduled')
    if company_queryset.exists():
        Meeting.mark_expired_meetings_not_held(queryset=company_queryset)
    
    # Get all not_held meetings
    # Optimize: select_related for company, prefetch_related for interviewers with avatars
    not_held_meetings = Meeting.objects.filter(
        company=company,
        status='not_held'
    ).select_related('company').prefetch_related(
        'interviewers',
        'interviewers__avatar'
    ).order_by('-scheduled_datetime')
    
    serializer = MeetingListSerializer(not_held_meetings, many=True, context={'request': request})
    
    return Response({
        'count': not_held_meetings.count(),
        'meetings': serializer.data
    })


@api_view(['GET'])
@permission_classes([])
def meeting_status_check_view(request, room_id):
    """Check meeting status and participant count (Public)"""
    try:
        meeting = Meeting.objects.get(meeting_room_id=room_id)

        active_participants = MeetingParticipant.objects.filter(
            meeting=meeting,
            joined_at__isnull=False,
            left_at__isnull=True
        )

        return Response({
            'meeting_id': str(meeting.id),
            'status': meeting.status,
            'active_participants_count': active_participants.count(),
            'participants': [
                {
                    'type': p.participant_type,
                    'name': p.name,
                    'joined_at': p.joined_at
                }
                for p in active_participants
            ]
        })

    except Meeting.DoesNotExist:
        raise NotFound("Meeting not found")
    
# Add this to meetings/views.py (before webrtc_config_view)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_meeting_links_view(request, meeting_id):
    """Get personalized join links for a meeting (Admin only)"""
    if not request.user.company:
        return Response(
            {'error': 'Company required'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        # Optimize: select_related for company, prefetch_related for interviewers with avatars
        meeting = Meeting.objects.select_related('company').prefetch_related(
            'interviewers',
            'interviewers__avatar'
        ).get(
            id=meeting_id,
            company=request.user.company
        )

        # Get interviewee link
        interviewee_link = meeting.get_interviewee_join_url()

        # Get all interviewer links
        interviewer_links = []
        for interviewer in meeting.interviewers.all():
            interviewer_links.append({
                'interviewer_id': interviewer.id,
                'name': interviewer.name,
                'email': interviewer.email,
                'join_url': meeting.get_interviewer_join_url(interviewer)
            })

        return Response({
            'meeting_id': str(meeting.id),
            'meeting_title': meeting.title,
            'interviewee_link': {
                'name': meeting.interviewee_name,
                'email': meeting.interviewee_email,
                'join_url': interviewee_link,
                'requires_otp': True
            },
            'interviewer_links': interviewer_links,
            'generic_join_url': meeting.join_url  # Backward compatibility
        })

    except Meeting.DoesNotExist:
        raise NotFound("Meeting not found")


@api_view(['GET'])
@permission_classes([])
def webrtc_config_view(request):
    """Get WebRTC configuration (ICE servers)"""
    return Response({
        'ice_servers': settings.WEBRTC_CONFIG.get('ice_servers', [
            {'urls': 'stun:stun.l.google.com:19302'},
            {'urls': 'stun:stun1.l.google.com:19302'}
        ])
    })


# ============= FEEDBACK VIEWS =============

from .serializers import MeetingFeedbackSerializer

class MeetingFeedbackView(generics.CreateAPIView):
    """Submit feedback for a meeting (Interviewer only)"""
    serializer_class = MeetingFeedbackSerializer
    permission_classes = []  # Allow unauthenticated access per user request

    def create(self, request, *args, **kwargs):
        meeting_id = self.kwargs.get('meeting_id')
        meeting = get_object_or_404(Meeting, id=meeting_id)

        data = request.data.copy()
        data['meeting'] = meeting.id
        
        interviewer_id = data.get('interviewer')
        
        # Handle interviewer identification
        if not interviewer_id:
             if request.user.is_authenticated:
                  # If authenticated, assume current user
                  interviewer_id = request.user.id
                  data['interviewer'] = interviewer_id
             else:
                  return Response(
                      {'error': 'Interviewer ID is required for unauthenticated submission'}, 
                      status=status.HTTP_400_BAD_REQUEST
                  )

        # Validate interviewer belongs to meeting
        # We assume interviewer_id is the ID of CompanyPerson
        if not meeting.interviewers.filter(id=interviewer_id).exists():
             # Allow company admin override if authenticated
             is_admin = (
                 request.user.is_authenticated and 
                 request.user.company == meeting.company and 
                 request.user.role in ['admin', 'owner']
             )
             
             if not is_admin:
                 return Response(
                    {'error': 'Provided interviewer is not assigned to this meeting'},
                    status=status.HTTP_403_FORBIDDEN
                )

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        # Pass meeting and interviewer details directly to save()
        # This bypasses the read_only_fields restriction in the serializer
        feedback = serializer.save(meeting=meeting, interviewer_id=interviewer_id)
        
        # Trigger notification
        try:
            interviewer = meeting.interviewers.filter(id=interviewer_id).first()
            interviewer_name = interviewer.name if interviewer else "An interviewer"
            notify_feedback_received(meeting, interviewer_name)
        except Exception as e:
            logger.error(f"Failed to create notification for feedback received: {str(e)}")
        
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class MeetingFeedbackByRoomView(generics.CreateAPIView):
    """Submit feedback for a meeting using room_id (Public endpoint)"""
    serializer_class = MeetingFeedbackSerializer
    permission_classes = []  # Allow unauthenticated access

    def create(self, request, *args, **kwargs):
        room_id = self.kwargs.get('room_id')
        meeting = get_object_or_404(Meeting, meeting_room_id=room_id)

        data = request.data.copy()
        data['meeting'] = meeting.id
        
        interviewer_id = data.get('interviewer')
        
        # Handle interviewer identification
        if not interviewer_id:
             if request.user.is_authenticated:
                  # If authenticated, assume current user
                  interviewer_id = request.user.id
                  data['interviewer'] = interviewer_id
             else:
                  return Response(
                      {'error': 'Interviewer ID is required for unauthenticated submission'}, 
                      status=status.HTTP_400_BAD_REQUEST
                  )

        # Validate interviewer belongs to meeting
        if not meeting.interviewers.filter(id=interviewer_id).exists():
             # Allow company admin override if authenticated
             is_admin = (
                 request.user.is_authenticated and 
                 request.user.company == meeting.company and 
                 request.user.role in ['admin', 'owner']
             )
             
             if not is_admin:
                 return Response(
                    {'error': 'Provided interviewer is not assigned to this meeting'},
                    status=status.HTTP_403_FORBIDDEN
                )

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        feedback = serializer.save(meeting=meeting, interviewer_id=interviewer_id)
        
        # Trigger notification
        try:
            interviewer = meeting.interviewers.filter(id=interviewer_id).first()
            interviewer_name = interviewer.name if interviewer else "An interviewer"
            notify_feedback_received(meeting, interviewer_name)
        except Exception as e:
            logger.error(f"Failed to create notification for feedback received: {str(e)}")
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)