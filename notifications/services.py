# notifications/services.py
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.files.storage import default_storage
import logging
import uuid
from email.header import decode_header
from typing import List, Dict, Optional
import openai
from celery import shared_task
from typing import TYPE_CHECKING
from openai import OpenAI
import time
import json

from .utils import notify_email_campaign_sent, notify_email_campaign_completed

if TYPE_CHECKING:
    from .models import Email


logger = logging.getLogger(__name__)


class EmailService:
    """Production-ready email sending service"""
    
    def __init__(self, company):
        self.company = company
        if not company.has_smtp_config():
            raise ValueError(
                f"Company {company.name} has no SMTP configuration. "
                "To use this feature, please create SMTP configuration first."
            )
        self.smtp_config = company.smtp_config
    
    def get_connection(self):
        """Get SMTP connection for this company"""
        params = self.smtp_config.get_connection_params()
        return get_connection(**params)
    
    def send_single_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        to_name: str = "",
        cc: List[str] = None,
        bcc: List[str] = None,
        attachments: List = None,
        created_by=None
    ) -> 'Email':
        """Send a single email and create Email record"""
        from .models import Email
        
        # Generate tracking ID first
        tracking_id = uuid.uuid4()
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        
        # Check if html_content is already wrapped in base_email.html
        # If it is, we need to add tracking pixel. If not, wrap it with tracking included.
        if 'email-container' in html_content:
            # Already wrapped - check if tracking pixel exists
            if f'track/open/' not in html_content:
                # Add tracking pixel before </body>
                tracking_pixel = f'<img src="{base_url}/api/notifications/track/open/{tracking_id}/" width="1" height="1" style="display:none; width:1px; height:1px; border:none; position:absolute; visibility:hidden;" alt="" />'
                if '</body>' in html_content:
                    import re
                    html_content = re.sub(
                        r'(</body>)',
                        tracking_pixel + r'\1',
                        html_content,
                        flags=re.IGNORECASE,
                        count=1
                    )
                else:
                    html_content += tracking_pixel
        else:
            # Not wrapped - wrap it with tracking included
            html_content = self.create_branded_html(
                content=html_content,
                tracking_id=tracking_id,
                subject=subject
            )
        
        # Create email record
        email = Email.objects.create(
            company=self.company,
            from_email=self.smtp_config.from_email,
            from_name=self.smtp_config.from_name,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            plain_content=strip_tags(html_content),
            cc_emails=cc or [],
            bcc_emails=bcc or [],
            tracking_id=tracking_id,
            status='queued',
            created_by=created_by
        )
        
        logger.info(f"Email {email.id} created with tracking_id {tracking_id}. Tracking pixel included: {f'track/open/{tracking_id}' in html_content}")
        
        # Send asynchronously
        send_email_task.delay(email.id)
        
        return email
    
    def send_campaign_emails(self, campaign_id: int):
        """Send all emails for a campaign"""
        from .models import EmailCampaign, Email
        
        try:
            campaign = EmailCampaign.objects.get(id=campaign_id)
            campaign.status = 'sending'
            campaign.save()
            
            recipients = campaign.get_recipients_list()
            sent_count = 0

            # Notify that campaign sending has started
            try:
                notify_email_campaign_sent(self.company, campaign.name)
            except Exception as e:
                logger.error(f"Failed to create 'campaign sent' notification: {str(e)}")
            
            for person in recipients:
                # Render content with person context
                context = {
                    'person': person,
                    'company': self.company,
                    'unsubscribe_url': f"{settings.BASE_URL}/unsubscribe/{person.id}"
                }
                
                # Create individual email
                email = Email.objects.create(
                    company=self.company,
                    campaign=campaign,
                    from_email=self.smtp_config.from_email,
                    from_name=self.smtp_config.from_name,
                    to_email=person.email,
                    to_name=person.name,
                    subject=campaign.subject,
                    html_content=self._render_with_context(campaign.html_content, context),
                    plain_content=campaign.plain_content,
                    tracking_id=uuid.uuid4(),
                    status='queued',
                    created_by=campaign.created_by
                )
                
                # Queue for sending
                send_email_task.delay(email.id)
                sent_count += 1
            
            campaign.status = 'sent'
            campaign.sent_at = timezone.now()
            campaign.total_recipients = sent_count
            campaign.save()

            # Notify that campaign completed
            try:
                notify_email_campaign_completed(self.company, campaign.name, sent_count)
            except Exception as e:
                logger.error(f"Failed to create 'campaign completed' notification: {str(e)}")
            
        except Exception as e:
            logger.error(f"Campaign sending failed: {str(e)}")
            campaign.status = 'failed'
            campaign.save()
            raise
    
    def _render_with_context(self, content: str, context: dict) -> str:
        """Render content with context variables"""
        from django.template import Template, Context
        template = Template(content)
        return template.render(Context(context))
    
    def create_branded_html(
        self,
        content: str,
        template_name: str = 'emails/base_email.html',
        tracking_id: Optional[str] = None,
        subject: str = ""
    ) -> str:
        """Wrap content in branded HTML template"""
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        context = {
            'company': self.company,
            'content': content,
            'logo_url': self.company.logo.url if self.company.logo else None,
            'company_address': f"{self.company.address_street}, {self.company.address_city}",
            'current_year': timezone.now().year,
            'subject': subject,
            'tracking_id': str(tracking_id) if tracking_id else None,
            'base_url': base_url
        }
        return render_to_string(template_name, context)


