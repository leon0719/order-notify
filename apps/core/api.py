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
        # Parse host and port from amqp URL
        # amqp://guest:guest@rabbitmq:5672//

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
