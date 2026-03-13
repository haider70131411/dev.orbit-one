# Generated migration to backfill cached file metadata for existing avatars
from django.db import migrations


def backfill_file_metadata(apps, schema_editor):
    """Backfill vrm_file_url, preview_image_url, and vrm_file_size_bytes for existing avatars"""
    Avatar = apps.get_model('avatars', 'Avatar')
    
    updated_count = 0
    error_count = 0
    
    for avatar in Avatar.objects.all():
        try:
            # Backfill VRM file URL and size
            if avatar.vrm_file:
                try:
                    avatar.vrm_file_url = avatar.vrm_file.url
                    avatar.vrm_file_size_bytes = avatar.vrm_file.size
                except Exception as e:
                    print(f"Warning: Could not cache VRM metadata for avatar {avatar.id}: {e}")
                    avatar.vrm_file_url = None
                    avatar.vrm_file_size_bytes = 0
            else:
                avatar.vrm_file_url = None
                avatar.vrm_file_size_bytes = 0
            
            # Backfill preview image URL
            if avatar.preview_image:
                try:
                    avatar.preview_image_url = avatar.preview_image.url
                except Exception as e:
                    print(f"Warning: Could not cache preview image URL for avatar {avatar.id}: {e}")
                    avatar.preview_image_url = None
            else:
                avatar.preview_image_url = None
            
            # Save without triggering signals/metadata update
            Avatar.objects.filter(pk=avatar.pk).update(
                vrm_file_url=avatar.vrm_file_url,
                preview_image_url=avatar.preview_image_url,
                vrm_file_size_bytes=avatar.vrm_file_size_bytes
            )
            updated_count += 1
            
        except Exception as e:
            print(f"Error processing avatar {avatar.id}: {e}")
            error_count += 1
    
    print(f"Backfill complete: {updated_count} avatars updated, {error_count} errors")


def reverse_backfill(apps, schema_editor):
    """Reverse migration - clear cached metadata"""
    Avatar = apps.get_model('avatars', 'Avatar')
    Avatar.objects.all().update(
        vrm_file_url=None,
        preview_image_url=None,
        vrm_file_size_bytes=0
    )


class Migration(migrations.Migration):

    dependencies = [
        ('avatars', '0002_add_cached_file_metadata'),
    ]

    operations = [
        migrations.RunPython(backfill_file_metadata, reverse_backfill),
    ]

