# notifications/management/commands/generate_email_template.py
from django.core.management.base import BaseCommand
from companies.models import Company
from notifications.models import EmailTemplate


class Command(BaseCommand):
    help = 'Generate default email templates for a company'
    
    def add_arguments(self, parser):
        parser.add_argument('company_id', type=int, help='Company ID')
    
    def handle(self, *args, **options):
        try:
            company = Company.objects.get(id=options['company_id'])
            
            templates = [
                {
                    'name': 'Interviewee Invitation',
                    'template_type': 'invitation',
                    'subject': 'Interview Invitation - {{ position }}',
                    'html_content': open('notifications/templates/emails/interviewee_invitation.html').read()
                },
                {
                    'name': 'Interviewer Invitation',
                    'template_type': 'invitation',
                    'subject': 'Interview Invitation - {{ position }}',
                    'html_content': open('notifications/templates/emails/interviewer_invitation.html').read()
                },
                {
                    'name': 'Interviewee OTP',
                    'template_type': 'otp',
                    'subject': 'Otp for meeting access',
                    'html_content': open('notifications/templates/emails/meeting_otp.html').read()
                },
                {
                    'name': 'Welcome Email',
                    'template_type': 'welcome',
                    'subject': 'Welcome to {{ company.name }}!',
                    'html_content': open('notifications/templates/emails/welcome.html').read()
                },
                {
                    'name': 'Interview Reminder',
                    'template_type': 'reminder',
                    'subject': 'Reminder: Interview Tomorrow',
                    'html_content': open('notifications/templates/emails/reminder.html').read()
                },
                {
                    'name': 'Application Status',
                    'template_type': 'rejection',
                    'subject': 'Update on Your Application',
                    'html_content': open('notifications/templates/emails/rejection.html').read()
                }
            ]
            
            created_count = 0
            for template_data in templates:
                template, created = EmailTemplate.objects.get_or_create(
                    company=company,
                    name=template_data['name'],
                    defaults=template_data
                )
                if created:
                    created_count += 1
                    self.stdout.write(f"Created: {template.name}")
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created {created_count} templates for {company.name}'
                )
            )
            
        except Company.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Company with ID {options["company_id"]} not found')
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))