# notifications/management/commands/fetch_inbox.py
from django.core.management.base import BaseCommand
from companies.models import Company
from notifications.services import InboxService


class Command(BaseCommand):
    help = 'Fetch inbox emails for a company'
    
    def add_arguments(self, parser):
        parser.add_argument('company_id', type=int, help='Company ID')
        parser.add_argument('--limit', type=int, default=50, help='Number of emails to fetch')
    
    def handle(self, *args, **options):
        try:
            company = Company.objects.get(id=options['company_id'])
            inbox_service = InboxService(company)
            
            self.stdout.write('Fetching emails...')
            inbox_service.fetch_emails(limit=options['limit'])
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully fetched emails for {company.name}'
                )
            )
            
        except Company.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Company with ID {options["company_id"]} not found')
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
