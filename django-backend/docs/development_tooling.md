# SoroScan Development Tooling

This document covers the new utilities added for database seeding, event replay, bulk import, and backup verification.

---

## Database Seeder (`seed_database`)

Populates the development database with realistic test data.

### Commands

```bash
cd django-backend
```

Full seed with default fixture:
```bash
python manage.py seed_database
```

Use a custom fixture file:
```bash
python manage.py seed_database --fixture=fixtures/custom.json
```

Use a predefined scenario:
```bash
python manage.py seed_database --scenario=minimal
python manage.py seed_database --scenario=webhook
```

Clear all seeded data before re-seeding:
```bash
python manage.py seed_database --clear
```

### Fixture Format (`fixtures/development.json`)

```json
{
    "organizations": [...],
    "teams": [...],
    "users": [...],
    "memberships": [...],
    "team_memberships": [...],
    "contracts": [...],
    "events": {
        "per_contract": 20,
        "contracts": ["CAAAA..."],
        "event_types": ["swap", "deposit"],
        "days_back": 14
    },
    "webhooks": [...],
    "webhook_delivery_logs": {
        "per_webhook": 5,
        "status_codes": [200, 200, 200, 500, 408]
    },
    "alert_rules": [...],
    "api_keys": [...]
}
```

---

## Local Event Replay (`replay_events`)

Replay ContractEvent records through webhook delivery for debugging and retesting.

```bash
cd django-backend
```

Basic replay (dispatches to all active webhooks):
```bash
python manage.py replay_events --contract=CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAZ2KZ --limit=10
```

Dry run preview:
```bash
python manage.py replay_events --contract=CAAAA... --dry-run
```

Filter by event type:
```bash
python manage.py replay_events --contract=CAAAA... --event-type=swap
```

Filter by ledger range:
```bash
python manage.py replay_events --contract=CAAAA... --from-ledger=100 --to-ledger=1000
```

Filter by date range:
```bash
python manage.py replay_events --contract=CAAAA... --from-date=2025-01-01 --to-date=2025-01-31
```

Replay to a single webhook:
```bash
python manage.py replay_events --contract=CAAAA... --webhook-id=3
```

Write report to JSON:
```bash
python manage.py replay_events --contract=CAAAA... --output-json=replay_report.json
```

---

## Bulk Metadata Import (`bulk_import_metadata`)

Import contract metadata from CSV or JSON with validation and rollback support.

```bash
cd django-backend
```

CSV import:
```bash
python manage.py bulk_import_metadata --input=contracts.csv --format=csv
```

JSON import:
```bash
python manage.py bulk_import_metadata --input=contracts.json --format=json
```

Dry run (validate without changing DB):
```bash
python manage.py bulk_import_metadata --input=contracts.csv --dry-run
```

Skip errors instead of rolling back:
```bash
python manage.py bulk_import_metadata --input=contracts.csv --on-error=skip
```

Write import report:
```bash
python manage.py bulk_import_metadata --input=contracts.csv --report=import_report.json
```

### CSV Format

```
contract_id,name,description,tags,documentation_url,github_repo,team_email
CAAAA...,Stablecoin Swap,An AMM,"defi,amm,swap",https://...,https://...,team@acme.example.com
```

### JSON Format

```json
{
  "metadata": [
    {
      "contract_id": "CAAAA...",
      "name": "Stablecoin Swap",
      "description": "An AMM",
      "tags": ["defi", "amm", "swap"],
      "documentation_url": "https://...",
      "github_repo": "https://...",
      "team_email": "team@acme.example.com"
    }
  ]
}
```

---

## Backup Verification & Testing (`test_backup.py`)

Automated backup verification and restoration testing.

```bash
cd scripts/backup
```

Full test (verify + restore):
```bash
python test_backup.py --bucket=soroscan-backups --prefix=pg-backups --db-url=postgresql://...
```

Or use environment variables:
```bash
export DATABASE_URL=postgresql://user:pass@host:5432/dbname
export S3_BUCKET=soroscan-backups
export S3_PREFIX=pg-backups
python test_backup.py full-test
```

Verify only (no restore):
```bash
python test_backup.py verify-only
```

Restore only:
```bash
python test_backup.py restore-only --s3-key=pg-backups/20250101.dump.gz
```

Print manual runbook:
```bash
python test_backup.py --runbook
```

Write test report to JSON:
```bash
python test_backup.py full-test --output=backup_report.json
```

Alerting:
- Set `SLACK_WEBHOOK_URL` to receive alerts on test failure.
- Results include RTO (restore duration) and RPO (time since backup) in seconds.

---

## Automation

### Nightly Backup Verification (cron)

```cron
0 6 * * * cd /path/to/soroscan/scripts/backup && python test_backup.py verify-only >> /var/log/backup_verify.log 2>&1
```

### Weekly Restoration Test (cron)

```cron
0 4 * * 0 cd /path/to/soroscan/scripts/backup && python test_backup.py restore-only >> /var/log/backup_restore.log 2>&1
```
