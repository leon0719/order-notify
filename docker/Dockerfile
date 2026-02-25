# ===========================
# Stage 1: Build
# ===========================
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY . .
RUN uv run python manage.py collectstatic --noinput

# ===========================
# Stage 2: Runtime
# ===========================
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=builder /app /app

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
