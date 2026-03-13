# meetings/utils.py
from django.template.loader import render_to_string
from django.core.mail import get_connection, EmailMessage, send_mail, EmailMultiAlternatives
from django.conf import settings
from django.utils.html import strip_tags
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Centralized email service for all meeting-related emails - sends directly via SMTP (synchronously)"""
    
    def __init__(self, company):
        self.company = company
    
    def _get_email_connection(self):
        """Get email connection (company SMTP or system default SMTP)"""
        if self.company.has_smtp_config():
            smtp_config = self.company.smtp_config
            connection = get_connection(**smtp_config.get_connection_params())
            from_email = smtp_config.get_from_email()
            connection_type = "company SMTP"
        else:
            # Use Django's default SMTP settings (from settings.py)
            # Passing None or calling get_connection() without params uses default settings
            connection = get_connection()  # Uses EMAIL_HOST, EMAIL_PORT, etc. from settings
            from_email = settings.DEFAULT_FROM_EMAIL
            connection_type = "system default SMTP"
        
        return connection, from_email, connection_type
    
    def _send_email_direct(self, subject, html_content, to_email, to_name=""):
        """Send email directly via SMTP (synchronously) - no Celery delay
        
        Uses company SMTP if available, otherwise falls back to system default SMTP.
        """
        if not to_email:
            logger.error("Cannot send email: to_email is empty or None")
            return False
        
        # Convert HTML to plain text
        plain_content = strip_tags(html_content)
        
        # Get connection (company SMTP or system default)
        connection_type = None
        was_using_company_smtp = False
        try:
            connection, from_email, connection_type = self._get_email_connection()
            was_using_company_smtp = self.company.has_smtp_config()
            logger.info(f"Attempting to send email to {to_email} from {from_email} using {connection_type}")
            
            # Create email message with HTML
            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_content,
                from_email=from_email,
                to=[to_email],
                connection=connection
            )
            # Attach HTML version
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            logger.info(f"✅ Email sent successfully using {connection_type} to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send email using {connection_type or 'SMTP'} to {to_email}: {str(e)}", exc_info=True)
            
            # If we were using company SMTP and it failed, try system default SMTP as fallback
            if was_using_company_smtp:
                try:
                    logger.info(f"Company SMTP failed, trying system default SMTP as fallback for {to_email}")
                    # Use Django's default connection (from settings)
                    default_connection = get_connection()
                    fallback_msg = EmailMultiAlternatives(
                        subject=subject,
                        body=plain_content,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[to_email],
                        connection=default_connection
                    )
                    fallback_msg.attach_alternative(html_content, "text/html")
                    fallback_msg.send()
                    
                    logger.info(f"✅ Email sent using system default SMTP (fallback) to {to_email}")
                    return True
                except Exception as fallback_error:
                    logger.error(f"❌ All email methods failed for {to_email}: {str(fallback_error)}", exc_info=True)
                    return False
            else:
                # We were already using system default SMTP, and it failed
                logger.error(f"❌ System default SMTP failed for {to_email}. Please check Django EMAIL settings in settings.py")
                return False
    
    def send_interviewee_invitation(self, meeting):
        """Send invitation to interviewee with personalized link using template"""
        # Get meeting time in user's timezone
        meeting_dt = meeting.get_scheduled_datetime_in_timezone()
        
        # Get personalized join URL for interviewee
        join_url = meeting.get_interviewee_join_url()
        
        # Render template with context
        template_context = {
            'interviewee_name': meeting.interviewee_name,
            'company': self.company,
            'meeting_title': meeting.title,
            'meeting_date': meeting_dt.strftime('%B %d, %Y'),
            'meeting_time': meeting_dt.strftime('%I:%M %p %Z'),
            'duration_minutes': meeting.duration_minutes,
            'join_url': join_url,
        }
        
        # Render template content
        template_content = render_to_string('emails/interviewee_invitation.html', template_context)
        
        subject = f"Interview Invitation - {meeting.title}"
        
        # Wrap in branded template (base_email.html)
        # Use notifications EmailService just for create_branded_html (no sending)
        try:
            from notifications.services import EmailService as NotificationsEmailService
            notifications_service = NotificationsEmailService(self.company)
            html_content = notifications_service.create_branded_html(
                template_content,
                subject=subject
            )
        except (ValueError, Exception) as e:
            # If notifications service not available, wrap manually
            logger.warning(f"Could not use notifications service for branding: {str(e)}, using manual wrap")
            branded_context = {
                'company': self.company,
                'content': template_content,
                'logo_url': self.company.logo.url if self.company.logo else None,
                'company_address': f"{self.company.address_street}, {self.company.address_city}" if self.company.address_street else None,
                'current_year': timezone.now().year,
                'subject': subject,
                'unsubscribe_url': '#',
                'tracking_id': None,
                'base_url': getattr(settings, 'BASE_URL', 'http://localhost:8000')
            }
            html_content = render_to_string('emails/base_email.html', branded_context)
        
        # Send directly via SMTP (synchronously)
        return self._send_email_direct(subject, html_content, meeting.interviewee_email, meeting.interviewee_name)
    
    def send_interviewer_invitation(self, meeting, interviewer):
        """Send invitation to interviewer with personalized link using template"""
        try:
            # Validate interviewer has email
            if not interviewer or not hasattr(interviewer, 'email'):
                logger.error(f"Invalid interviewer object: {interviewer}")
                return False
            
            if not interviewer.email:
                logger.error(f"Interviewer {interviewer.name} (ID: {interviewer.id}) has no email address")
                return False
            
            logger.info(f"Sending interviewer invitation to {interviewer.name} ({interviewer.email}) for meeting {meeting.title}")
            
            # Get meeting time in user's timezone
            meeting_dt = meeting.get_scheduled_datetime_in_timezone()
            
            # Get personalized join URL for this specific interviewer
            join_url = meeting.get_interviewer_join_url(interviewer)
            
            # Get other interviewers
            interviewer_names_list = [i.name for i in meeting.interviewers.all()]
            other_names = [name for name in interviewer_names_list if name != interviewer.name]
            other_interviewers = ', '.join(other_names) if other_names else None
            
            # Render template with context
            template_context = {
                'interviewer_name': interviewer.name,
                'company': self.company,
                'meeting_title': meeting.title,
                'interviewee_name': meeting.interviewee_name,
                'interviewee_email': meeting.interviewee_email,
                'meeting_date': meeting_dt.strftime('%B %d, %Y'),
                'meeting_time': meeting_dt.strftime('%I:%M %p %Z'),
                'duration_minutes': meeting.duration_minutes,
                'other_interviewers': other_interviewers,
                'join_url': join_url,
            }
            
            # Render template content
            template_content = render_to_string('emails/interviewer_invitation.html', template_context)
            
            subject = f"Interview Assignment - {meeting.title}"
            
            # Wrap in branded template (base_email.html)
            # Use notifications EmailService just for create_branded_html (no sending)
            try:
                from notifications.services import EmailService as NotificationsEmailService
                notifications_service = NotificationsEmailService(self.company)
                html_content = notifications_service.create_branded_html(
                    template_content,
                    subject=subject
                )
            except (ValueError, Exception) as e:
                # If notifications service not available, wrap manually
                logger.warning(f"Could not use notifications service for branding: {str(e)}, using manual wrap")
                branded_context = {
                    'company': self.company,
                    'content': template_content,
                    'logo_url': self.company.logo.url if self.company.logo else None,
                    'company_address': f"{self.company.address_street}, {self.company.address_city}" if self.company.address_street else None,
                    'current_year': timezone.now().year,
                    'subject': subject,
                    'unsubscribe_url': '#',
                    'tracking_id': None,
                    'base_url': getattr(settings, 'BASE_URL', 'http://localhost:8000')
                }
                html_content = render_to_string('emails/base_email.html', branded_context)
            
            # Send directly via SMTP (synchronously)
            result = self._send_email_direct(subject, html_content, interviewer.email, interviewer.name)
            
            if result:
                logger.info(f"✅ Interviewer invitation sent successfully to {interviewer.email}")
            else:
                logger.error(f"❌ Failed to send interviewer invitation to {interviewer.email}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error sending interviewer invitation to {interviewer.email if interviewer and hasattr(interviewer, 'email') else 'unknown'}: {str(e)}", exc_info=True)
            return False
    
    def send_otp_email(self, otp_obj):
        """Send OTP to interviewee using template"""
        meeting = otp_obj.meeting
        meeting_dt = meeting.get_scheduled_datetime_in_timezone()
        
        # Render template with context
        template_context = {
            'interviewee_name': meeting.interviewee_name,
            'company': self.company,
            'meeting_title': meeting.title,
            'otp_code': otp_obj.otp_code,
            'meeting_date': meeting_dt.strftime('%B %d, %Y'),
            'meeting_time': meeting_dt.strftime('%I:%M %p %Z'),
        }
        
        # Render template content
        template_content = render_to_string('emails/meeting_otp.html', template_context)
        
        subject = f"OTP for Meeting Access - {meeting.title}"
        
        # Wrap in branded template (base_email.html)
        # Use notifications EmailService just for create_branded_html (no sending)
        try:
            from notifications.services import EmailService as NotificationsEmailService
            notifications_service = NotificationsEmailService(self.company)
            html_content = notifications_service.create_branded_html(
                template_content,
                subject=subject
            )
        except (ValueError, Exception) as e:
            # If notifications service not available, wrap manually
            logger.warning(f"Could not use notifications service for branding: {str(e)}, using manual wrap")
            branded_context = {
                'company': self.company,
                'content': template_content,
                'logo_url': self.company.logo.url if self.company.logo else None,
                'company_address': f"{self.company.address_street}, {self.company.address_city}" if self.company.address_street else None,
                'current_year': timezone.now().year,
                'subject': subject,
                'unsubscribe_url': '#',
                'tracking_id': None,
                'base_url': getattr(settings, 'BASE_URL', 'http://localhost:8000')
            }
            html_content = render_to_string('emails/base_email.html', branded_context)
        
        # Send directly via SMTP (synchronously)
        return self._send_email_direct(subject, html_content, otp_obj.email, meeting.interviewee_name)
