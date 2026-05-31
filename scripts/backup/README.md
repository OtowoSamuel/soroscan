# PostgreSQL Backup & Recovery

## Overview

Two complementary strategies:

| Strategy | Script | Schedule | Use case |
|---|---|---|---|
| Daily pg_dump | `pg_backup.sh` | CronJob 02:00 UTC | Full restore to any daily snapshot |
| WAL archiving | `wal_archive.sh` | Continuous (archive_command) | Point-in-time recovery (PITR) |

---

## Daily pg_dump Backup

### How it works
1. Runs `pg_dump --format=custom --compress=9`
2. Uploads to `s3://$S3_BUCKET/$S3_PREFIX/<timestamp>.dump.gz`
3. Prunes backups older than `BACKUP_RETENTION_DAYS` (default: 30)

### Deploy (Kubernetes)
```bash
# Create the backup configmap
kubectl apply -f k8s/backup-configmap.yaml

# Add AWS credentials to the existing soroscan-secrets:
kubectl patch secret soroscan-secrets -n soroscan \
  --type=merge \
  -p '{"stringData":{"AWS_ACCESS_KEY_ID":"...","AWS_SECRET_ACCESS_KEY":"..."}}'

# Build and push the backup image
docker build -t soroscan/pg-backup:latest scripts/backup/
docker push soroscan/pg-backup:latest

# Deploy the CronJob
kubectl apply -f k8s/backup-cronjob.yaml
```

### Trigger a manual backup
```bash
kubectl create job --from=cronjob/soroscan-pg-backup manual-backup-$(date +%s) -n soroscan
```

### Restore from a backup
```bash
# List available backups
aws s3 ls s3://$S3_BUCKET/pg-backups/

# Restore latest (or pass a specific key as argument)
export DATABASE_URL="postgresql://user:pass@host:5432/soroscan"
export S3_BUCKET="soroscan-backups"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
./scripts/backup/pg_restore.sh
# Or restore a specific backup:
./scripts/backup/pg_restore.sh pg-backups/20250115T020000Z.dump.gz
```

---

## WAL Archiving (PITR)

### How it works
PostgreSQL calls `wal_archive.sh %p %f` for every completed WAL segment,
uploading it to `s3://$S3_BUCKET/$S3_WAL_PREFIX/`. This enables recovery
to any point in time between daily backups.

### Configure PostgreSQL
Mount `postgresql-wal.conf` settings into your PostgreSQL instance:

```bash
# Docker Compose example
volumes:
  - ./scripts/backup/postgresql-wal.conf:/etc/postgresql/conf.d/wal.conf:ro
  - ./scripts/backup:/scripts:ro
```

Or add to your Helm chart's `postgresql.conf` override.

### Point-in-time recovery procedure
1. Restore the most recent daily backup before your target time:
   ```bash
   ./scripts/backup/pg_restore.sh pg-backups/20250115T020000Z.dump.gz
   ```

2. Add recovery settings to `postgresql.conf`:
   ```
   restore_command = '/scripts/wal_restore.sh %f %p'
   recovery_target_time = '2025-01-15 14:30:00 UTC'
   recovery_target_action = 'promote'
   ```

3. Create `recovery.signal` (PG12+) and start PostgreSQL:
   ```bash
   touch $PGDATA/recovery.signal
   pg_ctl start
   ```

4. PostgreSQL replays WAL segments until the target time, then promotes.

---

## Automated Backup Testing

`test_backup.py` validates backup integrity and performs restoration tests.

```bash
python test_backup.py full-test
python test_backup.py verify-only
python test_backup.py restore-only --s3-key=pg-backups/<key>
python test_backup.py --runbook
```

Set `SLACK_WEBHOOK_URL` to receive alerts on failure.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | `postgresql://user:pass@host:port/dbname` |
| `S3_BUCKET` | Yes | S3 bucket name |
| `S3_PREFIX` | No | Key prefix for dumps (default: `pg-backups`) |
| `S3_WAL_PREFIX` | No | Key prefix for WAL (default: `wal-archive`) |
| `AWS_ACCESS_KEY_ID` | Yes | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | Yes | AWS credentials |
| `AWS_DEFAULT_REGION` | Yes | e.g. `us-east-1` |
| `AWS_ENDPOINT_URL` | No | For MinIO/Localstack |
| `BACKUP_RETENTION_DAYS` | No | Days to keep dumps (default: `30`) |
| `RESTORE_JOBS` | No | Parallel restore jobs (default: `4`) |
