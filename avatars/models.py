import os
from django.db import models
from django.core.validators import FileExtensionValidator
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver
from django.utils.text import slugify
import uuid
from django.utils import timezone
from django.core.files.storage import default_storage


def avatar_vrm_path(instance, filename):
    """Generate unique path for VRM files"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    return os.path.join('avatars', 'vrm', filename)


def avatar_image_path(instance, filename):
    """Generate unique path for avatar images"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    return os.path.join('avatars', 'images', filename)


class Avatar(models.Model):
    """Model for storing VRM avatars with preview images"""
    
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique name for the avatar"
    )
    
    slug = models.SlugField(
        max_length=255,
        unique=True,
        blank=True,
        help_text="URL-friendly version of name"
    )
    
    vrm_file = models.FileField(
        upload_to=avatar_vrm_path,
        validators=[FileExtensionValidator(allowed_extensions=['vrm'])],
        help_text="VRM avatar file",
        blank=True,
        null=True,
    )
    
    preview_image = models.ImageField(
        upload_to=avatar_image_path,
        help_text="Preview image of the avatar",
        blank=True,
        null=True,
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description of the avatar"
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this avatar is available for selection"
    )
    
    # Cached file metadata (computed at upload/update time)
    vrm_file_url = models.URLField(
        blank=True,
        null=True,
        help_text="Cached URL for VRM file (computed at upload time)"
    )
    preview_image_url = models.URLField(
        blank=True,
        null=True,
        help_text="Cached URL for preview image (computed at upload time)"
    )
    vrm_file_size_bytes = models.BigIntegerField(
        default=0,
        help_text="Cached file size in bytes (computed at upload time)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Avatar'
        verbose_name_plural = 'Avatars'
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        """
        Override save to auto-generate slug and cache file metadata.
        Metadata is cached whenever files are present - this only runs during saves
        (create/update), not during GET requests, so performance impact is minimal.
        """
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure slug is unique
            original_slug = self.slug
            counter = 1
            while Avatar.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        
        # Cache file URLs and size when files are present
        # This runs during save (infrequent), not GET requests (frequent)
        self._cache_file_metadata()
        
        super().save(*args, **kwargs)
    
    def _cache_file_metadata(self):
        """
        Compute and cache file URLs and sizes when FileFields are present.
        When vrm_file/preview_image are not set (e.g. direct R2 upload path),
        do NOT overwrite vrm_file_url/preview_image_url – they are set by the serializer.
        """
        # Cache VRM file URL and size only when we have a file
        if self.vrm_file:
            try:
                self.vrm_file_url = self.vrm_file.url
                self.vrm_file_size_bytes = self.vrm_file.size
            except Exception as e:
                if self.pk:
                    print(f"Warning: Could not cache VRM file metadata: {e}")
                self.vrm_file_url = None
                self.vrm_file_size_bytes = 0
        # else: leave vrm_file_url and vrm_file_size_bytes unchanged (direct-create sets them)

        # Cache preview image URL only when we have an image
        if self.preview_image:
            try:
                self.preview_image_url = self.preview_image.url
            except Exception as e:
                if self.pk:
                    print(f"Warning: Could not cache preview image URL: {e}")
                self.preview_image_url = None
        # else: leave preview_image_url unchanged (direct-create sets it)
    
    @property
    def vrm_file_size(self):
        """
        Return file size in MB from cached value.
        Falls back to computing if cache is missing (backward compatibility).
        """
        if self.vrm_file_size_bytes > 0:
            return round(self.vrm_file_size_bytes / (1024 * 1024), 2)
        
        # Fallback: compute if cache is missing (for existing records)
        if self.vrm_file:
            try:
                size = self.vrm_file.size
                # Update cache for next time
                self.vrm_file_size_bytes = size
                # Save without triggering metadata update (avoid recursion)
                Avatar.objects.filter(pk=self.pk).update(vrm_file_size_bytes=size)
                return round(size / (1024 * 1024), 2)
            except Exception:
                return 0
        return 0


@receiver(pre_delete, sender=Avatar)
def delete_avatar_files(sender, instance, **kwargs):
    """
    Delete VRM file and preview image when Avatar instance is deleted
    (works for both local and R2)
    """
    storage = default_storage

    # Delete VRM file
    if instance.vrm_file and storage.exists(instance.vrm_file.name):
        try:
            storage.delete(instance.vrm_file.name)
        except Exception as e:
            print(f"Error deleting VRM file from storage: {e}")

    # Delete preview image
    if instance.preview_image and storage.exists(instance.preview_image.name):
        try:
            storage.delete(instance.preview_image.name)
        except Exception as e:
            print(f"Error deleting preview image from storage: {e}")


@receiver(pre_save, sender=Avatar)
def delete_old_files_on_update(sender, instance, **kwargs):
    """
    Delete old files when Avatar is updated with new files
    (works for both local and R2)
    """
    if not instance.pk:
        return

    try:
        old_instance = Avatar.objects.get(pk=instance.pk)
    except Avatar.DoesNotExist:
        return

    storage = default_storage

    # VRM file changed
    if old_instance.vrm_file and old_instance.vrm_file != instance.vrm_file:
        if storage.exists(old_instance.vrm_file.name):
            try:
                storage.delete(old_instance.vrm_file.name)
            except Exception as e:
                print(f"Error deleting old VRM file: {e}")

    # Preview image changed
    if old_instance.preview_image and old_instance.preview_image != instance.preview_image:
        if storage.exists(old_instance.preview_image.name):
            try:
                storage.delete(old_instance.preview_image.name)
            except Exception as e:
                print(f"Error deleting old preview image: {e}")