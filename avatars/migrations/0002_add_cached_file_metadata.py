# Generated migration for adding cached file metadata fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('avatars', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='avatar',
            name='vrm_file_url',
            field=models.URLField(blank=True, null=True, help_text='Cached URL for VRM file'),
        ),
        migrations.AddField(
            model_name='avatar',
            name='preview_image_url',
            field=models.URLField(blank=True, null=True, help_text='Cached URL for preview image'),
        ),
        migrations.AddField(
            model_name='avatar',
            name='vrm_file_size_bytes',
            field=models.BigIntegerField(default=0, help_text='Cached file size in bytes'),
        ),
    ]

