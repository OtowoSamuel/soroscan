from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ingest", "0041_eventdeduplicationconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlacklistedContract",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "contract_id",
                    models.CharField(
                        db_index=True,
                        help_text="Stellar contract address to block from indexing (C...)",
                        max_length=56,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Contract address must start with 'C' and be exactly 56 characters using valid Base32 characters (A-Z, 2-7).",
                                regex="^C[A-Z2-7]{55}$",
                            )
                        ],
                    ),
                ),
                (
                    "reason",
                    models.TextField(
                        blank=True,
                        help_text="Human-readable explanation of why this contract is blacklisted",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
                (
                    "added_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who added this entry",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="blacklisted_contracts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Blacklisted Contract",
                "verbose_name_plural": "Blacklisted Contracts",
                "ordering": ["-created_at"],
            },
        ),
    ]
