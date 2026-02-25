# Order Notify

Django Ninja + Celery + RabbitMQ + Nginx 學習專案。
建立訂單後，透過 Celery 非同步發送 Slack 通知。

## Tech Stack

| 類別 | 技術 |
|------|------|
| Framework | Django 5.2 + Django Ninja |
| Task Queue | Celery + RabbitMQ (broker) + Redis (result backend) |
| Database | PostgreSQL 16 |
| Reverse Proxy | Nginx |
| Notification | Slack `chat.postMessage` API (Block Kit) |
| Package Manager | uv |
| Container | Docker Compose (7 services) |

## Architecture

```
HTTP Request
    │
    ▼
  Nginx (:80)  ──  rate limit (10 req/s per IP)
    │
    ▼
  Django Ninja API (:8000)
    │
    ├── api.py        ← 驗證輸入、回傳結果
    ├── services.py   ← 商業邏輯、狀態驗證
    ├── models.py     ← ORM、狀態機定義
    │
    └── transaction.on_commit()
            │
            ▼
        RabbitMQ (:5672)  ──  Celery Broker
            │
            ▼
        Celery Worker  ──  send_order_notification
            │
            ├── Slack API (chat.postMessage)
            └── Redis (:6379)  ──  Result Backend
```

## Order Status Flow

```
pending ──→ confirmed ──→ shipped ──→ delivered
   │            │
   └──→ cancelled ←──┘
```

delivered 和 cancelled 為終態，不可再變更。

## Quick Start

### 1. 環境設定

```bash
cp .env.local.example .env.local
```

編輯 `.env.local`，填入 `SECRET_KEY`：

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 2. 啟動服務

```bash
make up         # 啟動 7 個 Docker 容器
make migrate    # 執行資料庫 migration
```

### 3. 驗證

- API Docs: http://localhost:80/api/docs
- RabbitMQ UI: http://localhost:15672 (guest / guest)
- Flower: http://localhost:5555

### 4. 測試 API

```bash
# 建立訂單
curl -X POST http://localhost:80/api/orders/ \
  -H "Content-Type: application/json" \
  -d '{"customer_name": "Alice", "product_name": "Widget", "quantity": 3, "price": "29.99"}'

# 列出訂單
curl http://localhost:80/api/orders/

# 更新狀態
curl -X PATCH http://localhost:80/api/orders/{id}/status/ \
  -H "Content-Type: application/json" \
  -d '{"status": "confirmed"}'
```

## Slack Notification

使用 Slack Bot Token + `chat.postMessage` API 發送通知。

### 設定方式

1. 在 [Slack API](https://api.slack.com/apps) 建立 App
2. 新增 Bot Token Scopes: `chat:write`, `chat:write.public`
3. 安裝 App 到 Workspace，取得 `xoxb-` 開頭的 Bot Token
4. 編輯 `.env.local`：

```env
SLACK_ENABLED=true
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_CHANNEL=#your-channel
```

通知內容使用 Slack Block Kit 格式，包含訂單編號、客戶、商品、數量、金額和狀態，並以顏色區分狀態。

`SLACK_ENABLED=false` 時，Celery task 會跳過發送（預設行為）。

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health/` | Health check (DB + Redis + RabbitMQ) |
| `POST` | `/api/orders/` | 建立訂單 → 觸發 Celery notification |
| `GET` | `/api/orders/` | 訂單列表（分頁 + status 篩選） |
| `GET` | `/api/orders/{id}/` | 訂單詳情 |
| `PATCH` | `/api/orders/{id}/status/` | 更新狀態 → 觸發 Celery notification |

## Docker Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| nginx | nginx:1.25-alpine | 80 | 反向代理 + 靜態檔案 + rate limiting |
| api | Dockerfile.dev | 8000 | Django Ninja + Uvicorn (hot reload) |
| db | postgres:16-alpine | 5433→5432 | PostgreSQL |
| redis | redis:7-alpine | 6379 | Cache + Celery result backend |
| rabbitmq | rabbitmq:3-management-alpine | 5672, 15672 | Celery broker + 管理介面 |
| celery_worker | Dockerfile.dev | - | 背景任務執行 |
| celery_flower | Dockerfile.dev | 5555 | Celery 監控 UI |

## Make Commands

```bash
# Docker
make up              # 啟動所有服務
make down            # 停止所有服務
make rebuild         # 重新建構並啟動
make logs            # 查看所有日誌
make logs-worker     # 查看 Celery worker 日誌

# Django
make migrate         # 執行 migration
make makemigrations  # 建立 migration
make createsuperuser # 建立管理員
make shell           # Django shell

# Code Quality
make format          # ruff format
make lint            # ruff check
make type-check      # mypy
make test            # pytest
make coverage        # pytest + coverage

# Cleanup
make clean           # 清理 cache
make docker-clean    # 移除 Docker volumes
```

## Project Structure

```
order-notify/
├── apps/
│   ├── core/              # 共用工具
│   │   ├── api.py         #   Health check (DB + Redis + RabbitMQ)
│   │   ├── exceptions.py  #   AppError, NotFoundError, ValidationError, InvalidStateError
│   │   ├── schemas.py     #   ErrorSchema, MessageSchema
│   │   ├── middleware.py   #   RequestContextMiddleware (structured logging)
│   │   └── log_config.py  #   Loguru + request_id context
│   └── orders/            # 訂單功能
│       ├── models.py      #   Order model (UUID7 PK, 狀態機)
│       ├── api.py         #   Django Ninja router (4 endpoints)
│       ├── schemas.py     #   Pydantic schemas (create, update, response)
│       ├── services.py    #   商業邏輯 + transaction.on_commit()
│       ├── tasks.py       #   Celery task (Slack chat.postMessage)
│       └── admin.py       #   Django admin
├── config/
│   ├── __init__.py        # import celery_app
│   ├── celery.py          # Celery app (autodiscover_tasks)
│   ├── urls.py            # NinjaExtraAPI + routers + exception handlers
│   └── settings/
│       ├── base.py        #   Pydantic BaseSettings + Celery config
│       ├── local.py       #   開發環境
│       └── prod.py        #   正式環境
├── docker/
│   ├── Dockerfile.dev     # uv + hot reload
│   ├── Dockerfile         # Production multi-stage
│   ├── docker-compose.dev.yml
│   └── nginx/
│       ├── nginx.conf     #   gzip, rate limit zone
│       └── default.conf   #   upstream, proxy_pass, security headers
├── tests/
│   ├── conftest.py        # fixtures (api_client, sample_order)
│   ├── test_health.py
│   ├── test_orders_api.py
│   ├── test_orders_services.py
│   └── test_orders_tasks.py
├── .env.local.example
├── Makefile
└── pyproject.toml
```
