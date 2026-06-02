"""
Django settings for SoroScan project.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_software_version() -> str:
    """
    Resolve the platform version from VERSION.md, with a safe fallback.
    """
    version_file_candidates = [
        BASE_DIR / "VERSION.md",
        BASE_DIR.parent / "VERSION.md",
    ]
    for candidate in version_file_candidates:
        try:
            if candidate.exists():
                content = candidate.read_text(encoding="utf-8").strip()
                if content:
                    return content
        except OSError:
            continue
    return "1.0.0"

# Environment variables
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

REQUIRED_ENV_VARS = [
    'SECRET_KEY',
    'DATABASE_URL',
    'REDIS_URL',
    'SOROBAN_RPC_URL',
    'STELLAR_NETWORK_PASSPHRASE',
    'SOROSCAN_CONTRACT_ID',
]

_running_tests = 'test' in sys.argv or os.environ.get('DJANGO_SETTINGS_MODULE', '').endswith('_test')
if not _running_tests:
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            raise ImproperlyConfigured(f"Required environment variable '{var}' is not set.")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-this-in-production")

# Warn on startup if SECRET_KEY is weak or a known default
_KNOWN_WEAK_KEYS = {
    "django-insecure-change-this-in-production",
    "secret",
    "changeme",
    "insecure",
}
if len(SECRET_KEY) < 50 or SECRET_KEY in _KNOWN_WEAK_KEYS:
    import logging as _logging
    _logging.getLogger("soroscan.security").warning(
        "SECRET_KEY is too short or matches a known default. "
        "Set a strong, unique SECRET_KEY before deploying to production."
    )

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:3000")
SOFTWARE_VERSION = env("SOFTWARE_VERSION", default=_load_software_version())

# Application definition
INSTALLED_APPS = [
    "daphne",
    "django_prometheus",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Third-party
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "django_filters",
    "strawberry.django",
    "channels",
    # Local apps
    "soroscan.ingest",
]

ENABLE_SILK = env.bool("ENABLE_SILK", default=False)

MIDDLEWARE = [
    # PrometheusBeforeMiddleware must be first to capture all requests.
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "soroscan.middleware.RequestBodySizeMiddleware",
    "soroscan.middleware.MaintenanceModeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "soroscan.middleware.ReverseProxyFixedIPMiddleware",
    "soroscan.middleware.ClientIPLoggingMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "soroscan.middleware.RequestIdMiddleware",
    "soroscan.middleware.PlatformVersionMiddleware",
    "soroscan.perf_logger.SlowQueryLoggerMiddleware",
    "soroscan.middleware.SlowQueryMiddleware",
    "soroscan.middleware.ApiDeprecationMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # PrometheusAfterMiddleware must be last to record response codes/latencies.
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

if ENABLE_SILK:
    MIDDLEWARE.insert(0, "silk.middleware.SilkyMiddleware")
    if "silk" not in INSTALLED_APPS:
        INSTALLED_APPS.append("silk")

ROOT_URLCONF = "soroscan.urls"

ASGI_APPLICATION = "soroscan.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "soroscan.wsgi.application"

# Database
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    ),
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache (used for rate limiting and expensive query results — issue #131)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
    }
}
# TTL for REST/GraphQL search, stats, and timeline responses (seconds)
QUERY_CACHE_TTL_SECONDS = env.int("QUERY_CACHE_TTL_SECONDS", default=60)

# Rate limiting configuration (via environment variables)
# To add a new endpoint rate limit:
# 1. Define a new environment variable here (e.g. ENDPOINT_RATE_LIMIT_MYFEATURE).
# 2. Add it to the DEFAULT_THROTTLE_RATES dictionary below with a custom scope name.
# 3. Apply the `DynamicEndpointThrottle` to your ViewSet and map the action in `action_throttle_scopes`,
#    or set `throttle_scope = "my_scope"` on an APIView.
RATE_LIMIT_ANON = env("RATE_LIMIT_ANON", default="60/minute")
RATE_LIMIT_USER = env("RATE_LIMIT_USER", default="300/minute")
RATE_LIMIT_INGEST = env("RATE_LIMIT_INGEST", default="10/minute")
RATE_LIMIT_GRAPHQL = env("RATE_LIMIT_GRAPHQL", default="60/minute")
ENDPOINT_RATE_LIMIT_SEARCH = env("ENDPOINT_RATE_LIMIT_SEARCH", default="30/minute")
ENDPOINT_RATE_LIMIT_STATS = env("ENDPOINT_RATE_LIMIT_STATS", default="100/minute")

# REST Framework
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "soroscan.exceptions.custom_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "soroscan.authentication.APIKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "soroscan.throttles.DynamicEndpointThrottle",
        "soroscan.throttles.APIKeyThrottle",
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": RATE_LIMIT_ANON,
        "user": RATE_LIMIT_USER,
        "ingest": RATE_LIMIT_INGEST,
        "graphql": RATE_LIMIT_GRAPHQL,
        "events_search": ENDPOINT_RATE_LIMIT_SEARCH,
        "contract_stats": ENDPOINT_RATE_LIMIT_STATS,
    },
}

# Spectacular Settings
SPECTACULAR_SETTINGS = {
    "TITLE": "SoroScan API",
    "DESCRIPTION": "REST API documentation for SoroScan, a Stellar Soroban smart contract indexer.",
    "VERSION": "1.0.0",
}

# Simple JWT Settings
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# CORS
origins_str = env("ALLOWED_ORIGINS", default="")
CORS_ALLOWED_ORIGINS = [o.strip() for o in origins_str.split(",") if o.strip()] if origins_str else []
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True  # Required for Apollo Client with credentials: 'include'

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("REDIS_URL", default="redis://localhost:6379/0")],
        },
    },
}

# Celery
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ROUTES = {
    "ingest.tasks.ingest_latest_events": {"queue": "high_priority"},
    "ingest.tasks.dispatch_webhook": {"queue": "default"},
    "ingest.tasks.aggregate_event_statistics": {"queue": "low_priority"},
    "soroscan.ingest.tasks.backfill_contract_events": {"queue": "backfill"},
    "soroscan.ingest.tasks.evaluate_remediation_rules": {"queue": "default"},
}

# Celery Beat periodic task schedule
CELERY_BEAT_SCHEDULE = {
    "cleanup-webhook-delivery-logs": {
        "task": "soroscan.ingest.tasks.cleanup_webhook_delivery_logs",
        "schedule": 86400,  # daily
    },
    "cleanup-old-dedup-logs": {
        "task": "soroscan.ingest.tasks.cleanup_old_dedup_logs",
        "schedule": 86400,  # daily
    },
    "cleanup-silk-data": {
        "task": "soroscan.ingest.tasks.cleanup_silk_data",
        "schedule": 604800,  # weekly
    },
    "archive-old-events": {
        "task": "soroscan.ingest.tasks.archive_old_events",
        "schedule": 86400,  # daily
    },
    "evaluate-remediation-rules": {
        "task": "soroscan.ingest.tasks.evaluate_remediation_rules",
        "schedule": 300,  # every 5 minutes
    },
    "aggregate-event-statistics": {
        "task": "ingest.tasks.aggregate_event_statistics",
        "schedule": 3600,  # hourly
    },
    "aggregate-organization-costs": {
        "task": "ingest.tasks.aggregate_organization_costs",
        "schedule": 3600,  # hourly
    },
    "reconcile-event-completeness": {
        "task": "ingest.tasks.reconcile_event_completeness",
        "schedule": 300,  # every 5 minutes
    },
    "recompute-call-graph": {
        "task": "ingest.tasks.recompute_call_graph",
        "schedule": 3600,  # hourly
    },
    "warm-event-count-cache": {
        "task": "ingest.tasks.warm_event_count_cache",
        "schedule": 300,  # every 5 minutes
    },
}

# Data Retention Configuration
# Number of days to retain deduplication logs before cleanup
DEDUP_LOG_RETENTION_DAYS = env("DEDUP_LOG_RETENTION_DAYS", default=90, cast=int)
# Number of days to retain contract events before pruning
EVENT_RETENTION_DAYS = env("EVENT_RETENTION_DAYS", default=30, cast=int)

# Alert deduplication window
ALERT_DEDUP_WINDOW_SECONDS = env.int("ALERT_DEDUP_WINDOW_SECONDS", default=300)

# Webhook delivery + escalation configuration
WEBHOOK_ESCALATION_TIMEOUT_SECONDS = env.int(
    "WEBHOOK_ESCALATION_TIMEOUT_SECONDS", default=10
)
WEBHOOK_ESCALATION_DEDUP_SECONDS = env.int(
    "WEBHOOK_ESCALATION_DEDUP_SECONDS", default=300
)
WEBHOOK_ESCALATION_SLACK_TARGET = env(
    "WEBHOOK_ESCALATION_SLACK_TARGET", default=""
)
WEBHOOK_ESCALATION_SMS_TARGET = env(
    "WEBHOOK_ESCALATION_SMS_TARGET", default=""
)
WEBHOOK_ESCALATION_PAGERDUTY_TARGET = env(
    "WEBHOOK_ESCALATION_PAGERDUTY_TARGET", default=""
)

# Webhook deduplication window
WEBHOOK_DEDUP_WINDOW_SECONDS = env.int("WEBHOOK_DEDUP_WINDOW_SECONDS", default=300)

# Dependency change alert deduplication
DOWNSTREAM_ALERT_DEDUP_SECONDS = env.int("DOWNSTREAM_ALERT_DEDUP_SECONDS", default=3600)

# Cost model defaults (USD)
COST_RPC_PER_CALL_USD = env("COST_RPC_PER_CALL_USD", default="0.00001")
COST_STORAGE_PER_GB_USD = env("COST_STORAGE_PER_GB_USD", default="0.10")
COST_COMPUTE_PER_UNIT_USD = env("COST_COMPUTE_PER_UNIT_USD", default="0.00002")

# Stellar / Soroban Configuration
SOROBAN_RPC_URL = env("SOROBAN_RPC_URL", default="https://soroban-testnet.stellar.org")
STELLAR_NETWORK_PASSPHRASE = env(
    "STELLAR_NETWORK_PASSPHRASE",
    default="Test SDF Network ; September 2015",
)
SOROSCAN_CONTRACT_ID = env("SOROSCAN_CONTRACT_ID", default="")
INDEXER_SECRET_KEY = env("INDEXER_SECRET_KEY", default="")

# Available Soroban networks exposed via GET /api/ingest/networks/.
# Override individual RPC URLs via the corresponding env vars if needed.
SOROBAN_NETWORKS = [
    {
        "id": "testnet",
        "name": "Testnet",
        "rpc_url": env("TESTNET_RPC_URL", default="https://soroban-testnet.stellar.org"),
        "network_passphrase": "Test SDF Network ; September 2015",
    },
    {
        "id": "mainnet",
        "name": "Mainnet",
        "rpc_url": env("MAINNET_RPC_URL", default="https://mainnet.stellar.validationcloud.io/v1/public"),
        "network_passphrase": "Public Global Stellar Network ; September 2015",
    },
    {
        "id": "futurenet",
        "name": "Futurenet",
        "rpc_url": env("FUTURENET_RPC_URL", default="https://soroban-futurenet.stellar.org"),
        "network_passphrase": "Test SDF Future Network ; October 2022",
    },
]

# ---------------------------------------------------------------------------
# GraphQL Introspection (security: disable in production)
# ---------------------------------------------------------------------------
# Set GRAPHQL_INTROSPECTION_ENABLED=True to allow introspection queries.
# Defaults to True in DEBUG mode, False otherwise.
GRAPHQL_INTROSPECTION_ENABLED = env.bool(
    "GRAPHQL_INTROSPECTION_ENABLED",
    default=DEBUG,
)

# Prometheus
# Expose the /metrics endpoint without authentication.
# The URL is registered in urls.py via django_prometheus.urls.
PROMETHEUS_EXPORT_MIGRATIONS = False  # avoid migration noise in metrics
LOG_FORMAT = env("LOG_FORMAT", default="")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(name)s %(levelname)s [req:%(request_id)s] %(message)s",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(request_id)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "default",
            "filters": ["log_context"],
        },
    },
    "filters": {
        "log_context": {
            "()": "soroscan.log_context.LogContextFilter",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# ---------------------------------------------------------------------------
# Slow-query logging (Issue: perf monitoring)
# ---------------------------------------------------------------------------
LOGGING_SLOW_QUERIES_THRESHOLD_MS = env.int("SLOW_QUERY_THRESHOLD_MS", default=100)
DATABASE_SLOW_QUERY_THRESHOLD = env.float("DATABASE_SLOW_QUERY_THRESHOLD", default=1.0)

# Ensure log directories exist before configuring handlers
_LOG_DIR = BASE_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "logs" / "profiler").mkdir(parents=True, exist_ok=True)

# Extend LOGGING to capture slow queries in a separate rotating file
LOGGING.setdefault("loggers", {})
LOGGING["handlers"]["slow_queries"] = {
    "level": "WARNING",
    "class": "logging.handlers.TimedRotatingFileHandler",
    "filename": str(BASE_DIR / "logs" / "slow_queries.log"),
    "when": "midnight",
    "backupCount": 7,
    "formatter": "default",
}
LOGGING["loggers"]["soroscan.slow_queries"] = {
    "handlers": ["slow_queries", "console"],
    "level": "WARNING",
    "propagate": False,
}
LOGGING["loggers"]["soroscan.migrate"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}
LOGGING["loggers"]["django.performance.database"] = {
    "handlers": ["console"],
    "level": "WARNING",
    "propagate": False,
}

# ---------------------------------------------------------------------------
# Security audit logger — admin login success / failure events
# ---------------------------------------------------------------------------
LOGGING["handlers"]["security_audit"] = {
    "level": "INFO",
    "class": "logging.handlers.TimedRotatingFileHandler",
    "filename": str(BASE_DIR / "logs" / "security_audit.log"),
    "when": "midnight",
    "backupCount": 30,
    "formatter": "default",
}
LOGGING["loggers"]["soroscan.security_audit"] = {
    "handlers": ["security_audit", "console"],
    "level": "INFO",
    "propagate": False,
}

# ---------------------------------------------------------------------------
# IP access logger — client IP, method, and path for every API request
# ---------------------------------------------------------------------------
LOGGING["loggers"]["soroscan.ip_access"] = {
    "handlers": ["console"],
    "level": "INFO",
    "propagate": False,
}

# ---------------------------------------------------------------------------
# Django Silk profiler (Issue: perf monitoring) — enabled via ENABLE_SILK=true
# ---------------------------------------------------------------------------
SILK_PROFILER_LOG_DIR = env("SILK_PROFILER_LOG_DIR", default=str(BASE_DIR / "logs" / "profiler"))
SILK_META_MAX_RESPONSE_SIZE = 4096  # bytes, keep overhead minimal
SILK_MAX_RECORDED_REQUESTS = 1000   # ring-buffer per process
SILK_AUTHENTICATION_REQUIRED = not DEBUG
SILK_AUTHORISATION_REQUIRED = not DEBUG

# ---------------------------------------------------------------------------
# Email backend (Issue: event-driven alerts)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@soroscan.io")

# Alert settings
SLACK_ALERT_TIMEOUT_SECONDS = env.int("SLACK_ALERT_TIMEOUT_SECONDS", default=10)

# ---------------------------------------------------------------------------
# Event Streaming Configuration (Issue: Downstream Integration)
# ---------------------------------------------------------------------------
EVENT_STREAMING = {
    "enabled": env.bool("EVENT_STREAMING_ENABLED", default=False),
    "backend": env("EVENT_STREAMING_BACKEND", default="kafka"),  # 'kafka', 'pubsub', or 'sqs'
    "kafka": {
        "bootstrap_servers": env.list("KAFKA_BOOTSTRAP_SERVERS", default=["localhost:9092"]),
        "topic": env("KAFKA_TOPIC", default="soroscan.events"),
        "schema_registry_url": env("KAFKA_SCHEMA_REGISTRY_URL", default=""),
    },
    "pubsub": {
        "project_id": env("PUBSUB_PROJECT_ID", default=""),
        "topic": env("PUBSUB_TOPIC", default="soroscan.events"),
    },
    "sqs": {
        "queue_url": env("SQS_QUEUE_URL", default=""),
    },
}

# ---------------------------------------------------------------------------
# S3 / Archive storage configuration
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
# Set AWS_S3_ENDPOINT_URL for S3-compatible stores (MinIO, Localstack, etc.)
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")

# Sentry (optional): init only when SENTRY_DSN is set. Celery task failures reported via CeleryIntegration.
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
        send_default_pii=False,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
    )

# --- Request Size Limit (Issue #338) ---
# Default to 10MB (10 * 1024 * 1024 bytes)
MAX_REQUEST_BODY_SIZE = env.int("MAX_REQUEST_BODY_SIZE", default=10485760)

# --- API Deprecation (Issue #336) ---
DEPRECATED_ENDPOINTS = {
    "/api/audit-trail/": {
        "sunset": "2026-12-31",
        "replacement": "/graphql/"
    }
}

if 'test' in sys.argv:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }