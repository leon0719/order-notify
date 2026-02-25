# Best Practices Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor all installed packages to follow their official best practices without changing the project's core architecture.

**Architecture:** Keep the existing three-layer architecture (api -> services -> models) with function-based endpoints. Upgrade how each tool is used: pure NinjaAPI instead of NinjaExtraAPI, Loguru contextualize() instead of manual ContextVar, Pydantic Settings native list types and nested models, Celery task best practices, and httpx fine-grained timeout.

**Tech Stack:** Django 5.2, Django Ninja 1.4, Celery 5.4, Loguru 0.7.3, Pydantic Settings 2.7, httpx 0.28, PostgreSQL 16, Redis 7

---

### Task 1: Remove django-ninja-extra, Switch to Pure NinjaAPI

**Files:**
- Modify: `pyproject.toml:10-11`
- Modify: `config/settings/base.py:72`
- Modify: `config/urls.py:9,16`

**Step 1: Update pyproject.toml — remove django-ninja-extra**

Remove the `django-ninja-extra` line from dependencies:

```toml
dependencies = [
    # Django & API
    "django>=5.2",
    "django-ninja>=1.4",
    "django-cors-headers>=4.6",
    # Database
    ...
```

(Remove `"django-ninja-extra>=0.21",` from the list)

**Step 2: Update config/settings/base.py — remove ninja_extra from INSTALLED_APPS**

Change `INSTALLED_APPS` to remove `"ninja_extra"`:

```python
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
```

**Step 3: Update config/urls.py — replace NinjaExtraAPI with NinjaAPI**

Replace the full file content. Key changes:
- `from ninja_extra import NinjaExtraAPI` -> `from ninja import NinjaAPI`
- `api = NinjaExtraAPI(...)` -> `api = NinjaAPI(...)`

```python
"""URL configuration for the project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import DatabaseError, IntegrityError
from django.http import HttpRequest
from django.urls import path
from ninja import NinjaAPI

from apps.core.api import router as core_router
from apps.core.exceptions import AppValidationError, InvalidStateError, NotFoundError
from apps.core.log_config import logger
from apps.orders.api import router as orders_router

api = NinjaAPI(
    title="Order Notify API",
    version="1.0.0",
    description="Django Ninja + Celery Order Notification System",
)


@api.exception_handler(NotFoundError)
def handle_not_found(request: HttpRequest, exc: NotFoundError):
    return api.create_response(request, {"error": exc.message, "code": exc.code}, status=404)


@api.exception_handler(AppValidationError)
def handle_validation_error(request: HttpRequest, exc: AppValidationError):
    return api.create_response(request, {"error": exc.message, "code": exc.code}, status=400)


@api.exception_handler(InvalidStateError)
def handle_invalid_state(request: HttpRequest, exc: InvalidStateError):
    return api.create_response(request, {"error": exc.message, "code": exc.code}, status=409)


@api.exception_handler(IntegrityError)
def handle_integrity_error(request: HttpRequest, exc: IntegrityError):
    logger.warning("Integrity error: {}", exc)
    return api.create_response(
        request,
        {"error": "Resource already exists or constraint violated", "code": "INTEGRITY_ERROR"},
        status=400,
    )


@api.exception_handler(DatabaseError)
def handle_database_error(request: HttpRequest, exc: DatabaseError):
    logger.exception("Database error: {}", exc)
    return api.create_response(
        request,
        {"error": "Database error occurred", "code": "DATABASE_ERROR"},
        status=500,
    )


api.add_router("", core_router, tags=["health"])
api.add_router("/orders", orders_router, tags=["orders"])

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    *static(settings.STATIC_URL, document_root=settings.STATIC_ROOT),
]
```

**Step 4: Run tests to verify nothing broke**

Run: `make test`
Expected: All existing tests PASS

**Step 5: Commit**

```bash
git add pyproject.toml config/settings/base.py config/urls.py
git commit -m "refactor: replace NinjaExtraAPI with pure NinjaAPI

Remove django-ninja-extra dependency since none of its features
(class-based controllers, permissions, DI) are used."
```

---

### Task 2: Upgrade OrderSchema to ModelSchema + Add HealthSchema

