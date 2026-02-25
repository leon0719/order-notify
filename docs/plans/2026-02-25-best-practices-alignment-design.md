# Best Practices Alignment Design

## Goal

Audit and refactor all installed packages to follow their official best practices, without changing the project's core architecture (service layer pattern, function-based API endpoints).

## Approach

Moderate refactor: fix all identified issues and align each package to its recommended usage patterns. Keep the same three-layer architecture (api -> services -> models) but upgrade how each tool is used.

## Tech Stack

- Django 5.2 + Django Ninja 1.4 (replacing django-ninja-extra)
- Celery 5.4 + RabbitMQ
- Loguru 0.7.3
- Pydantic Settings 2.7
- httpx 0.28
- PostgreSQL 16 + Redis 7

---

## Section 1: Django Ninja — Remove Extra, Use Pure NinjaAPI

### Problem

- `django-ninja-extra` and `NinjaExtraAPI` installed but none of its core features (class-based controllers, permissions, DI) are used
- Health check response uses `dict` instead of proper Schema
- `OrderSchema` manually lists all fields instead of using `ModelSchema`

### Changes

- `config/urls.py`: `NinjaExtraAPI` -> `NinjaAPI` (from `ninja`)
- `pyproject.toml`: remove `django-ninja-extra` dependency
- `config/settings/base.py`: remove `ninja_extra` from `INSTALLED_APPS`
- `apps/orders/schemas.py`: `OrderSchema` -> `ModelSchema` with `model = Order` and `model_fields` auto-mapping
- `apps/core/api.py`: health check response uses `HealthSchema` instead of `dict`

### Impact

API behavior unchanged. Lighter dependency. `ModelSchema` auto-syncs with model field changes.

---

## Section 2: Celery Task — Best Practice Alignment

### Problem

- `bind=True` set but `self` never used (autoretry handles retries)
- Notification task returns results that are never consumed, missing `ignore_result=True`
- Missing `retry_jitter=True` (explicit is better than implicit)
- Missing `reject_on_worker_lost=True` (prevents task loss when worker crashes with `acks_late`)
- Missing `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP` setting

### Changes

**`apps/orders/tasks.py`:**

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

- Remove `bind=True` and `self` parameter
- Add `ignore_result=True`, `retry_jitter=True`, `reject_on_worker_lost=True`

**`config/settings/base.py`:**

- Add `CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True`

---

## Section 3: Loguru — Use Built-in contextualize()

### Problem

- Manual `ContextVar` management instead of Loguru's built-in `logger.contextualize()`
- `user_id_var` set in middleware but never used in formatter
- Missing `enqueue=True` for thread safety in ASGI/Uvicorn
- Missing `backtrace` and `diagnose` configuration

### Changes

**`apps/core/log_config.py`:**

- Remove manual `ContextVar` definitions (`request_id_var`, `user_id_var`)
- Formatter uses `{extra[request_id]}` and `{extra[user_id]}` (injected by Loguru contextualize)
- `logger.add()` with `enqueue=True`, `backtrace=True`, `diagnose=False`

**`apps/core/middleware.py`:**

- Replace manual ContextVar set/reset with `logger.contextualize(request_id=..., user_id=...)`
- Cleaner code, proper user_id display in logs

---

## Section 4: Pydantic Settings — Native Types + Nested Models

### Problem

- `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` use `str` with manual comma parsing
- Slack settings (token, channel, enabled) not grouped

### Changes

**`config/settings/base.py`:**

- `ALLOWED_HOSTS: list[str]` and `CORS_ALLOWED_ORIGINS: list[str]` (native Pydantic parsing)
- Remove `_parse_comma_separated()`, `get_allowed_hosts()`, `get_cors_allowed_origins()` helpers
- Add `SlackSettings(BaseModel)` nested model with `bot_token`, `channel`, `enabled`
- Add `env_nested_delimiter="__"` to `SettingsConfigDict`
- Environment variables: `SLACK__BOT_TOKEN=xoxb-...`, `SLACK__CHANNEL=#orders`, `SLACK__ENABLED=true`

