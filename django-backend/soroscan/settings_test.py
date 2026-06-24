"""
Test settings for SoroScan project.
"""
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-test-key-for-testing-only"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["*"]
FRONTEND_BASE_URL = "http://localhost:3000"
SOFTWARE_VERSION = "1.0.0-test"

# Application definition
INSTALLED_APPS = [
    "django_prometheus",  # must be before django.contrib apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "channels",
    # Local apps
    "soroscan.ingest",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "soroscan.middleware.RequestBodySizeMiddleware",
    "soroscan.middleware.MaintenanceModeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "soroscan.middleware.RequestIdMiddleware",
    "soroscan.middleware.PlatformVersionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "soroscan.middleware.ApiDeprecationMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "soroscan.urls_test"  # safe mirror — excludes strawberry/GDAL import

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
ASGI_APPLICATION = "soroscan.asgi.application"

# Channels configuration for testing
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Database - use in-memory SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = []

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

# In-memory cache for tests (query result caching — issue #131)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "soroscan-test",
    }
}
QUERY_CACHE_TTL_SECONDS = 60

# REST Framework
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "soroscan.exceptions.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/hour",
        "user": "10000/hour",
        "ingest": "100/hour",
        "graphql": "500/hour",
    },
}

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = []

# Celery - Test settings (synchronous execution)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Stellar / Soroban Configuration
SOROBAN_RPC_URL = "https://soroban-testnet.stellar.org"
STELLAR_NETWORK_PASSPHRASE = "Test SDF Network ; September 2015"
SOROSCAN_CONTRACT_ID = "C" + "A" * 55
INDEXER_SECRET_KEY = ""

# Event Streaming Configuration (Disabled by default for tests)
EVENT_STREAMING = {
    "enabled": False,
    "backend": "kafka",
    "kafka": {
        "bootstrap_servers": ["localhost:9092"],
        "topic": "soroscan.events",
        "schema_registry_url": "",
    },
    "pubsub": {
        "project_id": "test-project",
        "topic": "soroscan.events",
    },
    "sqs": {
        "queue_url": "",
    },
}

# GraphQL Introspection — enabled in tests/dev
GRAPHQL_INTROSPECTION_ENABLED = True
GRAPHQL_MAX_COMPLEXITY = 1000

# Fixed test seed for deterministic webhook signature tests.
WEBHOOK_ED25519_SIGNING_SEED = (
    "0000000000000000000000000000000000000000000000000000000000000001"
)

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "soroscan.migrate": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}

MAX_REQUEST_BODY_SIZE = 10485760
DEPRECATED_ENDPOINTS = {}