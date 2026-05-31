"""
Management command: seed_database

Populates the development database with realistic test data from fixture files.

Usage:
    python manage.py seed_database
    python manage.py seed_database --fixture=fixtures/custom.json
    python manage.py seed_database --scenario=minimal
    python manage.py seed_database --clear

Scenarios:
    default   - Full dataset (organizations, teams, users, contracts, events, webhooks)
    minimal   - Single user, one organization, three contracts, no events
    webhook   - Contracts with multiple webhook subscriptions and delivery logs

Clear mode removes all seeded data (users with is_staff=False and emails ending in @example.com).
"""
import json
import random
import string
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as django_tz

from soroscan.ingest.models import (
    AlertExecution,
    AlertRule,
    ContractEvent,
    ContractInvocation,
    ContractMetadata,
    ContractSource,
    ContractVerification,
    Organization,
    OrganizationMembership,
    Team,
    TeamMembership,
    TrackedContract,
    WebhookDeliveryLog,
    WebhookSubscription,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures"


def _random_hex(length=64):
    return "".join(random.choices("0123456789abcdef", k=length))


def _random_address():
    return "G" + "".join(random.choices(string.ascii_uppercase + string.digits, k=55))


def _now():
    return django_tz.now()


class Command(BaseCommand):
    help = "Seed the development database with realistic test data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            default=None,
            help="Path to JSON fixture file (default: fixtures/development.json)",
        )
        parser.add_argument(
            "--scenario",
            choices=["default", "minimal", "webhook"],
            default="default",
            help="Predefined scenario to seed (default: default)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove all seeded data before seeding",
        )

    def handle(self, *args, **options):
        fixture_path = options["fixture"]
        scenario = options["scenario"]
        clear = options["clear"]

        if fixture_path:
            data = self._load_fixture(Path(fixture_path))
        else:
            fixture_file = FIXTURES_DIR / "development.json"
            if fixture_file.exists():
                data = self._load_fixture(fixture_file)
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Fixture file not found at {fixture_file}, using built-in {scenario} scenario."
                    )
                )
                data = self._get_scenario(scenario)

        if clear:
            self._clear_seeded_data()

        self.stdout.write("Seeding database...")
        self._seed(data)
        self.stdout.write(self.style.SUCCESS("Database seeded successfully."))

    def _load_fixture(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in fixture file {path}: {exc}")

    def _get_scenario(self, scenario: str) -> dict:
        if scenario == "minimal":
            return {
                "organizations": [
                    {
                        "name": "Minimal Org",
                        "slug": "minimal-org",
                        "owner_email": "admin@example.com",
                        "settings": {},
                        "quota": 1000,
                    }
                ],
                "teams": [],
                "users": [
                    {
                        "email": "admin@example.com",
                        "password": "testpass123",
                        "first_name": "Admin",
                        "last_name": "User",
                    }
                ],
                "memberships": [
                    {"user_email": "admin@example.com", "organization_slug": "minimal-org", "role": "owner"}
                ],
                "team_memberships": [],
                "contracts": [
                    {
                        "contract_id": "CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAZ2KZ",
                        "name": "Token Contract",
                        "alias": "Simple Token",
                        "description": "Basic token contract",
                        "owner_email": "admin@example.com",
                        "organization_slug": "minimal-org",
                        "team_name": None,
                        "abi_schema": None,
                        "event_filter_type": "none",
                        "event_filter_list": [],
                    },
                    {
                        "contract_id": "CBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBZ2KZ",
                        "name": "Exchange",
                        "alias": "Mini DEX",
                        "description": "Simple exchange",
                        "owner_email": "admin@example.com",
                        "organization_slug": "minimal-org",
                        "team_name": None,
                        "abi_schema": {"events": [{"name": "swap", "params": ["in", "out", "trader"]}]},
                        "event_filter_type": "none",
                        "event_filter_list": [],
                    },
                    {
                        "contract_id": "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCZ2KZ",
                        "name": "Governor",
                        "alias": "Voting",
                        "description": "Governance contract",
                        "owner_email": "admin@example.com",
                        "organization_slug": "minimal-org",
                        "team_name": None,
                        "abi_schema": None,
                        "event_filter_type": "none",
                        "event_filter_list": [],
                    },
                ],
                "events": None,
                "webhooks": [],
                "webhook_delivery_logs": None,
                "alert_rules": [],
                "api_keys": [],
            }
        if scenario == "webhook":
            base = self._get_scenario("default")
            base["webhooks"] = [
                {
                    "contract_id": "CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAZ2KZ",
                    "event_type": "swap",
                    "target_url": "https://httpbin.org/post",
                    "timeout_seconds": 5,
                    "retry_backoff_strategy": "exponential",
                    "retry_backoff_seconds": 30,
                    "signature_algorithm": "sha256",
                },
                {
                    "contract_id": "CBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBZ2KZ",
                    "event_type": "",
                    "target_url": "https://httpbin.org/post",
                    "timeout_seconds": 10,
                    "retry_backoff_strategy": "fixed",
                    "retry_backoff_seconds": 60,
                    "signature_algorithm": "sha256",
                },
            ]
            base["webhook_delivery_logs"] = {"per_webhook": 8, "status_codes": [200, 200, 201, 500, 408, 200, 500, 200]}
            return base
        return self._get_scenario("default")

    def _clear_seeded_data(self):
        self.stdout.write("Clearing seeded data...")
        WebhookDeliveryLog.objects.filter(
            subscription__contract__owner__email__endswith="@example.com"
        ).delete()
        WebhookSubscription.objects.filter(
            contract__owner__email__endswith="@example.com"
        ).delete()
        AlertExecution.objects.filter(
            rule__contract__owner__email__endswith="@example.com"
        ).delete()
        AlertRule.objects.filter(
            contract__owner__email__endswith="@example.com"
        ).delete()
        ContractEvent.objects.filter(
            contract__owner__email__endswith="@example.com"
        ).delete()
        ContractInvocation.objects.filter(
            contract__owner__email__endswith="@example.com"
        ).delete()
        ContractMetadata.objects.filter(
            contract__owner__email__endswith="@example.com"
        ).delete()
        ContractSource.objects.filter(
            contract__owner__email__endswith="@example.com"
        ).delete()
        ContractVerification.objects.filter(
            contract__owner__email__endswith="@example.com"
        ).delete()
        TrackedContract.objects.filter(
            owner__email__endswith="@example.com"
        ).delete()
        TeamMembership.objects.filter(
            user__email__endswith="@example.com"
        ).delete()
        Team.objects.filter(
            created_by__email__endswith="@example.com"
        ).delete()
        OrganizationMembership.objects.filter(
            user__email__endswith="@example.com"
        ).delete()
        Organization.objects.filter(
            owner__email__endswith="@example.com"
        ).delete()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.filter(email__endswith="@example.com", is_staff=False).delete()
        self.stdout.write(self.style.SUCCESS("Cleared seeded data."))

    def _seed(self, data: dict):
        users = self._seed_users(data.get("users", []))
        orgs = self._seed_organizations(data.get("organizations", []), users)
        teams = self._seed_teams(data.get("teams", []), orgs, users)
        self._seed_memberships(data.get("memberships", []), orgs, users)
        self._seed_team_memberships(data.get("team_memberships", []), teams, users)
        contracts = self._seed_contracts(data.get("contracts", []), orgs, teams, users)
        self._seed_events(data.get("events"), contracts)
        self._seed_webhooks(data.get("webhooks", []), contracts)
        self._seed_webhook_delivery_logs(data.get("webhook_delivery_logs"), contracts)
        self._seed_alert_rules(data.get("alert_rules", []), contracts, users)

    def _seed_users(self, users_data: list) -> dict:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        users = {}
        for ud in users_data:
            email = ud["email"]
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": ud.get("first_name", ""),
                    "last_name": ud.get("last_name", ""),
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            if created and ud.get("password"):
                user.set_password(ud["password"])
                user.save()
            users[email] = user
        return users

    def _seed_organizations(self, orgs_data: list, users: dict) -> dict:
        orgs = {}
        for od in orgs_data:
            owner_email = od["owner_email"]
            owner = users.get(owner_email)
            if not owner:
                continue
            org, created = Organization.objects.get_or_create(
                slug=od["slug"],
                defaults={
                    "name": od["name"],
                    "owner": owner,
                    "settings": od.get("settings", {}),
                    "quota": od.get("quota", 0),
                },
            )
            orgs[od["slug"]] = org
        return orgs

    def _seed_teams(self, teams_data: list, orgs: dict, users: dict) -> dict:
        teams = {}
        for td in teams_data:
            org_slug = td.get("organization_slug")
            org = orgs.get(org_slug)
            if not org:
                continue
            creator_email = td.get("created_by_email")
            creator = users.get(creator_email) if creator_email else None
            team, created = Team.objects.get_or_create(
                slug=f"{org.slug}-{td['name'].lower().replace(' ', '-')}",
                defaults={
                    "name": td["name"],
                    "organization": org,
                    "created_by": creator,
                },
            )
            teams[td["name"]] = team
        return teams

    def _seed_memberships(self, memberships_data: list, orgs: dict, users: dict):
        for md in memberships_data:
            user = users.get(md["user_email"])
            org = orgs.get(md["organization_slug"])
            if not user or not org:
                continue
            OrganizationMembership.objects.get_or_create(
                organization=org,
                user=user,
                defaults={"role": md.get("role", "member")},
            )

    def _seed_team_memberships(self, memberships_data: list, teams: dict, users: dict):
        for md in memberships_data:
            user = users.get(md["user_email"])
            team = teams.get(md["team_name"])
            if not user or not team:
                continue
            TeamMembership.objects.get_or_create(
                team=team,
                user=user,
                defaults={"role": md.get("role", "member")},
            )

    def _seed_contracts(self, contracts_data: list, orgs: dict, teams: dict, users: dict) -> dict:
        contracts = {}
        for cd in contracts_data:
            owner = users.get(cd.get("owner_email"))
            if not owner:
                continue
            org = orgs.get(cd.get("organization_slug")) if cd.get("organization_slug") else None
            team = teams.get(cd.get("team_name")) if cd.get("team_name") else None
            contract, created = TrackedContract.objects.get_or_create(
                contract_id=cd["contract_id"],
                defaults={
                    "name": cd["name"],
                    "alias": cd.get("alias", ""),
                    "description": cd.get("description", ""),
                    "owner": owner,
                    "organization": org,
                    "team": team,
                    "abi_schema": cd.get("abi_schema"),
                    "event_filter_type": cd.get("event_filter_type", "none"),
                    "event_filter_list": cd.get("event_filter_list", []),
                    "is_active": True,
                    "deprecation_status": "active",
                },
            )
            contracts[cd["contract_id"]] = contract
        return contracts

    def _seed_events(self, events_config, contracts: dict):
        if not events_config:
            return
        per_contract = events_config.get("per_contract", 20)
        contract_ids = events_config.get("contracts", list(contracts.keys()))
        event_types = events_config.get("event_types", ["event_default"])
        days_back = events_config.get("days_back", 14)

        for contract_id in contract_ids:
            contract = contracts.get(contract_id)
            if not contract:
                continue
            base_time = _now() - timedelta(days=days_back)
            for i in range(per_contract):
                event_type = random.choice(event_types)
                ledger = 100000 + i + random.randint(0, 5000)
                timestamp = base_time + timedelta(
                    minutes=random.randint(0, days_back * 24 * 60)
                )
                payload = {
                    "amount": random.randint(1, 1000000),
                    "trader": _random_address(),
                    "token_id": random.randint(1, 1000),
                }
                try:
                    event = ContractEvent(
                        contract=contract,
                        event_type=event_type,
                        schema_version=1,
                        validation_status="passed",
                        payload=payload,
                        ledger=ledger,
                        event_index=i % 5,
                        timestamp=timestamp,
                        tx_hash=_random_hex(64),
                        raw_xdr="",
                        decoding_status="no_abi",
                        signature_status="missing",
                    )
                    event.save()
                except Exception:
                    pass

    def _seed_webhooks(self, webhooks_data: list, contracts: dict):
        for wd in webhooks_data:
            contract = contracts.get(wd["contract_id"])
            if not contract:
                continue
            try:
                WebhookSubscription.objects.create(
                    contract=contract,
                    event_type=wd.get("event_type", ""),
                    target_url=wd["target_url"],
                    timeout_seconds=wd.get("timeout_seconds", 10),
                    retry_backoff_strategy=wd.get("retry_backoff_strategy", "exponential"),
                    retry_backoff_seconds=wd.get("retry_backoff_seconds", 60),
                    signature_algorithm=wd.get("signature_algorithm", "sha256"),
                )
            except Exception:
                pass

    def _seed_webhook_delivery_logs(self, logs_config, contracts: dict):
        if not logs_config:
            return
        per_webhook = logs_config.get("per_webhook", 5)
        status_codes = logs_config.get("status_codes", [200])
        webhooks = list(WebhookSubscription.objects.filter(contract__in=contracts.values()))
        for webhook in webhooks:
            events = list(
                ContractEvent.objects.filter(contract=webhook.contract).order_by("?")[:per_webhook]
            )
            for idx, event in enumerate(events, start=1):
                status_code = status_codes[idx % len(status_codes)]
                success = 200 <= status_code < 300
                try:
                    WebhookDeliveryLog.objects.create(
                        subscription=webhook,
                        event=event,
                        attempt_number=idx,
                        status_code=status_code,
                        success=success,
                        error="" if success else f"HTTP {status_code}",
                        payload_bytes=random.randint(200, 2000),
                    )
                except Exception:
                    pass

    def _seed_alert_rules(self, rules_data: list, contracts: dict, users: dict):
        for rd in rules_data:
            contract = contracts.get(rd["contract_id"])
            if not contract:
                continue
            try:
                rule = AlertRule.objects.create(
                    contract=contract,
                    name=rd["name"],
                    condition=rd.get("condition", {}),
                    channels=rd.get("channels", []),
                    action_type=rd.get("action_type", "webhook"),
                    action_target=rd.get("action_target", ""),
                )
                events = list(ContractEvent.objects.filter(contract=contract)[:2])
                for event in events:
                    AlertExecution.objects.create(
                        rule=rule,
                        event=event,
                        channel=rd.get("action_type", "webhook"),
                        status=random.choice(["sent", "sent", "failed"]),
                        response="OK" if random.random() > 0.3 else "Timeout",
                    )
            except Exception:
                pass
