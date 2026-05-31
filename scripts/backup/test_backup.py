#!/usr/bin/env python3
"""
Backup verification and restoration testing for SoroScan.

Features:
  - Backup verification (checks S3 backup exists, size, pg_dump integrity)
  - Restoration testing (downloads backup and verifies it restores)
  - RTO/RPO metrics tracking
  - Alerting hooks (Slack/webhook) on failure
  - Runbook output for manual restore steps

Usage (locally):
    python scripts/backup/test_backup.py --bucket=soroscan-backups --prefix=pg-backups --db-url=postgresql://...

    python scripts/backup/test_backup.py verify-only
    python scripts/backup/test_backup.py restore-only --s3-key=pg-backups/20250101.dump.gz
    python scripts/backup/test_backup.py full-test

Environment variables:
    DATABASE_URL         Target database for restore verification
    S3_BUCKET            Backup bucket name
    S3_PREFIX            Backup key prefix
    AWS_ACCESS_KEY_ID    (optional, uses default credential chain)
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION
    SLACK_WEBHOOK_URL    (optional) alert destination
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import boto3
except ImportError:
    boto3 = None


REQUIRED_ENV = ["DATABASE_URL", "S3_BUCKET", "S3_PREFIX"]


@dataclass
class TestResult:
    test_name: str
    passed: bool
    duration_seconds: float
    details: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class BackupTestReport:
    timestamp: str
    bucket: str
    prefix: str
    verify_result: Optional[TestResult] = None
    restore_result: Optional[TestResult] = None
    rto_seconds: Optional[float] = None
    rpo_seconds: Optional[float] = None
    overall_passed: bool = False

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "bucket": self.bucket,
            "prefix": self.prefix,
            "verify": self.verify_result,
            "restore": self.restore_result,
            "rto_seconds": self.rto_seconds,
            "rpo_seconds": self.rpo_seconds,
            "overall_passed": self.overall_passed,
        }


class BackupTester:
    def __init__(
        self,
        db_url: str,
        bucket: str,
        prefix: str,
        s3_key: str | None = None,
        restore_db_url: str | None = None,
        slack_webhook: str | None = None,
        region: str = "us-east-1",
    ):
        self.db_url = db_url
        self.bucket = bucket
        self.prefix = prefix
        self.s3_key = s3_key
        self.restore_db_url = restore_db_url or db_url
        self.slack_webhook = slack_webhook
        self.region = region
        self.s3_client = None
        if boto3:
            self.s3_client = boto3.client("s3", region_name=region)

    def latest_backup_key(self) -> str:
        if self.s3_key:
            return self.s3_key
        if not self.s3_client:
            raise RuntimeError("boto3 is not installed. Install it or pass --s3-key.")

        response = self.s3_client.list_objects_v2(
            Bucket=self.bucket, Prefix=f"{self.prefix}/"
        )
        contents = response.get("Contents", [])
        if not contents:
            raise RuntimeError(f"No backups found in s3://{self.bucket}/{self.prefix}/")

        contents.sort(key=lambda obj: obj["LastModified"], reverse=True)
        return contents[0]["Key"]

    def verify_backup(self, s3_key: str) -> TestResult:
        start = time.monotonic()
        try:
            if not self.s3_client:
                raise RuntimeError("boto3 not installed")

            head = self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            size_bytes = head.get("ContentLength", 0)

            if size_bytes == 0:
                return TestResult(
                    test_name="verify_backup",
                    passed=False,
                    duration_seconds=time.monotonic() - start,
                    details="Backup file is 0 bytes.",
                    metadata={"s3_key": s3_key, "size_bytes": 0},
                )

            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = Path(tmpdir) / Path(s3_key).name
                self.s3_client.download_file(self.bucket, s3_key, str(local_path))

                result = subprocess.run(
                    ["pg_restore", "--list", str(local_path)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return TestResult(
                        test_name="verify_backup",
                        passed=False,
                        duration_seconds=time.monotonic() - start,
                        details=f"pg_restore --list failed: {result.stderr}",
                        metadata={"s3_key": s3_key, "size_bytes": size_bytes},
                    )

                archive_ok = result.stdout.strip() != ""

            return TestResult(
                test_name="verify_backup",
                passed=True,
                duration_seconds=time.monotonic() - start,
                details=f"Backup verified. Size={size_bytes} bytes.",
                metadata={"s3_key": s3_key, "size_bytes": size_bytes, "archive_valid": archive_ok},
            )
        except Exception as exc:
            return TestResult(
                test_name="verify_backup",
                passed=False,
                duration_seconds=time.monotonic() - start,
                details=str(exc),
                metadata={"s3_key": s3_key},
            )

    def restore_backup(self, s3_key: str) -> TestResult:
        start = time.monotonic()
        try:
            self.run_restore_script(s3_key)
            elapsed = time.monotonic() - start
            return TestResult(
                test_name="restore_backup",
                passed=True,
                duration_seconds=elapsed,
                details=f"Restored backup {s3_key} successfully.",
                metadata={"s3_key": s3_key},
            )
        except Exception as exc:
            return TestResult(
                test_name="restore_backup",
                passed=False,
                duration_seconds=time.monotonic() - start,
                details=str(exc),
                metadata={"s3_key": s3_key},
            )

    def run_restore_script(self, s3_key: str):
        script_path = Path(__file__).resolve().parent / "pg_restore.sh"
        if not script_path.exists():
            raise RuntimeError(f"Restore script not found: {script_path}")

        env = os.environ.copy()
        env.update({
            "DATABASE_URL": self.restore_db_url,
            "S3_BUCKET": self.bucket,
            "S3_PREFIX": self.prefix,
            "AWS_DEFAULT_REGION": self.region,
        })

        result = subprocess.run(
            ["bash", str(script_path), s3_key],
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Restore script failed (exit {result.returncode}): {result.stderr}"
            )

    def compute_rpo(self, s3_key: str) -> float:
        try:
            timestamp_part = Path(s3_key).stem.replace(".dump", "")
            for fmt in ("%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    backup_time = datetime.strptime(timestamp_part, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            else:
                return 0.0
            return (datetime.now(timezone.utc) - backup_time).total_seconds()
        except Exception:
            return 0.0

    def run_full_test(self) -> BackupTestReport:
        now = datetime.now(timezone.utc).isoformat()
        report = BackupTestReport(timestamp=now, bucket=self.bucket, prefix=self.prefix)

        s3_key = self.latest_backup_key()
        report.verify_result = self.verify_backup(s3_key)
        if report.verify_result.passed:
            report.restore_result = self.restore_backup(s3_key)
            if report.restore_result.passed:
                report.rto_seconds = report.restore_result.duration_seconds
                report.rpo_seconds = self.compute_rpo(s3_key)

        report.overall_passed = (
            report.verify_result.passed and (report.restore_result is None or report.restore_result.passed)
        )
        self._maybe_alert(report)
        return report

    def _maybe_alert(self, report: BackupTestReport):
        if not report.overall_passed and self.slack_webhook:
            try:
                import requests

                text = (
                    f":warning: SoroScan backup test *FAILED*\\n"
                    f"Bucket: `{report.bucket}`\\n"
                    f"Prefix: `{report.prefix}`\\n"
                    f"Verify: {report.verify_result.passed if report.verify_result else 'N/A'}\\n"
                    f"Restore: {report.restore_result.passed if report.restore_result else 'N/A'}"
                )
                requests.post(self.slack_webhook, json={"text": text}, timeout=10)
            except Exception:
                pass

    def print_runbook(self):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Manual Restore Runbook ==="))
        self.stdout.write("")
        self.stdout.write("Prerequisites:")
        self.stdout.write("  - AWS CLI configured with access to the backup bucket")
        self.stdout.write("  - pg_restore installed")
        self.stdout.write("  - Target database credentials (DATABASE_URL)")
        self.stdout.write("")
        self.stdout.write("Steps:")
        self.stdout.write("  1. Find the latest backup:")
        self.stdout.write(f"       aws s3 ls s3://{self.bucket}/{self.prefix}/ | sort | tail -n 5")
        self.stdout.write("")
        self.stdout.write("  2. Execute the restore script:")
        self.stdout.write(f"       bash scripts/backup/pg_restore.sh <S3_KEY>")
        self.stdout.write("")
        self.stdout.write("  3. Verify the database:")
        self.stdout.write("       psql $DATABASE_URL -c 'SELECT count(*) FROM ingest_trackedcontract;'")
        self.stdout.write("")
        self.stdout.write("  4. Re-run migrations if needed:")
        self.stdout.write("       cd django-backend && python manage.py migrate")
        self.stdout.write("")
        self.stdout.write("Rollback:")
        self.stdout.write("  - Restore from the previous backup (repeat step 2 with the prior S3_KEY).")
        self.stdout.write("")


def main():
    parser = argparse.ArgumentParser(description="SoroScan backup verification and restoration testing")
    parser.add_argument("mode", nargs="?", default="full-test", choices=["full-test", "verify-only", "restore-only"])
    parser.add_argument("--bucket", default=os.environ.get("S3_BUCKET", "soroscan-backups"))
    parser.add_argument("--prefix", default=os.environ.get("S3_PREFIX", "pg-backups"))
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--restore-db-url", default=None)
    parser.add_argument("--s3-key", default=None)
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument("--slack-webhook", default=os.environ.get("SLACK_WEBHOOK_URL"))
    parser.add_argument("--output", default=None, help="Write report JSON to this file")
    parser.add_argument("--runbook", action="store_true", help="Print manual restore runbook")
    args = parser.parse_args()

    if args.runbook:
        tester = BackupTester(
            db_url=args.db_url,
            bucket=args.bucket,
            prefix=args.prefix,
            region=args.region,
            slack_webhook=args.slack_webhook,
        )
        tester.print_runbook()
        return

    if not args.db_url:
        parser.error("--db-url or DATABASE_URL is required")

    tester = BackupTester(
        db_url=args.db_url,
        bucket=args.bucket,
        prefix=args.prefix,
        s3_key=args.s3_key,
        restore_db_url=args.restore_db_url,
        region=args.region,
        slack_webhook=args.slack_webhook,
    )

    if args.mode == "verify-only":
        s3_key = tester.latest_backup_key() if not args.s3_key else args.s3_key
        result = tester.verify_backup(s3_key)
        report = BackupTestReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            bucket=args.bucket,
            prefix=args.prefix,
            verify_result=result,
            overall_passed=result.passed,
        )
    elif args.mode == "restore-only":
        s3_key = args.s3_key or tester.latest_backup_key()
        result = tester.restore_backup(s3_key)
        report = BackupTestReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            bucket=args.bucket,
            prefix=args.prefix,
            restore_result=result,
            overall_passed=result.passed,
        )
    else:
        report = tester.run_full_test()

    summary = report.to_dict()
    json.dump(summary, sys.stdout, indent=2, default=str)
    sys.stdout.write("\\n")

    if report.overall_passed:
        print("Backup test PASSED", file=sys.stderr)
        sys.exit(0)
    else:
        print("Backup test FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