**Files:**
- Modify: `apps/orders/schemas.py:26-37`
- Modify: `apps/core/schemas.py`
- Modify: `apps/core/api.py:17`

**Step 1: Update apps/orders/schemas.py — use ModelSchema**

Replace `OrderSchema` with `ModelSchema`. Keep other schemas unchanged:

```python
"""Order Pydantic schemas."""

from decimal import Decimal

from ninja import ModelSchema, Schema
from pydantic import Field

from apps.orders.models import Order


class OrderCreateSchema(Schema):
    """Schema for creating an order."""

    customer_name: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)
    price: Decimal = Field(ge=0, decimal_places=2)


class OrderStatusUpdateSchema(Schema):
    """Schema for updating order status."""

    status: str = Field(pattern=r"^(pending|confirmed|shipped|delivered|cancelled)$")


class OrderSchema(ModelSchema):
    """Schema for order response."""

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer_name",
            "product_name",
            "quantity",
            "price",
            "status",
            "created_at",
            "updated_at",
        ]


class PaginatedOrdersSchema(Schema):
    """Schema for paginated orders response."""

    items: list[OrderSchema]
    total: int
    page: int
    page_size: int
```

**Step 2: Add HealthSchema to apps/core/schemas.py**

```python
"""Core schemas shared across applications."""

from ninja import Schema
from pydantic import Field


class ErrorSchema(Schema):
    """Schema for error response."""

    error: str = Field(min_length=1, max_length=500)
    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z_]+$")


class MessageSchema(Schema):
    """Schema for simple message response."""

    message: str


class HealthSchema(Schema):
    """Schema for health check response."""

    status: str
    database: str
    redis: str
    rabbitmq: str
```

**Step 3: Update apps/core/api.py to use HealthSchema**

Replace `response={200: dict, 503: dict}` with `response={200: HealthSchema, 503: HealthSchema}`:

```python
"""Core API endpoints - health check."""

import socket
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, OperationalError, connection
from ninja import Router
from redis.exceptions import RedisError

from apps.core.log_config import logger
from apps.core.schemas import HealthSchema

router = Router()


@router.get("/health/", response={200: HealthSchema, 503: HealthSchema})
def health_check(request):
    """Health check endpoint for load balancers and container orchestration."""
    health = {
        "status": "healthy",
        "database": "ok",
        "redis": "ok",
        "rabbitmq": "ok",
    }

    # Check database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except (DatabaseError, OperationalError):
        logger.exception("Database health check failed")
        health["database"] = "error"
        health["status"] = "unhealthy"

    # Check Redis
    try:
        cache.set("health_check", "ok", 1)
        cache.get("health_check")
    except (RedisError, ConnectionError, TimeoutError):
        logger.exception("Redis health check failed")
        health["redis"] = "error"
        health["status"] = "unhealthy"

    # Check RabbitMQ (basic TCP connection check)
    try:
        rabbitmq_url = settings.CELERY_BROKER_URL
        parsed = urlparse(rabbitmq_url)
        host = parsed.hostname or "rabbitmq"
        port = parsed.port or 5672
        sock = socket.create_connection((host, port), timeout=3)
        sock.close()
    except (OSError, TimeoutError):
        logger.exception("RabbitMQ health check failed")
        health["rabbitmq"] = "error"
        health["status"] = "unhealthy"

    status_code = 200 if health["status"] == "healthy" else 503
    return status_code, health
```

**Step 4: Run tests**

Run: `make test`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/orders/schemas.py apps/core/schemas.py apps/core/api.py
git commit -m "refactor: use ModelSchema for OrderSchema, add HealthSchema

ModelSchema auto-maps Order model fields, reducing manual maintenance.
HealthSchema replaces raw dict for proper API documentation."
```

---

### Task 3: Celery Task Best Practices

**Files:**
- Modify: `apps/orders/tasks.py:88-95`
- Modify: `config/settings/base.py:129-139`

**Step 1: Update apps/orders/tasks.py — fix task decorator and remove self**

Replace the task decorator and function signature:

```python
@shared_task(
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    ignore_result=True,
    reject_on_worker_lost=True,
)
def send_order_notification(order_id: str, event: str):
```

The rest of the function body stays exactly the same (lines 96-136), except no `self` references exist so nothing else changes.

**Step 2: Update config/settings/base.py — add CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP**

After `CELERY_TASK_SOFT_TIME_LIMIT = 25`, add:

```python
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
```

**Step 3: Run tests**

Run: `make test`
Expected: All tests PASS (task tests call the function directly without `self`)

**Step 4: Commit**

```bash
git add apps/orders/tasks.py config/settings/base.py
git commit -m "refactor: align Celery task with best practices

