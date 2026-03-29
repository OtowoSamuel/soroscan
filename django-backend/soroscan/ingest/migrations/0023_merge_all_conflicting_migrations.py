# Generated merge migration to resolve conflicting 0019 migrations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0019_merge_20260327_1621"),
        ("ingest", "0019_merge_github_ci_conflicts"),
        ("ingest", "0022_trackedcontract_event_filter"),
    ]

    operations = []