@shared_task(bind=True, max_retries=3)
def send_email_task(self, email_id: int):
    """Celery task to send email asynchronously"""
    from .models import Email
    
    try:
        email = Email.objects.select_related('company__smtp_config').get(id=email_id)
        
        if not email.company.has_smtp_config():
            raise ValueError("No SMTP configuration found")
        
        email.status = 'sending'
        email.save()
        
        smtp_config = email.company.smtp_config
        connection = get_connection(**smtp_config.get_connection_params())
        
        # Create email message
        msg = EmailMultiAlternatives(
            subject=email.subject,
            body=email.plain_content,
            from_email=smtp_config.get_from_email(),
            to=[email.to_email],
            cc=email.cc_emails,
            bcc=email.bcc_emails,
            connection=connection
        )
        
        # Tracking pixel should already be in html_content (from base_email.html template)
        # Just verify it's there and use the HTML as-is
        tracking_html = email.html_content
        
        if email.tracking_id:
            tracking_url = f"{getattr(settings, 'BASE_URL', 'http://localhost:8000')}/api/notifications/track/open/{email.tracking_id}/"
            if f'track/open/{email.tracking_id}' in tracking_html:
                logger.info(f"✅ Tracking pixel found in email {email.id} HTML")
            else:
                logger.warning(f"⚠️ Tracking pixel NOT found in email {email.id} HTML. Adding as fallback...")
                # Fallback: add tracking pixel if missing
                tracking_pixel = f'<img src="{tracking_url}" width="1" height="1" style="display:none; width:1px; height:1px; border:none; position:absolute; visibility:hidden;" alt="" />'
                if '</body>' in tracking_html:
                    import re
                    tracking_html = re.sub(
                        r'(</body>)',
                        tracking_pixel + r'\1',
                        tracking_html,
                        flags=re.IGNORECASE,
                        count=1
                    )
                else:
                    tracking_html += tracking_pixel
        else:
            logger.warning(f"Email {email.id} has no tracking_id, cannot track opens")
        
        msg.attach_alternative(tracking_html, "text/html")
        
        # Attach files (works with both local and cloud storage)
        for attachment in email.attachments.all():
            try:
                # For cloud storage (R2), use storage.open() instead of .path
                if hasattr(attachment.file, 'storage') and hasattr(attachment.file.storage, 'url'):
                    # Cloud storage - read file content
                    with default_storage.open(attachment.file.name, 'rb') as f:
                        msg.attach(
                            attachment.filename,
                            f.read(),
                            attachment.content_type
                        )
                else:
                    # Local filesystem storage - use .path
                    msg.attach_file(attachment.file.path)
            except Exception as e:
                logger.error(f"Failed to attach file {attachment.filename}: {str(e)}")
                # Continue with other attachments even if one fails
        
        # Send
        msg.send()
        
        email.status = 'sent'
        email.sent_at = timezone.now()
        email.save()
        
        logger.info(f"Email {email.id} sent successfully to {email.to_email}")
        
        # Update campaign statistics
        if email.campaign:
            email.campaign.update_statistics()
        
    except Exception as exc:
        logger.error(f"Email {email_id} failed: {str(exc)}")
        
        email.status = 'failed'
        email.error_message = str(exc)
        email.retry_count += 1
        email.save()
        
        if email.retry_count < email.max_retries:
            # Retry with exponential backoff
            raise self.retry(exc=exc, countdown=60 * (2 ** email.retry_count))

