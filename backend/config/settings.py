import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Configure DJANGO_SECRET_KEY; no embedded credentials are provided.")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend").split(",")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "axes",
    "apps.organizations",
    "apps.accounts",
    "apps.commitments",
    "apps.audit",
    "apps.notifications",
    "apps.customfields",
    "apps.reports",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
if os.getenv("DATABASE_ENGINE") == "sqlite":
    if not DEBUG:
        raise ImproperlyConfigured("SQLite is restricted to local development/tests.")
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "agenda"),
            "USER": os.getenv("POSTGRES_USER", "agenda"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "db"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation." + name}
    for name in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = os.getenv("TIME_ZONE", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Agenda Regulatória",
    "COMPONENT_SPLIT_REQUEST": True,
    "VERSION": "1.0.0",
    "ENUM_NAME_OVERRIDES": {
        "OccurrenceStatusEnum": "apps.commitments.models.CommitmentOccurrence.Status",
        "DeliveryStatusEnum": "apps.notifications.models.NotificationDelivery.Status",
    },
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True
CSRF_TRUSTED_ORIGINS = os.getenv(
    "CSRF_TRUSTED_ORIGINS", "http://localhost:4200,http://localhost:8080"
).split(",")
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
AXES_LOCKOUT_PARAMETERS = ["ip_address"]
AXES_RESET_ON_SUCCESS = True
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("SMTP_HOST", "mailpit")
EMAIL_PORT = int(os.getenv("SMTP_PORT", "1025"))
EMAIL_HOST_USER = os.getenv("SMTP_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("SMTP_TLS", "false").lower() == "true"

SPECTACULAR_SETTINGS.update(
    {"SWAGGER_UI_DIST": "SIDECAR", "SWAGGER_UI_FAVICON_HREF": "SIDECAR", "REDOC_DIST": "SIDECAR"}
)


# SMTP acceptance is recorded; delivery to an inbox is never inferred.
DEFAULT_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "Agenda Regulatória <agenda@agenda.invalid>")
EMAIL_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "15"))
EMAIL_USE_SSL = os.getenv("SMTP_SSL", "false").lower() == "true"
NOTIFICATION_BASE_URL = os.getenv("NOTIFICATION_BASE_URL", "http://localhost:8080").rstrip("/")
NOTIFICATION_MAX_ATTEMPTS = 5
NOTIFICATION_RETRY_BASE_SECONDS = 60
NOTIFICATION_LEASE_SECONDS = 180
NOTIFICATION_ALERT_CATCHUP_DAYS = 7
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_TASK_PUBLISH_RETRY = False
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 300,
    "socket_connect_timeout": 3,
    "socket_timeout": 3,
}
CELERY_BEAT_SCHEDULE = {
    "dispatch-durable-outbox": {"task": "apps.notifications.tasks.dispatch", "schedule": 30.0},
    "scan-deadlines": {"task": "apps.notifications.tasks.deadlines", "schedule": 300.0},
}

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured("Configure somente SMTP_TLS ou SMTP_SSL, não ambos.")

# Only enable after the gateway overwrites this header and backend is isolated.
TRUST_PROXY_HTTPS = os.getenv("TRUST_PROXY_HTTPS", "false").lower() == "true"
if TRUST_PROXY_HTTPS:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_PRELOAD = False
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
DATA_UPLOAD_MAX_MEMORY_SIZE = 2621440
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
if not DEBUG:
    if len(SECRET_KEY) < 50:
        raise ImproperlyConfigured("Production requires a secret key of at least 50 characters.")
    if "*" in ALLOWED_HOSTS or not os.getenv("DJANGO_ALLOWED_HOSTS"):
        raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS.")
    if not os.getenv("CSRF_TRUSTED_ORIGINS") or any(
        not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS
    ):
        raise ImproperlyConfigured("Production requires explicit HTTPS CSRF_TRUSTED_ORIGINS.")

AXES_CLIENT_IP_CALLABLE = "apps.accounts.proxy.client_ip"

if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    DATABASES["default"]["OPTIONS"] = {"sslmode": os.getenv("POSTGRES_SSLMODE", "prefer")}
    if os.getenv("POSTGRES_SSLROOTCERT"):
        DATABASES["default"]["OPTIONS"]["sslrootcert"] = os.environ["POSTGRES_SSLROOTCERT"]

# Bounded uploads, private storage, corporate scanner integration.
EVIDENCE_MAX_FILE_BYTES = int(os.getenv("EVIDENCE_MAX_FILE_BYTES", str(2 * 1024 * 1024)))
EVIDENCE_MAX_FILES = int(os.getenv("EVIDENCE_MAX_FILES", "3"))
if not 1 <= EVIDENCE_MAX_FILE_BYTES <= 10 * 1024 * 1024 or not 1 <= EVIDENCE_MAX_FILES <= 5:
    raise ImproperlyConfigured("Invalid evidence upload limits")
EVIDENCE_STORAGE_BACKEND = os.getenv(
    "EVIDENCE_STORAGE_BACKEND", "apps.commitments.evidence_storage.DatabaseEvidenceStorage"
)
EVIDENCE_SCANNER_HOST = os.getenv("EVIDENCE_SCANNER_HOST", "")
EVIDENCE_SCANNER_PORT = int(os.getenv("EVIDENCE_SCANNER_PORT", "3310"))
EVIDENCE_SCANNER_TIMEOUT = 15
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 5

EVIDENCE_MAX_OCCURRENCE_BYTES = int(
    os.getenv("EVIDENCE_MAX_OCCURRENCE_BYTES", str(50 * 1024 * 1024))
)
EVIDENCE_MAX_OCCURRENCE_FILES = int(os.getenv("EVIDENCE_MAX_OCCURRENCE_FILES", "30"))
if (
    not 1 <= EVIDENCE_MAX_OCCURRENCE_BYTES <= 500 * 1024 * 1024
    or not 1 <= EVIDENCE_MAX_OCCURRENCE_FILES <= 100
):
    raise ImproperlyConfigured("Invalid evidence occurrence limits")

FILE_UPLOAD_HANDLERS = [
    "apps.commitments.upload_limits.EvidenceUploadLimits",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
