from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.core.files.storage import default_storage

from .models import Meeting


@receiver(pre_delete, sender=Meeting)
def delete_recording_file_on_meeting_delete(sender, instance: Meeting, **kwargs):
    """
    Delete the recording file from storage when a Meeting is deleted.
    Works for both local storage and R2 (S3-compatible) via Django's storage backend.
    """
    if instance.recording_file:
        storage = default_storage
        file_name = instance.recording_file.name
        try:
            if storage.exists(file_name):
                storage.delete(file_name)
        except Exception as e:
            # Don't block meeting deletion if storage cleanup fails
            print(f"Error deleting meeting recording file from storage ({file_name}): {e}")

