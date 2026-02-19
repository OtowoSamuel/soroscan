# Generated manually for issue #17 (event schema versioning)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TrackedContract",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("contract_id", models.CharField(db_index=True, help_text="Stellar contract address (C...)", max_length=56, unique=True)),
                ("name", models.CharField(help_text="Human-readable contract name", max_length=100)),
                ("description", models.TextField(blank=True, help_text="Optional description")),
                ("abi_schema", models.JSONField(blank=True, help_text="Optional ABI/schema for decoding events", null=True)),
                ("is_active", models.BooleanField(default=True, help_text="Whether indexing is active")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(help_text="User who registered this contract", on_delete=django.db.models.deletion.CASCADE, related_name="tracked_contracts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="EventSchema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField(help_text="Schema version number")),
                ("event_type", models.CharField(help_text="Event type/name this schema describes", max_length=128)),
                ("json_schema", models.JSONField(help_text="JSON Schema for validating event payloads")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("contract", models.ForeignKey(help_text="Contract this schema applies to", on_delete=django.db.models.deletion.CASCADE, related_name="event_schemas", to="ingest.trackedcontract")),
            ],
            options={
                "ordering": ["contract", "event_type", "-version"],
            },
        ),
        migrations.CreateModel(
            name="ContractEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(db_index=True, help_text="Event type/name (e.g., 'swap', 'transfer')", max_length=100)),
                ("schema_version", models.PositiveIntegerField(blank=True, help_text="EventSchema version used for validation (if any)", null=True)),
                ("validation_status", models.CharField(choices=[("passed", "Passed"), ("failed", "Failed")], db_index=True, default="passed", help_text="Result of schema validation", max_length=32)),
                ("payload", models.JSONField(help_text="Decoded event payload")),
                ("payload_hash", models.CharField(db_index=True, help_text="SHA-256 hash of the payload", max_length=64)),
                ("ledger", models.PositiveBigIntegerField(db_index=True, help_text="Ledger sequence number")),
                ("timestamp", models.DateTimeField(db_index=True, help_text="Event timestamp")),
                ("tx_hash", models.CharField(help_text="Transaction hash", max_length=64)),
                ("raw_xdr", models.TextField(blank=True, help_text="Raw XDR for debugging")),
                ("contract", models.ForeignKey(help_text="The contract that emitted this event", on_delete=django.db.models.deletion.CASCADE, related_name="events", to="ingest.trackedcontract")),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
        migrations.CreateModel(
            name="WebhookSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(blank=True, help_text="Event type filter (blank = all events)", max_length=100)),
                ("target_url", models.URLField(help_text="URL to POST event data to")),
                ("secret", models.CharField(help_text="Secret for HMAC signature verification", max_length=64)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_triggered", models.DateTimeField(blank=True, null=True)),
                ("failure_count", models.PositiveIntegerField(default=0)),
                ("contract", models.ForeignKey(help_text="Contract to monitor", on_delete=django.db.models.deletion.CASCADE, related_name="webhooks", to="ingest.trackedcontract")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="IndexerState",
            fields=[
                ("key", models.CharField(max_length=50, primary_key=True, serialize=False, unique=True)),
                ("value", models.CharField(max_length=200)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="eventschema",
            constraint=models.UniqueConstraint(fields=("contract", "version", "event_type"), name="ingest_eventschema_contract_version_event_type_uniq"),
        ),
        migrations.AddIndex(
            model_name="trackedcontract",
            index=models.Index(fields=["contract_id", "is_active"], name="ingest_trac_contrac_9b2b0d_idx"),
        ),
        migrations.AddIndex(
            model_name="contractevent",
            index=models.Index(fields=["contract", "event_type", "timestamp"], name="ingest_cont_contract_7f8c2a_idx"),
        ),
        migrations.AddIndex(
            model_name="contractevent",
            index=models.Index(fields=["ledger"], name="ingest_cont_ledger_2a1b3c_idx"),
        ),
        migrations.AddIndex(
            model_name="contractevent",
            index=models.Index(fields=["tx_hash"], name="ingest_cont_tx_hash_4d5e6f_idx"),
        ),
    ]
