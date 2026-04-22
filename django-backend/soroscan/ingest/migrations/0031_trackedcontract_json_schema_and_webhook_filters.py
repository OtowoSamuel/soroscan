from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0030_webhook_backoff_strategy"),
    ]

    operations = [
        migrations.AddField(
            model_name="trackedcontract",
            name="json_schema",
            field=models.JSONField(
                blank=True,
                help_text="Optional JSON Schema used to validate ingested event payloads.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="webhooksubscription",
            name="filter_condition",
            field=models.JSONField(
                blank=True,
                help_text="Optional JSON condition DSL used to route events to this webhook.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="webhooksubscription",
            name="signature_algorithm",
            field=models.CharField(
                choices=[("sha256", "SHA-256"), ("sha1", "SHA-1 (legacy)")],
                default="sha256",
                help_text="HMAC algorithm used for X-SoroScan-Signature header.",
                max_length=16,
            ),
        ),
    ]