**`.env.local.example`:**

- Update format to match new settings structure

---

## Section 5: httpx — Fine-grained Timeout + Remove Unused orjson

### Problem

- Timeout uses `int` instead of `httpx.Timeout` for fine-grained control
- `orjson` in dependencies but never used

### Changes

**`apps/orders/tasks.py`:**

```python
timeout = httpx.Timeout(10.0, connect=5.0)
with httpx.Client(timeout=timeout) as client:
```

**`pyproject.toml`:**

- Remove `orjson>=3.10`

---

## Section 6: Django Model — Add Index + Strengthen Order Number Generation

### Problem

- `status` field used in queries but missing `db_index`
- `generate_order_number()` has collision risk under high concurrency

### Changes

**`apps/orders/models.py`:**

- Add `db_index=True` to `status` field
- Add uniqueness check loop (up to 5 attempts) in `generate_order_number()`

**New migration required** for the `db_index` change.

---

## Section 7: Testing — Fix Flaky Tests + Modernize Patterns

### Problem

- Health check test is flaky: `assert status_code in (200, 503)`
- Using `json.dumps()` + `content_type` instead of Django Client native JSON support
- httpx mock setup is overly verbose

### Changes

**`tests/test_health.py`:**

- Mock Redis cache and RabbitMQ socket for deterministic 200 response

**`tests/test_orders_api.py`:**

- Replace `json.dumps(data)` with plain `dict` (Django Client auto-serializes when `content_type="application/json"`)
- Remove `import json`

**`tests/test_orders_tasks.py`:**

- Simplify httpx Client mock using `mock_client_cls.return_value.__enter__.return_value`

---

## Section 8: Docker — Add Health Checks + Explicit Worker Config

### Problem

- api, celery_worker, celery_flower containers missing health checks
- Celery worker missing explicit `--pool` and `--concurrency` parameters

### Changes

**`docker/docker-compose.dev.yml`:**

- Add health checks for api (HTTP /api/health/), celery_worker (celery inspect ping), celery_flower (HTTP /healthcheck)
- Celery worker command: `--pool=prefork --concurrency=2`
- nginx `depends_on` uses `condition: service_healthy` for api

---

## Section 9: Pre-commit — Add mypy Hook

### Problem

- Pre-commit hooks only have ruff, missing type checking

### Changes

**`.pre-commit-config.yaml`:**

- Add `mirrors-mypy` hook with `additional_dependencies` for django-stubs and types-redis

---

## Files Changed Summary

| File | Action |
|------|--------|
| `config/urls.py` | Modify: NinjaExtraAPI -> NinjaAPI |
| `config/settings/base.py` | Modify: settings restructure, Celery config, remove ninja_extra |
| `apps/core/log_config.py` | Modify: remove ContextVar, add enqueue/backtrace |
| `apps/core/middleware.py` | Modify: use logger.contextualize() |
| `apps/core/api.py` | Modify: add HealthSchema |
| `apps/core/schemas.py` | Modify: add HealthSchema |
| `apps/orders/models.py` | Modify: db_index, order number retry |
| `apps/orders/schemas.py` | Modify: use ModelSchema |
| `apps/orders/tasks.py` | Modify: Celery decorators, httpx.Timeout |
| `pyproject.toml` | Modify: remove django-ninja-extra, orjson |
| `.env.local.example` | Modify: update format |
| `docker/docker-compose.dev.yml` | Modify: health checks, worker config |
| `.pre-commit-config.yaml` | Modify: add mypy hook |
| `tests/test_health.py` | Modify: mock external deps |
| `tests/test_orders_api.py` | Modify: simplify JSON |
| `tests/test_orders_tasks.py` | Modify: simplify mocks |
| `apps/orders/migrations/0002_*.py` | Create: db_index migration |
