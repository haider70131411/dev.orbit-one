# notifications/management/commands/send_test_email.py
from django.core.management.base import BaseCommand
from companies.models import Company
from notifications.services import EmailService


class Command(BaseCommand):
    help = 'Send a test email'
    
    def add_arguments(self, parser):
        parser.add_argument('company_id', type=int, help='Company ID')
        parser.add_argument('to_email', type=str, help='Recipient email')
        parser.add_argument('--subject', type=str, default='Test Email')
        parser.add_argument('--content', type=str, default='This is a test email.')
    
    def handle(self, *args, **options):
        try:
            company = Company.objects.get(id=options['company_id'])
            email_service = EmailService(company)
            
            html_content = email_service.create_branded_html(
                f"<h1>Test Email</h1><p>{options['content']}</p>"
            )
            
            email = email_service.send_single_email(
                to_email=options['to_email'],
                subject=options['subject'],
                html_content=html_content
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Test email queued successfully! Email ID: {email.id}'
                )
            )
            
        except Company.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Company with ID {options["company_id"]} not found')
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))