class AIEmailAssistant:
    """AI-powered email writing and analysis"""
    
    def __init__(self, company, user):
        self.company = company
        self.user = user

    def _get_groq_client(self):
        """Return Groq-compatible OpenAI client"""
        return OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    def generate_email(
        self,
        prompt: str,
        context: dict = None,
        tone: str = "professional"
    ) -> Dict:

        from .models import AIEmailDraft
        start_time = time.time()

        system_prompt = f"""You are an expert email writer for {self.company.name}.
Write professional, clear, and engaging emails.

Company Info:
- Name: {self.company.name}
- Industry: {self.company.get_industry_display()}
- Type: {self.company.get_company_type_display()}

Tone: {tone}
Context: {context or 'None'}

Generate a complete email with subject and body in HTML format."""

        try:
            # GROQ (FREE)
            client = self._get_groq_client()

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = response.choices[0].message.content

            # Groq returns this, compatible with OpenAI
            tokens_used = response.usage.total_tokens

            # Parse SUBJECT + BODY
            subject, body = self._parse_ai_response(response_text)
            generation_time = time.time() - start_time

            draft = AIEmailDraft.objects.create(
                company=self.company,
                user=self.user,
                prompt=prompt,
                context=context or {},
                subject=subject,
                content=body,
                tone=tone,
                model_used="llama-3.3-70b-versatile",
                tokens_used=tokens_used,
                generation_time=generation_time
            )

            return {
                'success': True,
                'subject': subject,
                'body': body,
                'draft_id': draft.id,
                'tokens_used': tokens_used,
                'generation_time': generation_time
            }

        except Exception as e:
            logger.error(f"AI generation failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    def analyze_email(self, content: str) -> Dict:
        """Analyze email content for sentiment, tone, readability"""

        system_prompt = """Analyze the following email and provide:
1. Overall sentiment (positive/neutral/negative)
2. Tone (professional/casual/formal/friendly)
3. Readability score (1-10)
4. Word count
5. Suggestions for improvement
6. Potential issues

Return valid JSON."""

        try:
            # GROQ (FREE)
            client = self._get_groq_client()

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ]
            )
            analysis_text = response.choices[0].message.content

            analysis = json.loads(analysis_text)

            return {'success': True, 'analysis': analysis}

        except Exception as e:
            logger.error(f"AI analysis failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    def summarize_email(self, email_content: str) -> str:
        """Generate a brief 1–2 sentence summary"""

        prompt = f"Summarize this email in 1–2 sentences:\n\n{email_content}"

        try:
            client = self._get_groq_client()

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Email summarization failed: {str(e)}")
            return "Summary unavailable"

    def _parse_ai_response(self, text: str) -> tuple:
        """Parse AI response into subject + body"""
        lines = text.strip().split('\n')
        subject = ""
        body = []
        in_body = False

        for line in lines:
            if line.startswith(('SUBJECT:', 'Subject:')):
                subject = line.split(':', 1)[1].strip()
            elif line.startswith(('BODY:', 'Body:')):
                in_body = True
            elif in_body:
                body.append(line)
            elif not subject:
                subject = line.strip()
            else:
                body.append(line)

        return subject, '\n'.join(body).strip()
    
class InboxService:
    """Service for fetching and processing inbox emails"""
    
    # IMAP host mapping for common providers
    IMAP_HOST_MAPPING = {
        'smtp.gmail.com': 'imap.gmail.com',
        'smtp.office365.com': 'outlook.office365.com',
        'smtp.mail.yahoo.com': 'imap.mail.yahoo.com',
        'smtp.zoho.com': 'imap.zoho.com',
        'smtp.mail.yahoo.co.uk': 'imap.mail.yahoo.co.uk',
    }
    
    def __init__(self, company):
        self.company = company
        if not company.has_smtp_config():
            raise ValueError(
                "No email configuration found. "
                "To use this feature, please create SMTP configuration first."
            )
        self.smtp_config = company.smtp_config
    
    def get_imap_host(self):
        """Get IMAP host from SMTP host with proper mapping"""
        smtp_host = self.smtp_config.smtp_host
        
        # Check mapping first
        if smtp_host in self.IMAP_HOST_MAPPING:
            return self.IMAP_HOST_MAPPING[smtp_host]
        
        # Fallback: try replacing 'smtp' with 'imap'
        if 'smtp' in smtp_host.lower():
            return smtp_host.replace('smtp', 'imap').replace('SMTP', 'imap')
        
        # If no smtp in host, return as-is (might be custom)
        return smtp_host
    
    def fetch_emails(self, limit: int = 50):
        """Fetch emails from IMAP server - only from SMTP setup date onwards"""
        import imaplib
        import email
        from email.header import decode_header
        from email.utils import parsedate_tz, mktime_tz
        from .models import InboxEmail
        from datetime import datetime
        
        try:
            # Get SMTP setup date - only fetch emails from this date onwards
            smtp_setup_date = self.smtp_config.created_at.date()
            
            # Connect to IMAP using proper host mapping
            imap_host = self.get_imap_host()
            try:
                mail = imaplib.IMAP4_SSL(imap_host)
            except Exception as e:
                logger.error(f"Failed to connect to IMAP host {imap_host}: {e}")
                raise ValueError(f"Failed to connect to IMAP server. Please check your email provider settings.")
            mail.login(
                self.smtp_config.smtp_username,
                self.smtp_config.decrypt_password()
            )
            
            mail.select('INBOX')
            
            # Search for emails from SMTP setup date onwards
            # Format: (SINCE date) - IMAP date format is DD-MMM-YYYY
            date_str = smtp_setup_date.strftime('%d-%b-%Y')
            search_criteria = f'(SINCE {date_str} UNSEEN)'
            
            status, messages = mail.search(None, search_criteria)
            
            if not messages[0]:
                logger.info(f"No new emails found for {self.company.name} since {smtp_setup_date}")
                mail.close()
                mail.logout()
                return
            
            email_ids = messages[0].split()[-limit:]
            
            fetched_count = 0
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Parse email date
                        email_date = None
                        if msg['Date']:
                            try:
                                date_tuple = parsedate_tz(msg['Date'])
                                if date_tuple:
                                    email_date = datetime.fromtimestamp(
                                        mktime_tz(date_tuple),
                                        tz=timezone.utc
                                    )
                            except Exception as e:
                                logger.warning(f"Failed to parse email date: {e}")
                                email_date = timezone.now()
                        
                        # Only process emails from SMTP setup date onwards
                        if email_date and email_date.date() < smtp_setup_date:
                            continue
                        
                        # Extract email data
                        subject = self._decode_header(msg['Subject'])
                        from_email = email.utils.parseaddr(msg['From'])[1]
                        from_name = email.utils.parseaddr(msg['From'])[0]
                        
                        # Get body
                        html_body, plain_body = self._get_email_body(msg)
                        
                        # Use email date if available, otherwise use current time
                        received_at = email_date if email_date else timezone.now()
                        
                        # Create inbox email
                        inbox_email, created = InboxEmail.objects.get_or_create(
                            company=self.company,
                            message_id=msg['Message-ID'] or f"temp-{email_id.decode()}",
                            defaults={
                                'from_email': from_email,
                                'from_name': from_name,
                                'to_email': self.smtp_config.smtp_username,
                                'subject': subject,
                                'html_content': html_body,
                                'plain_content': plain_body,
                                'received_at': received_at,
                                'thread_id': msg.get('Thread-Index', ''),
                                'in_reply_to': msg.get('In-Reply-To', '')
                            }
                        )
                        
                        if created:
                            fetched_count += 1
                            # AI analysis
                            try:
                                ai_assistant = AIEmailAssistant(self.company, None)
                                summary = ai_assistant.summarize_email(plain_body or html_body)
                                inbox_email.ai_summary = summary
                                inbox_email.save()
                            except Exception as e:
                                logger.warning(f"AI analysis failed for email {inbox_email.id}: {e}")
            
            logger.info(f"Fetched {fetched_count} new emails for {self.company.name} since {smtp_setup_date}")
            
            mail.close()
            mail.logout()
            
        except Exception as e:
            logger.error(f"Inbox fetch failed: {str(e)}")
            raise
    
    def _decode_header(self, header):
        """Decode email header"""
        if header is None:
            return ""
        decoded = decode_header(header)
        return ''.join([
            t[0].decode(t[1] or 'utf-8') if isinstance(t[0], bytes) else t[0]
            for t in decoded
        ])
    
    def _get_email_body(self, msg):
        """Extract email body"""
        html_body = ""
        plain_body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    plain_body = part.get_payload(decode=True).decode()
                elif content_type == 'text/html':
                    html_body = part.get_payload(decode=True).decode()
        else:
            plain_body = msg.get_payload(decode=True).decode()
        
        return html_body, plain_body
    
