from .models import Notification
from companies.models import Company
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def should_send_notification(company, notification_type):
    """
    Check if notification should be sent based on user settings
    Returns True if notification should be sent, False otherwise
    """
    try:
        # Get company admin user
        if not hasattr(company, 'admin_user') or not company.admin_user:
            return True  # Default to True if no admin user
        
        user = company.admin_user
        
        # Get user settings
        try:
            settings = user.settings
        except:
            # If no settings exist, default to True (send notifications)
            return True
        
        # Check notification type and user preferences
        if notification_type in ['meeting_starting', 'meeting_started', 'meeting_ended', 
                                 'meeting_cancelled', 'meeting_rescheduled', 'meeting_invitation']:
            return settings.notifications_meetings
        
        elif notification_type in ['email_sent', 'email_completed']:
            return settings.notifications_campaigns
        
        # Support chat replies - always notify (important direct message)
        elif notification_type == 'support_reply':
            return True
        
        # For other notification types (avatar, feedback, system, etc.), check general email notifications
        else:
            return settings.notifications_email
            
    except Exception as e:
        # If any error occurs, default to True (send notification)
        print(f"Error checking notification settings: {str(e)}")
        return True

def create_notification(
    company,
    notification_type,
    title,
    message,
    action_url=None,
    related_object_type=None,
    related_object_id=None
):
    """
    Helper function to create notifications easily
    Checks user settings before creating notification
    """
    # Check if notification should be sent based on user settings
    if not should_send_notification(company, notification_type):
        return None  # Don't create notification if user has disabled it
    
    notification = Notification.objects.create(
        company=company,
        notification_type=notification_type,
        title=title,
        message=message,
        action_url=action_url,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )

    # Broadcast via WebSocket
    try:
        channel_layer = get_channel_layer()
        group_name = f"company_notifications_{company.id}"
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notification_message",
                "message": {
                    "id": notification.id,
                    "notification_type": notification.notification_type,
                    "title": notification.title,
                    "message": notification.message,
                    "action_url": notification.action_url,
                    "is_read": notification.is_read,
                    "created_at": notification.created_at.isoformat(),
                    "time_ago": "Just now"
                }
            }
        )
    except Exception as e:
        print(f"Failed to broadcast notification via WebSocket: {str(e)}")

    return notification


# Convenience functions for common notification types

def notify_meeting_starting(meeting):
    """Create notification for meeting starting soon (15 min before)"""
    return create_notification(
        company=meeting.company,
        notification_type='meeting_starting',
        title='Meeting starting soon',
        message=f'"{meeting.title}" will start in 15 minutes. Please be ready.',
        action_url=f'/dashboard/meetings?meeting={meeting.id}',
        related_object_type='meeting',
        related_object_id=meeting.id,
    )


def notify_meeting_started(meeting):
    """Create notification for meeting started"""
    return create_notification(
        company=meeting.company,
        notification_type='meeting_started',
        title='Meeting started',
        message=f'"{meeting.title}" is now in progress.',
        action_url=f'/dashboard/meetings?meeting={meeting.id}',
        related_object_type='meeting',
        related_object_id=meeting.id,
    )


def notify_meeting_ended(meeting):
    """Create notification for meeting ended"""
    return create_notification(
        company=meeting.company,
        notification_type='meeting_ended',
        title='Meeting Ended',
        message=f'Meeting "{meeting.title}" has ended',
        action_url=f'/dashboard/meetings?meeting={meeting.id}',
        related_object_type='meeting',
        related_object_id=meeting.id,
    )


def notify_meeting_cancelled(meeting):
    """Create notification for meeting cancelled"""
    return create_notification(
        company=meeting.company,
        notification_type='meeting_cancelled',
        title='Meeting Cancelled',
        message=f'Meeting "{meeting.title}" has been cancelled',
        action_url='/dashboard/meetings',
        related_object_type='meeting',
        related_object_id=meeting.id,
    )


