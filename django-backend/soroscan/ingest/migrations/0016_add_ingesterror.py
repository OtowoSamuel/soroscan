# Generated migration for IngestError model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ingest', '0015_merge_notification_and_teams'),
    ]

    operations = [
        migrations.CreateModel(
            name='IngestError',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('error_type', models.CharField(choices=[('decode_error', 'Decode Error'), ('validation_error', 'Validation Error'), ('rpc_error', 'RPC Error')], db_index=True, max_length=32)),
                ('contract_id', models.CharField(db_index=True, help_text='Contract that caused the error', max_length=56)),
                ('error_message', models.TextField(help_text='Full error message')),
                ('sample_error', models.CharField(help_text='Truncated error message for display', max_length=500)),
                ('ledger', models.PositiveBigIntegerField(blank=True, help_text='Ledger where error occurred', null=True)),
                ('tx_hash', models.CharField(blank=True, help_text='Transaction hash if available', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='ingesterror',
            index=models.Index(fields=['error_type', 'contract_id', 'created_at'], name='ingest_inge_error_t_b8e123_idx'),
        ),
        migrations.AddIndex(
            model_name='ingesterror',
            index=models.Index(fields=['created_at'], name='ingest_inge_created_f8a456_idx'),
        ),
    ]
