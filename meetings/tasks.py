# meetings/tasks.py
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
from .models import Meeting, MeetingParticipant

logger = logging.getLogger(__name__)


@shared_task
def mark_expired_meetings_not_held():
    """
    Celery task to automatically mark expired meetings as 'not_held'.
    This task runs periodically to check all meetings and update their status
    if their end time has passed and they're still in 'scheduled' status.
    """
    try:
        # Get all meetings that need to be checked
        all_meetings = Meeting.objects.all()
        
        # Use the class method to mark expired meetings
        updated_count = Meeting.mark_expired_meetings_not_held(queryset=all_meetings)
        
        if updated_count > 0:
            logger.info(f"Marked {updated_count} expired meeting(s) as 'not_held'")
        else:
            logger.debug("No expired meetings found to mark as 'not_held'")
        
        return {
            'success': True,
            'updated_count': updated_count,
            'timestamp': timezone.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in mark_expired_meetings_not_held task: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def close_expired_in_progress_meetings():
    """
    Celery task to automatically close meetings that are in_progress 
    and have passed their end time. Marks them as 'completed' and 
    sends WebSocket notifications to all active participants.
    """
    try:
        now = timezone.now()
        closed_count = 0
        
        # Get meetings that are in_progress and past their end time
        expired_meetings = Meeting.objects.filter(status='in_progress')
        
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("Channel layer not configured, cannot send WebSocket notifications")
            # Still mark as completed even if we can't send notifications
            channel_layer = None
        
        for meeting in expired_meetings:
            end_time = meeting.scheduled_end_datetime
            if now > end_time:
                # Get all active participants (those who haven't left yet)
                active_participants = MeetingParticipant.objects.filter(
                    meeting=meeting,
                    joined_at__isnull=False,
                    left_at__isnull=True
                )
                
                # Mark all active participants as having left the meeting
                participants_count = active_participants.count()
                if participants_count > 0:
                    active_participants.update(left_at=now)
                    logger.info(f"Marked {participants_count} participant(s) as left in meeting {meeting.meeting_room_id}")
                
                # Mark meeting as completed
                meeting.status = 'completed'
                meeting.save(update_fields=['status'])
                closed_count += 1
                logger.info(f"Meeting {meeting.meeting_room_id} automatically closed (passed end time)")
                
                # Send WebSocket notification to all active participants if channel layer is available
                if channel_layer and participants_count > 0:
                    room_group_name = f'meeting_{meeting.meeting_room_id}'
                    
                    # Send meeting ended notification to all connected participants
                    async_to_sync(channel_layer.group_send)(
                        room_group_name,
                        {
                            'type': 'meeting_ended',
                            'message': 'Meeting has ended due to scheduled time',
                            'meeting_id': str(meeting.id),
                            'meeting_title': meeting.title,
                            'reason': 'time_expired'
                        }
                    )
                    
                    logger.info(f"Sent meeting ended notification to {participants_count} active participants in meeting {meeting.meeting_room_id}")
        
        if closed_count > 0:
            logger.info(f"Closed {closed_count} expired in-progress meeting(s)")
        
        return {
            'success': True,
            'closed_count': closed_count,
            'timestamp': now.isoformat()
        }
    except Exception as e:
        logger.error(f"Error in close_expired_in_progress_meetings task: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


@shared_task
def send_meeting_end_warnings():
    """
    Celery task to send WebSocket alerts to active participants 
    5 minutes before a meeting's scheduled end time.
    Runs every minute to catch meetings approaching their end time.
    """
    try:
        now = timezone.now()
        warning_time = now + timedelta(minutes=5)
        sent_count = 0
        
        # Get meetings that are in_progress and will end in approximately 5 minutes
        # (with 1 minute tolerance since task runs every minute)
        meetings_to_warn = Meeting.objects.filter(
            status='in_progress'
        ).select_related('company')
        
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("Channel layer not configured, cannot send WebSocket warnings")
            return {
                'success': False,
                'error': 'Channel layer not configured',
                'timestamp': now.isoformat()
            }
        
        for meeting in meetings_to_warn:
            end_time = meeting.scheduled_end_datetime
            time_until_end = (end_time - now).total_seconds()
            
            # Check if meeting ends in 4.5-5.5 minutes (5 minutes ± 30 seconds tolerance)
            # This narrow window ensures warning is sent only once or twice
            if 270 <= time_until_end <= 330:  # 4.5 to 5.5 minutes (270-330 seconds)
                # Get active participants
                active_participants = MeetingParticipant.objects.filter(
                    meeting=meeting,
                    joined_at__isnull=False,
                    left_at__isnull=True
                )
                
                if active_participants.exists():
                    # Send warning to all active participants via WebSocket
                    room_group_name = f'meeting_{meeting.meeting_room_id}'
                    
                    # Calculate minutes remaining (round to nearest minute)
                    minutes_remaining = round(time_until_end / 60)
                    
                    async_to_sync(channel_layer.group_send)(
                        room_group_name,
                        {
                            'type': 'meeting_end_warning',
                            'message': f'Meeting will end in {minutes_remaining} minutes',
                            'minutes_remaining': minutes_remaining,
                            'meeting_id': str(meeting.id),
                            'meeting_title': meeting.title
                        }
                    )
                    
                    sent_count += 1
                    logger.info(f"Sent 5-minute warning for meeting {meeting.meeting_room_id} ({minutes_remaining} min remaining) to {active_participants.count()} participants")
        
        if sent_count > 0:
            logger.info(f"Sent end-time warnings to {sent_count} meeting(s)")
        
        return {
            'success': True,
            'warnings_sent': sent_count,
            'timestamp': now.isoformat()
        }
    except Exception as e:
        logger.error(f"Error in send_meeting_end_warnings task: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }

