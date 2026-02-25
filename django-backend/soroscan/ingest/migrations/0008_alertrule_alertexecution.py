"""
Migration: AlertRule and AlertExecution models for event-driven notifications.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0007_apikey_contractquota"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlertRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=256)),
                (
                    "condition",
                    models.JSONField(
                        help_text="Condition AST: {'op': 'and', 'conditions': [...]}"
                    ),
                ),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("slack", "Slack"),
                            ("email", "Email"),
                            ("webhook", "Webhook"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "action_target",
                    models.TextField(
                        help_text="Slack channel, email address, or webhook URL"
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contract",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alert_rules",
                        to="ingest.trackedcontract",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AlertExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "Sent"), ("failed", "Failed")],
                        max_length=16,
                    ),
                ),
                ("response", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alert_executions",
                        to="ingest.contractevent",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="executions",
                        to="ingest.alertrule",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="alertexecution",
            index=models.Index(
                fields=["rule", "created_at"],
                name="ingest_alertexecution_rule_created_at_idx",
            ),
        ),
    ]
