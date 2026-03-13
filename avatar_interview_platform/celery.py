# ==========================================
# celery.py (in your project root)
# ==========================================

import os
import logging.config
from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'avatar_interview_platform.settings')

app = Celery('avatar_interview_platform')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@setup_logging.connect
def configure_celery_logging(**kwargs):
    """Use Django's LOGGING config for Celery worker logs."""
    from django.conf import settings
    if hasattr(settings, 'LOGGING') and settings.LOGGING:
        logging.config.dictConfig(settings.LOGGING)
    return True  # Prevent Celery from overriding our config


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')