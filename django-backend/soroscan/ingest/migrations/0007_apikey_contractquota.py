"""
Migration: APIKey and ContractQuota models for tiered rate limiting.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0006_add_contract_timestamp_index"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="APIKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=128)),
                (
                    "key",
                    models.CharField(
                        db_index=True,
                        max_length=64,
                        unique=True,
                    ),
                ),
                (
                    "tier",
                    models.CharField(
                        choices=[
                            ("free", "Free"),
                            ("pro", "Pro"),
                            ("enterprise", "Enterprise"),
                        ],
                        default="free",
                        max_length=16,
                    ),
                ),
                (
                    "quota_per_hour",
                    models.IntegerField(
                        help_text="Max requests per hour. Auto-set from tier on creation."
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ContractQuota",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "quota_per_hour",
                    models.IntegerField(
                        help_text=(
                            "Custom requests-per-hour for this contract. "
                            "Cannot exceed the key tier limit."
                        )
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "api_key",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contract_quotas",
                        to="ingest.apikey",
                    ),
                ),
                (
                    "contract",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contract_quotas",
                        to="ingest.trackedcontract",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("contract", "api_key")},
            },
        ),
    ]
