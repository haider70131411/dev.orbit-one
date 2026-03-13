from django.db.models.signals import post_save
from django.dispatch import receiver
from companies.models import Company
from .models import EmailTemplate
from django.template.loader import render_to_string


@receiver(post_save, sender=Company)
def create_default_templates(sender, instance, created, **kwargs):
    """Auto-create default templates for new companies"""
    if created:
        templates = [
            {
                'name': 'Interviewee Invitation',
                'template_type': 'invitation',
                'subject': 'Interview Invitation - {{ position }}',
                'html_content': render_to_string('emails/interviewee_invitation.html')
            },
            {
                'name': 'Interviewer Invitation',
                'template_type': 'invitation',
                'subject': 'Interview Invitation - {{ position }}',
                'html_content': render_to_string('emails/interviewer_invitation.html')
            },
            {
                'name': 'Interviewee OTP',
                'template_type': 'otp',
                'subject': 'Otp for meeting access',
                'html_content': render_to_string('emails/meeting_otp.html')
            },
            {
                'name': 'Welcome Email',
                'template_type': 'welcome',
                'subject': 'Welcome to {{ company.name }}!',
                'html_content': render_to_string('emails/welcome.html')
            },
            {
                'name': 'Interview Reminder',
                'template_type': 'reminder',
                'subject': 'Reminder: Interview Tomorrow',
                'html_content': render_to_string('emails/reminder.html')
            },
            {
                'name': 'Application Status',
                'template_type': 'rejection',
                'subject': 'Update on Your Application',
                'html_content': render_to_string('emails/rejection.html')
            }
        ]

        for template_data in templates:
            EmailTemplate.objects.get_or_create(
                company=instance,
                name=template_data['name'],
                defaults=template_data
            )