Remove unused bind=True/self, add ignore_result, retry_jitter,
reject_on_worker_lost, and CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP."
```

---

### Task 4: Loguru — Use contextualize() Instead of Manual ContextVar

**Files:**
- Modify: `apps/core/log_config.py`
- Modify: `apps/core/middleware.py`

**Step 1: Rewrite apps/core/log_config.py**

```python
"""Loguru logging configuration."""

import sys

from loguru import logger


def formatter(record):
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[request_id]}</cyan> | "
        "<cyan>{extra[user_id]}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n"
    )


# Remove default logger and add custom one
logger.remove()
logger.add(
    sys.stderr,
    format=formatter,
    level="DEBUG",
    colorize=True,
    enqueue=True,
    backtrace=True,
    diagnose=False,
)

# Configure default extra values for when contextualize() is not active
logger = logger.bind(request_id="-", user_id="-")

__all__ = ["logger"]
```

**Step 2: Rewrite apps/core/middleware.py**

```python
"""Custom middleware for the application."""

import re
import uuid

from apps.core.log_config import logger

_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


class RequestContextMiddleware:
    """Middleware to add request context for structured logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_id = request.headers.get("X-Request-ID", "")
        if raw_id and _VALID_REQUEST_ID.match(raw_id):
            request_id = raw_id
        else:
            request_id = str(uuid.uuid4())[:8]

        if hasattr(request, "user") and request.user.is_authenticated:
            user_id = str(request.user.id)
        else:
            user_id = "-"

        with logger.contextualize(request_id=request_id, user_id=user_id):
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
```

**Step 3: Run tests**

Run: `make test`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add apps/core/log_config.py apps/core/middleware.py
git commit -m "refactor: use Loguru contextualize() for request context

Replace manual ContextVar management with Loguru's built-in
contextualize(). Add user_id to log format. Enable enqueue for
thread safety, backtrace for better exceptions."
```

---

### Task 5: Pydantic Settings — Native list[str] + Nested SlackSettings

**Files:**
- Modify: `config/settings/base.py:14-55,90-91,141-144`
- Modify: `.env.local.example`
- Modify: `apps/orders/tasks.py:97-103`

**Step 1: Rewrite Settings class in config/settings/base.py**

Replace the entire Settings class and related code:

```python
"""Django base settings."""

import os
from functools import lru_cache
from pathlib import Path

import dj_database_url
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

_env = os.getenv("ENV", "local")
_env_file = f".env.{_env}"


class SlackSettings(BaseModel):
    """Slack notification settings."""

    bot_token: str = ""
    channel: str = ""
    enabled: bool = False


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    # Required
    SECRET_KEY: str
    DATABASE_URL: str
    REDIS_URL: str
    RABBITMQ_URL: str

    # Optional
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]
    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Slack (nested)
    SLACK: SlackSettings = SlackSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
```

Then update the Django settings that reference the Settings object. Replace the old lines:

```python
# Replace these old lines:
# ALLOWED_HOSTS = settings.get_allowed_hosts()
# CORS_ALLOWED_ORIGINS = settings.get_cors_allowed_origins()
# SLACK_ENABLED = settings.SLACK_ENABLED
# SLACK_BOT_TOKEN = settings.SLACK_BOT_TOKEN
# SLACK_CHANNEL = settings.SLACK_CHANNEL

# With:
ALLOWED_HOSTS = settings.ALLOWED_HOSTS
CORS_ALLOWED_ORIGINS = settings.CORS_ALLOWED_ORIGINS
SLACK_ENABLED = settings.SLACK.enabled
SLACK_BOT_TOKEN = settings.SLACK.bot_token
SLACK_CHANNEL = settings.SLACK.channel
```

Everything else in base.py stays the same.

**Step 2: Update .env.local.example**

```
# ==================================
# Local Development Environment
# ==================================
# cp .env.local.example .env.local

# ===================
# Environment
# ===================
ENV=local
DJANGO_SETTINGS_MODULE=config.settings.local

# ===================
# Required Settings
# ===================

# Django
# python -c "import secrets; print(secrets.token_urlsafe(50))"
SECRET_KEY=

# Database (Docker internal)
DATABASE_URL=postgresql://order_notify:order_notify@db:5432/order_notify

# Redis (Docker internal)
REDIS_URL=redis://redis:6379/0

# RabbitMQ (Docker internal)
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672//

# ===================
# Optional Settings
# ===================

DEBUG=true
ALLOWED_HOSTS=["localhost","127.0.0.1"]
CORS_ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]

# Slack Notification (chat.postMessage API)
# SLACK__ENABLED=true
# SLACK__BOT_TOKEN=xoxb-your-bot-token
# SLACK__CHANNEL=#your-channel
```

**Step 3: Run tests**

Run: `make test`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add config/settings/base.py .env.local.example
git commit -m "refactor: use native list[str] and nested SlackSettings in Pydantic Settings

Replace manual comma parsing with Pydantic's native list[str] type.
Group Slack settings into nested SlackSettings model with env_nested_delimiter."
```

---

### Task 6: httpx Timeout + Remove orjson

**Files:**
- Modify: `apps/orders/tasks.py:120`
- Modify: `pyproject.toml:25`

**Step 1: Update apps/orders/tasks.py — use httpx.Timeout**

Replace line 120:

```python
# Old:
    with httpx.Client(timeout=10) as client:

# New:
    timeout = httpx.Timeout(10.0, connect=5.0)
    with httpx.Client(timeout=timeout) as client:
```

**Step 2: Remove orjson from pyproject.toml**

Remove `"orjson>=3.10",` from the dependencies list.

**Step 3: Run tests**

Run: `make test`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add apps/orders/tasks.py pyproject.toml
git commit -m "refactor: use httpx.Timeout for fine-grained control, remove unused orjson

Separate connect timeout (5s) from overall timeout (10s).
Remove orjson dependency that was never used in the project."
```

---

### Task 7: Django Model — Add db_index + Order Number Retry

**Files:**
- Modify: `apps/orders/models.py:29-32,42-46`
- Create: `apps/orders/migrations/0002_order_status_db_index.py` (auto-generated)

**Step 1: Update apps/orders/models.py — add db_index to status**

```python
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
```

**Step 2: Update generate_order_number() with uniqueness check**

```python
def generate_order_number() -> str:
    """Generate a unique order number like ORD-A3X7K9."""
    for _ in range(5):
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        order_number = f"ORD-{suffix}"
        if not Order.objects.filter(order_number=order_number).exists():
            return order_number
    # Final attempt — if collision, unique constraint will catch it
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{suffix}"
```

Note: This creates a circular reference since `generate_order_number` is defined before `Order`. To fix this, use a lazy import or move the check:

```python
def generate_order_number() -> str:
    """Generate a unique order number like ORD-A3X7K9."""
    from apps.orders.models import Order

    for _ in range(5):
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        order_number = f"ORD-{suffix}"
        if not Order.objects.filter(order_number=order_number).exists():
            return order_number
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{suffix}"
```

Wait — `generate_order_number` is in the same file as `Order`, defined before it. A lazy import inside the function avoids the circular reference.

**Step 3: Generate migration**

Run: `make makemigrations`
Expected: Creates `apps/orders/migrations/0002_order_status_db_index.py`

**Step 4: Run tests**

Run: `make test`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add apps/orders/models.py apps/orders/migrations/0002_*.py
git commit -m "refactor: add db_index to status field, add order number collision retry

Index on status improves filter query performance.
Order number generation retries up to 5 times to avoid collisions."
```

---

### Task 8: Fix Flaky Health Check Test

**Files:**
- Modify: `tests/test_health.py`

**Step 1: Rewrite tests/test_health.py with mocked dependencies**

```python
"""Tests for health check endpoint."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
@patch("apps.core.api.socket.create_connection")
@patch("apps.core.api.cache")
def test_health_check_returns_200(mock_cache, mock_socket, api_client):
    """Health check should return 200 when all services are healthy."""
    mock_cache.set.return_value = True
    mock_cache.get.return_value = "ok"
    mock_socket.return_value = MagicMock()

    response = api_client.get("/api/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ok"
    assert data["redis"] == "ok"
    assert data["rabbitmq"] == "ok"


@pytest.mark.django_db
def test_health_check_database_ok(api_client):
    """Health check should report database as ok when connected."""
    response = api_client.get("/api/health/")
    data = response.json()
    assert data["database"] == "ok"


@pytest.mark.django_db
@patch("apps.core.api.socket.create_connection", side_effect=OSError("Connection refused"))
@patch("apps.core.api.cache")
def test_health_check_returns_503_when_rabbitmq_down(mock_cache, mock_socket, api_client):
    """Health check should return 503 when RabbitMQ is unreachable."""
    mock_cache.set.return_value = True
    mock_cache.get.return_value = "ok"

    response = api_client.get("/api/health/")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["rabbitmq"] == "error"
```

**Step 2: Run tests**

Run: `make test`
Expected: All tests PASS (no more flakiness)

**Step 3: Commit**

```bash
git add tests/test_health.py
git commit -m "test: fix flaky health check test with mocked dependencies

Mock Redis cache and RabbitMQ socket for deterministic results.
Add explicit test for 503 when RabbitMQ is down."
```

---

### Task 9: Simplify API Test JSON Serialization

**Files:**
- Modify: `tests/test_orders_api.py`

**Step 1: Rewrite tests/test_orders_api.py — remove json.dumps**

```python
"""Tests for orders API endpoints."""

from unittest.mock import patch

import pytest

from apps.orders.models import Order, OrderStatus


@pytest.mark.django_db
class TestCreateOrder:
    def test_create_order_success(self, api_client):
        """POST /api/orders/ should create an order and return 201."""
        with patch("apps.orders.services.send_order_notification") as mock_task:
            mock_task.delay.return_value = None
            response = api_client.post(
                "/api/orders/",
                data={
                    "customer_name": "Alice",
                    "product_name": "Widget",
                    "quantity": 3,
                    "price": "29.99",
                },
                content_type="application/json",
            )

        assert response.status_code == 201
        data = response.json()
        assert data["customer_name"] == "Alice"
        assert data["product_name"] == "Widget"
        assert data["quantity"] == 3
        assert data["status"] == "pending"
        assert data["order_number"].startswith("ORD-")
        assert Order.objects.count() == 1

    def test_create_order_missing_fields(self, api_client):
        """POST /api/orders/ with missing fields should return 422."""
        response = api_client.post(
            "/api/orders/",
            data={"customer_name": "Alice"},
            content_type="application/json",
        )
        assert response.status_code == 422

    def test_create_order_invalid_quantity(self, api_client):
        """POST /api/orders/ with invalid quantity should return 422."""
        response = api_client.post(
            "/api/orders/",
            data={
                "customer_name": "Alice",
                "product_name": "Widget",
                "quantity": 0,
                "price": "10.00",
            },
            content_type="application/json",
        )
        assert response.status_code == 422


@pytest.mark.django_db
class TestListOrders:
    def test_list_orders_empty(self, api_client):
        """GET /api/orders/ with no orders should return empty list."""
        response = api_client.get("/api/orders/")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_orders_with_data(self, api_client, sample_orders):
        """GET /api/orders/ should return paginated orders."""
        response = api_client.get("/api/orders/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5

    def test_list_orders_pagination(self, api_client, sample_orders):
        """GET /api/orders/?page=1&page_size=2 should paginate."""
        response = api_client.get("/api/orders/?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_list_orders_filter_by_status(self, api_client, sample_order):
        """GET /api/orders/?status=pending should filter by status."""
        response = api_client.get("/api/orders/?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "pending"


@pytest.mark.django_db
class TestGetOrder:
    def test_get_order_success(self, api_client, sample_order):
        """GET /api/orders/{id}/ should return order details."""
        response = api_client.get(f"/api/orders/{sample_order.id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_order.id)
        assert data["customer_name"] == "Test Customer"

    def test_get_order_not_found(self, api_client):
        """GET /api/orders/{id}/ with invalid ID should return 404."""
        response = api_client.get("/api/orders/00000000-0000-0000-0000-000000000000/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestUpdateOrderStatus:
    def test_update_status_success(self, api_client, sample_order):
        """PATCH /api/orders/{id}/status/ should update status."""
        with patch("apps.orders.services.send_order_notification") as mock_task:
            mock_task.delay.return_value = None
            response = api_client.patch(
                f"/api/orders/{sample_order.id}/status/",
                data={"status": "confirmed"},
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    def test_update_status_invalid_transition(self, api_client, sample_order):
        """PATCH with invalid transition should return 409."""
        response = api_client.patch(
            f"/api/orders/{sample_order.id}/status/",
            data={"status": "delivered"},
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_update_status_cancelled_cannot_change(self, api_client, db):
        """Cancelled order should not allow further status changes."""
        order = Order.objects.create(
            customer_name="Bob",
            product_name="Gadget",
            quantity=1,
            price="50.00",
            status=OrderStatus.CANCELLED,
        )
        response = api_client.patch(
            f"/api/orders/{order.id}/status/",
            data={"status": "pending"},
            content_type="application/json",
        )
        assert response.status_code == 409
```

**Step 2: Run tests**

Run: `make test`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_orders_api.py
git commit -m "test: simplify API tests by removing manual json.dumps

Django test Client auto-serializes dict to JSON when
content_type='application/json' is set."
```

---

### Task 10: Simplify Task Test Mocks

**Files:**
- Modify: `tests/test_orders_tasks.py`

**Step 1: Rewrite tests/test_orders_tasks.py with simplified mocks**

```python
"""Tests for Celery order notification tasks."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from apps.orders.models import Order
from apps.orders.tasks import SLACK_API_URL, send_order_notification


@pytest.mark.django_db
class TestSendOrderNotification:
    @patch("apps.orders.tasks.settings")
    def test_skip_when_slack_disabled(self, mock_settings, sample_order):
        """Task should skip when SLACK_ENABLED is False."""
        mock_settings.SLACK_ENABLED = False
        result = send_order_notification(str(sample_order.id), "created")
        assert result["status"] == "skipped"
        assert result["reason"] == "slack_disabled"

    @patch("apps.orders.tasks.settings")
    def test_skip_when_no_slack_config(self, mock_settings, sample_order):
        """Task should skip when SLACK_BOT_TOKEN or SLACK_CHANNEL is empty."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = ""
        mock_settings.SLACK_CHANNEL = ""
        result = send_order_notification(str(sample_order.id), "created")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_slack_config"

    @patch("apps.orders.tasks.settings")
    def test_order_not_found(self, mock_settings):
        """Task should return error when order doesn't exist."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = "xoxb-test-token"
        mock_settings.SLACK_CHANNEL = "#test"
        result = send_order_notification(str(uuid4()), "created")
        assert result["status"] == "error"
        assert result["reason"] == "order_not_found"

    @patch("apps.orders.tasks.httpx.Client")
    @patch("apps.orders.tasks.settings")
    def test_send_notification_success(self, mock_settings, mock_client_cls, sample_order):
        """Task should send notification to Slack successfully."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = "xoxb-test-token"
        mock_settings.SLACK_CHANNEL = "#orders"

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}

        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_response

        result = send_order_notification(str(sample_order.id), "created")

        assert result["status"] == "sent"
        assert result["order_number"] == sample_order.order_number
        call_args = mock_client.post.call_args
        assert call_args[0][0] == SLACK_API_URL
        assert call_args[1]["headers"]["Authorization"] == "Bearer xoxb-test-token"
        assert call_args[1]["json"]["channel"] == "#orders"

    @patch("apps.orders.tasks.httpx.Client")
    @patch("apps.orders.tasks.settings")
    def test_send_notification_for_status_update(self, mock_settings, mock_client_cls, db):
        """Task should send notification for status update events."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = "xoxb-test-token"
        mock_settings.SLACK_CHANNEL = "#orders"

        order = Order.objects.create(
            customer_name="Test",
            product_name="Product",
            quantity=1,
            price=Decimal("25.00"),
            status="confirmed",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}

        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = mock_response

        result = send_order_notification(str(order.id), "status_updated")

        assert result["status"] == "sent"
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["channel"] == "#orders"
        assert "attachments" in payload
```

**Step 2: Run tests**

Run: `make test`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_orders_tasks.py
git commit -m "test: simplify httpx Client mocks in task tests

Use mock_client_cls.return_value.__enter__.return_value pattern
instead of manually setting __enter__ and __exit__."
```

---

### Task 11: Docker Health Checks + Worker Config

**Files:**
- Modify: `docker/docker-compose.dev.yml`

**Step 1: Update docker/docker-compose.dev.yml**

```yaml
services:
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - ../staticfiles:/app/staticfiles:ro
    depends_on:
      api:
        condition: service_healthy
    networks:
      - order_notify

  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile.dev
    ports:
      - "8000:8000"
    volumes:
      - ..:/app
      - api_venv:/app/.venv
    env_file:
      - ../.env.local
    environment:
      - UV_LINK_MODE=copy
    command: >
      sh -c "uv run python manage.py collectstatic --noinput &&
             uv run uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --reload"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/api/health/\")'"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - order_notify

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: order_notify
      POSTGRES_PASSWORD: order_notify
      POSTGRES_DB: order_notify
    ports:
      - "5433:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U order_notify -d order_notify"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - order_notify

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - order_notify

  rabbitmq:
    image: rabbitmq:3-management-alpine
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 10s
      retries: 5
    networks:
      - order_notify

  celery_worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile.dev
    volumes:
      - ..:/app
      - api_venv:/app/.venv
    env_file:
      - ../.env.local
    environment:
      - UV_LINK_MODE=copy
    command: uv run celery -A config worker -l info --pool=prefork --concurrency=2
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "uv run celery -A config inspect ping --timeout=5"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    networks:
      - order_notify

  celery_flower:
    build:
      context: ..
      dockerfile: docker/Dockerfile.dev
    ports:
      - "5555:5555"
    volumes:
      - ..:/app
      - api_venv:/app/.venv
    env_file:
      - ../.env.local
    environment:
      - UV_LINK_MODE=copy
    command: uv run celery -A config flower --port=5555
    depends_on:
      - rabbitmq
      - celery_worker
    healthcheck:
      test: ["CMD-SHELL", "python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:5555/healthcheck\")'"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks:
      - order_notify

volumes:
  postgres_data:
  redis_data:
  rabbitmq_data:
  api_venv:

networks:
  order_notify:
    driver: bridge
```

**Step 2: Commit**

```bash
git add docker/docker-compose.dev.yml
git commit -m "infra: add health checks for api, worker, flower containers

Add HTTP health check for api and flower, celery inspect ping for worker.
Explicit --pool=prefork --concurrency=2 for dev worker.
Nginx waits for api healthy before starting."
```

---

### Task 12: Add mypy to Pre-commit Hooks

**Files:**
- Modify: `.pre-commit-config.yaml`

**Step 1: Update .pre-commit-config.yaml**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.1
    hooks:
      - id: mypy
        additional_dependencies:
          - django-stubs>=5.2
          - django-stubs-ext>=5.2
          - types-redis>=4.6
        args: [--config-file=pyproject.toml]
```

**Step 2: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "ci: add mypy type checking to pre-commit hooks

Catch type errors before commit with django-stubs and types-redis."
```

---

### Task 13: Final Verification

**Step 1: Run full test suite**

Run: `make test`
Expected: All tests PASS

**Step 2: Run linting and type checking**

Run: `make all`
Expected: format, lint, type-check all pass

**Step 3: Verify Docker Compose syntax**

Run: `docker compose -f docker/docker-compose.dev.yml config --quiet`
Expected: No errors

**Step 4: Final commit if any formatting changes**

```bash
git add -A
git status
# Only commit if there are changes from formatting
git commit -m "style: apply formatting fixes from final verification"
```
