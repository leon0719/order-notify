"""Django base settings."""

import os
from functools import lru_cache
from pathlib import Path

import dj_database_url
from pydantic_settings import BaseSettings, SettingsConfigDict

_env = os.getenv("ENV", "local")
_env_file = f".env.{_env}"


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Required
    SECRET_KEY: str
    DATABASE_URL: str
    REDIS_URL: str
    RABBITMQ_URL: str

    # Optional
    DEBUG: bool = False
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Slack (chat.postMessage API)
    SLACK_BOT_TOKEN: str = ""
    SLACK_CHANNEL: str = ""
    SLACK_ENABLED: bool = False

    def _parse_comma_separated(self, value: str) -> list[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    def get_allowed_hosts(self) -> list[str]:
        return self._parse_comma_separated(self.ALLOWED_HOSTS)

    def get_cors_allowed_origins(self) -> list[str]:
        return self._parse_comma_separated(self.CORS_ALLOWED_ORIGINS)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = settings.SECRET_KEY
DEBUG = settings.DEBUG
ALLOWED_HOSTS = settings.get_allowed_hosts()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "corsheaders",
    # Local apps
    "apps.core",
    "apps.orders",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

CORS_ALLOWED_ORIGINS = settings.get_cors_allowed_origins()
CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=settings.DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": settings.REDIS_URL,
    }
}

# Celery
CELERY_BROKER_URL = settings.RABBITMQ_URL
CELERY_RESULT_BACKEND = settings.REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 30
CELERY_TASK_SOFT_TIME_LIMIT = 25

# Slack
SLACK_ENABLED = settings.SLACK_ENABLED
SLACK_BOT_TOKEN = settings.SLACK_BOT_TOKEN
SLACK_CHANNEL = settings.SLACK_CHANNEL

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
