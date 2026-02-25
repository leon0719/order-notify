"""Tests for orders API endpoints."""

import json
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
                data=json.dumps(
                    {
                        "customer_name": "Alice",
                        "product_name": "Widget",
                        "quantity": 3,
                        "price": "29.99",
                    }
                ),
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
            data=json.dumps({"customer_name": "Alice"}),
            content_type="application/json",
        )
        assert response.status_code == 422

    def test_create_order_invalid_quantity(self, api_client):
        """POST /api/orders/ with invalid quantity should return 422."""
        response = api_client.post(
            "/api/orders/",
            data=json.dumps(
                {
                    "customer_name": "Alice",
                    "product_name": "Widget",
                    "quantity": 0,
                    "price": "10.00",
                }
            ),
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
                data=json.dumps({"status": "confirmed"}),
                content_type="application/json",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    def test_update_status_invalid_transition(self, api_client, sample_order):
        """PATCH with invalid transition should return 409."""
        response = api_client.patch(
            f"/api/orders/{sample_order.id}/status/",
            data=json.dumps({"status": "delivered"}),
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
            data=json.dumps({"status": "pending"}),
            content_type="application/json",
        )
        assert response.status_code == 409
