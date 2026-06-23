import sys
from django.core.management.base import BaseCommand
from django.db import connections, DEFAULT_DB_ALIAS
from django.db.migrations.loader import MigrationLoader

class Command(BaseCommand):
    help = "Outputs a clear list of applied and pending migrations with native multi-database support."

    def add_arguments(self, parser):
        parser.add_argument(
            '--database',
            default=DEFAULT_DB_ALIAS,
            help='Nominates a database to check migration status for. Defaults to the "default" database.',
        )

    def handle(self, *args, **options):
        db = options['database']
        
        try:
            connection = connections[db]
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Database connection '{db}' failed: {e}"))
            sys.exit(1)

        self.stdout.write(f"Checking migration status for database: {db}")

        # Loading migrations might raise exceptions if DB connection fails here
        try:
            loader = MigrationLoader(connection)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to load migrations: {e}"))
            sys.exit(1)
        
        disk_migrations = set(loader.disk_migrations.keys())
        # applied_migrations is a dict keyed by (app_label, name); convert to a set of keys
        applied_migrations = set(loader.applied_migrations.keys())
        
        apps = sorted(set(app_label for app_label, _ in disk_migrations))

        for app in apps:
            self.stdout.write(self.style.SUCCESS(f"\nApp: {app}"))
            
            app_disk_migrations = sorted([m for m in disk_migrations if m[0] == app])
            
            for migration in app_disk_migrations:
                is_applied = migration in applied_migrations
                migration_name = migration[1]
                if is_applied:
                    self.stdout.write(self.style.SUCCESS(f"  [X] {migration_name} (Applied)"))
                else:
                    self.stdout.write(self.style.WARNING(f"  [ ] {migration_name} (Pending)"))
        
        if not apps:
            self.stdout.write("No migrations found.")
        
        ghost_migrations = applied_migrations - disk_migrations
        if ghost_migrations:
            self.stdout.write(self.style.ERROR("\nGhost Migrations (applied but not on disk):"))
            for ghost in sorted(ghost_migrations):
                self.stdout.write(self.style.ERROR(f"  [?] {ghost[0]}.{ghost[1]}"))

        self.stdout.write(self.style.SUCCESS("\nMigration status check complete."))
