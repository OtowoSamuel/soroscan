# Generated merge migration to resolve GitHub CI conflicts

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("ingest", "0018_merge_0016_add_ingesterror_0017_eventdeduplicationlog"),
        ("ingest", "0022_trackedcontract_event_filter"),
    ]

    operations = []
