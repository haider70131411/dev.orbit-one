from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Avatar
from companies.models import Company
from notifications.utils import notify_avatar_added, notify_avatar_updated
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Avatar)
def notify_all_companies_avatar_change(sender, instance, created, **kwargs):
    """
    When a global avatar is added or updated by system admin,
    notify all companies in the system.
    """
    companies = Company.objects.all()
    
    for company in companies:
        try:
            if created:
                notify_avatar_added(company, instance.name)
            else:
                notify_avatar_updated(company, instance.name)
        except Exception as e:
            logger.error(f"Failed to notify company {company.id} about avatar {instance.id}: {str(e)}")
