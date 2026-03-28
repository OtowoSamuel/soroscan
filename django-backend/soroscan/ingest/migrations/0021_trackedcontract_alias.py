from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ingest', '0020_trackedcontract_max_events_per_minute'),
    ]

    operations = [
        migrations.AddField(
            model_name='trackedcontract',
            name='alias',
            field=models.CharField(
                blank=True,
                default='',
                help_text="Optional friendly name/alias for easier identification (e.g. 'Token Transfer Contract')",
                max_length=256,
            ),
        ),
        migrations.AddIndex(
            model_name='trackedcontract',
            index=models.Index(fields=['alias'], name='ingest_trac_alias_idx'),
        ),
    ]
