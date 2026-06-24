"""Enable Postgres toast compression for event payload storage.

This keeps ContractEvent.payload queryable while letting PostgreSQL compress
the on-disk storage transparently.
"""

from django.db import migrations


def enable_payload_compression(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    statements = [
        'ALTER TABLE "ingest_contractevent" ALTER COLUMN "payload" SET COMPRESSION lz4',
        'ALTER TABLE "ingest_contractevent" ALTER COLUMN "decoded_payload" SET COMPRESSION lz4',
    ]
    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            try:
                cursor.execute(statement)
            except Exception:
                cursor.execute(statement.replace("lz4", "pglz"))


def disable_payload_compression(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "ingest_contractevent" ALTER COLUMN "payload" SET COMPRESSION pglz')
        cursor.execute('ALTER TABLE "ingest_contractevent" ALTER COLUMN "decoded_payload" SET COMPRESSION pglz')


class Migration(migrations.Migration):
    dependencies = [
        ("ingest", "0043_alter_webhooksubscription_retry_backoff_seconds_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_payload_compression, disable_payload_compression),
    ]