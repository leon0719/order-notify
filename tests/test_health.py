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
