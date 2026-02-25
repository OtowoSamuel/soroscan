"""
Migration: GIN index on ContractEvent.payload for fast full-text / JSON search.

This migration requires PostgreSQL. On non-PostgreSQL backends (e.g. SQLite
used in test environments) the index creation is skipped so that ``migrate``
succeeds during CI without needing a live Postgres instance.
"""
from django.contrib.postgres.indexes import GinIndex
from django.db import migrations


def _apply_gin_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ContractEvent = apps.get_model("ingest", "ContractEvent")
    index = GinIndex(fields=["payload"], name="ingest_contractevent_payload_gin")
    schema_editor.add_index(ContractEvent, index)


def _remove_gin_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ContractEvent = apps.get_model("ingest", "ContractEvent")
    index = GinIndex(fields=["payload"], name="ingest_contractevent_payload_gin")
    schema_editor.remove_index(ContractEvent, index)


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0008_alertrule_alertexecution"),
    ]

    operations = [
        migrations.RunPython(_apply_gin_index, _remove_gin_index, elidable=True),
    ]
