# notifications/management/commands/email_analytics.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from companies.models import Company
from notifications.models import EmailAnalytics
from datetime import timedelta


class Command(BaseCommand):
    help = 'Generate email analytics report'
    
    def add_arguments(self, parser):
        parser.add_argument('company_id', type=int, help='Company ID')
        parser.add_argument('--days', type=int, default=30, help='Number of days')
    
    def handle(self, *args, **options):
        try:
            company = Company.objects.get(id=options['company_id'])
            days = options['days']
            
            start_date = timezone.now().date() - timedelta(days=days)
            
            analytics = EmailAnalytics.objects.filter(
                company=company,
                date__gte=start_date
            ).order_by('-date')
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nEmail Analytics for {company.name} (Last {days} days)'
                )
            )
            self.stdout.write('=' * 80)
            
            total_sent = sum(a.emails_sent for a in analytics)
            total_opened = sum(a.emails_opened for a in analytics)
            total_clicked = sum(a.emails_clicked for a in analytics)
            
            self.stdout.write(f'\nTotal Emails Sent: {total_sent}')
            self.stdout.write(f'Total Opened: {total_opened}')
            self.stdout.write(f'Total Clicked: {total_clicked}')
            
            if total_sent > 0:
                open_rate = (total_opened / total_sent) * 100
                click_rate = (total_clicked / total_sent) * 100
                
                self.stdout.write(f'\nOverall Open Rate: {open_rate:.2f}%')
                self.stdout.write(f'Overall Click Rate: {click_rate:.2f}%')
            
            self.stdout.write('\n\nDaily Breakdown:')
            self.stdout.write('-' * 80)
            
            for a in analytics[:10]:  # Show last 10 days
                self.stdout.write(
                    f'{a.date}: Sent: {a.emails_sent}, '
                    f'Open Rate: {a.open_rate:.1f}%, '
                    f'Click Rate: {a.click_rate:.1f}%'
                )
            
        except Company.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Company with ID {options["company_id"]} not found')
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))