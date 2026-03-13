# Generated migration to add database indexes for meeting queries
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('meetings', '0002_add_not_held_status'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='meeting',
            index=models.Index(fields=['company', 'status', 'scheduled_datetime'], name='meetings_co_status_sched_idx'),
        ),
        migrations.AddIndex(
            model_name='meeting',
            index=models.Index(fields=['company', 'scheduled_datetime'], name='meetings_co_scheduled_idx'),
        ),
        migrations.AddIndex(
            model_name='meeting',
            index=models.Index(fields=['status', 'scheduled_datetime'], name='meetings_status_scheduled_idx'),
        ),
        migrations.AddIndex(
            model_name='meeting',
            index=models.Index(fields=['meeting_room_id'], name='meetings_room_id_idx'),
        ),
    ]