def notify_meeting_invitation(meeting, interviewee_name):
    """Create notification for new meeting invitation"""
    return create_notification(
        company=meeting.company,
        notification_type='meeting_invitation',
        title='New Meeting Invitation',
        message=f'Meeting invitation sent to {interviewee_name} for "{meeting.title}"',
        action_url=f'/dashboard/meetings?meeting={meeting.id}',
        related_object_type='meeting',
        related_object_id=meeting.id,
    )


def notify_avatar_added(company, avatar_name):
    """Create notification for new avatar added"""
    return create_notification(
        company=company,
        notification_type='avatar_added',
        title='New avatar added',
        message=f'Avatar "{avatar_name}" has been added to your library.',
        action_url='/dashboard/avatar',
        related_object_type='avatar',
    )


def notify_avatar_updated(company, avatar_name):
    """Create notification for avatar updated"""
    return create_notification(
        company=company,
        notification_type='avatar_updated',
        title='Avatar updated',
        message=f'Avatar "{avatar_name}" has been updated.',
        action_url='/dashboard/avatar',
        related_object_type='avatar',
    )


def notify_email_campaign_sent(company, campaign_name):
    """Create notification for email campaign sent"""
    return create_notification(
        company=company,
        notification_type='email_sent',
        title='Email campaign started',
        message=f'Campaign "{campaign_name}" is now being sent to recipients.',
        action_url='/dashboard/email/campaigns',
        related_object_type='campaign',
    )


def notify_email_campaign_completed(company, campaign_name, sent_count):
    """Create notification for email campaign completed"""
    return create_notification(
        company=company,
        notification_type='email_completed',
        title='Email campaign completed',
        message=f'Campaign "{campaign_name}" finished sending. {sent_count} emails sent successfully.',
        action_url='/dashboard/email/campaigns',
        related_object_type='campaign',
    )


def notify_feedback_received(meeting, interviewer_name):
    """Create notification for new feedback received"""
    return create_notification(
        company=meeting.company,
        notification_type='feedback_received',
        title='New Feedback Received',
        message=f'Feedback received from {interviewer_name} for "{meeting.title}"',
        action_url=f'/dashboard/meetings?meeting={meeting.id}',
        related_object_type='meeting',
        related_object_id=meeting.id,
    )


def notify_feedback_submitted(company, meeting_title):
    """Create notification for feedback submitted"""
    return create_notification(
        company=company,
        notification_type='feedback_submitted',
        title='Feedback Submitted',
        message=f'Your feedback for "{meeting_title}" has been submitted',
        action_url='/dashboard/meetings',
        related_object_type='meeting',
    )


def notify_company_approved(company):
    """Create notification for company approved"""
    return create_notification(
        company=company,
        notification_type='company_approved',
        title='Company Approved',
        message='Your company has been approved! You can now access all features',
        action_url='/dashboard',
    )


def notify_company_rejected(company, reason):
    """Create notification for company rejected"""
    return create_notification(
        company=company,
        notification_type='company_rejected',
        title='Company Registration Rejected',
        message=f'Your company registration was rejected. Reason: {reason}',
        action_url='/request-rejected',
    )


def notify_interviewer_added(company, interviewer_name):
    """Create notification for new interviewer added"""
    return create_notification(
        company=company,
        notification_type='interviewer_added',
        title='New Interviewer Added',
        message=f'{interviewer_name} has been added as an interviewer',
        action_url='/dashboard/users',
    )


def notify_support_reply(company, thread_id, preview=None):
    """Create notification when admin replies to support chat"""
    msg = f'Admin replied to your support request.' + (f' "{preview}"' if preview else '')
    return create_notification(
        company=company,
        notification_type='support_reply',
        title='Support Chat Reply',
        message=msg,
        action_url=f'/dashboard/help',
        related_object_type='support_thread',
        related_object_id=thread_id,
    )


def notify_system(company, title, message, action_url=None):
    """Create a generic system notification"""
    return create_notification(
        company=company,
        notification_type='system',
        title=title,
        message=message,
        action_url=action_url,
    )
