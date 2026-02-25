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

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:3000")

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

MIDDLEWARE = [
    # PrometheusBeforeMiddleware must be first to capture all requests.
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "soroscan.middleware.ReverseProxyFixedIPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "soroscan.middleware.RequestIdMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # PrometheusAfterMiddleware must be last to record response codes/latencies.
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

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

# Cache (used for rate limiting)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
    }
}

# Rate limiting configuration (via environment variables)
RATE_LIMIT_ANON = env("RATE_LIMIT_ANON", default="60/minute")
RATE_LIMIT_USER = env("RATE_LIMIT_USER", default="300/minute")
RATE_LIMIT_INGEST = env("RATE_LIMIT_INGEST", default="10/minute")
RATE_LIMIT_GRAPHQL = env("RATE_LIMIT_GRAPHQL", default="100/minute")

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
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
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": RATE_LIMIT_ANON,
        "user": RATE_LIMIT_USER,
        "ingest": RATE_LIMIT_INGEST,
        "graphql": RATE_LIMIT_GRAPHQL,
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
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
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
    "soroscan.ingest.tasks.backfill_contract_events": {"queue": "backfill"},
}

# Stellar / Soroban Configuration
SOROBAN_RPC_URL = env("SOROBAN_RPC_URL", default="https://soroban-testnet.stellar.org")
STELLAR_NETWORK_PASSPHRASE = env(
    "STELLAR_NETWORK_PASSPHRASE",
    default="Test SDF Network ; September 2015",
)
SOROSCAN_CONTRACT_ID = env("SOROSCAN_CONTRACT_ID", default="")
INDEXER_SECRET_KEY = env("INDEXER_SECRET_KEY", default="")

# Prometheus
# Expose the /metrics endpoint without authentication.
# The URL is registered in urls.py via django_prometheus.urls.
PROMETHEUS_EXPORT_MIGRATIONS = False  # avoid migration noise in metrics

# Logging: set LOG_FORMAT=json for structured JSON logs (no PII in messages or extra).
LOG_FORMAT = env("LOG_FORMAT", default="")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
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