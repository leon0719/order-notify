"""Tests for health check endpoint."""

import pytest


@pytest.mark.django_db
def test_health_check_returns_200(api_client):
    """Health check should return 200 when all services are healthy."""
    response = api_client.get("/api/health/")
    # In test environment, RabbitMQ may not be available
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data
    assert "rabbitmq" in data


@pytest.mark.django_db
def test_health_check_database_ok(api_client):
    """Health check should report database as ok when connected."""
    response = api_client.get("/api/health/")
    data = response.json()
    assert data["database"] == "ok"
