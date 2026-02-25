"""Tests for order service layer."""

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from apps.core.exceptions import InvalidStateError, NotFoundError
from apps.orders.models import Order, OrderStatus
from apps.orders.schemas import OrderCreateSchema, OrderStatusUpdateSchema
from apps.orders.services import create_order, get_order, get_orders, update_order_status


@pytest.mark.django_db
class TestCreateOrder:
    @patch("apps.orders.services.send_order_notification")
    def test_create_order(self, mock_task):
        """create_order should create an order and trigger notification."""
        mock_task.delay.return_value = None
        data = OrderCreateSchema(
            customer_name="Alice",
            product_name="Widget",
            quantity=3,
            price=Decimal("29.99"),
        )
        order = create_order(data)

        assert order.customer_name == "Alice"
        assert order.product_name == "Widget"
        assert order.quantity == 3
        assert order.price == Decimal("29.99")
        assert order.status == OrderStatus.PENDING
        assert order.order_number.startswith("ORD-")
        mock_task.delay.assert_called_once_with(str(order.id), "created")


@pytest.mark.django_db
class TestGetOrder:
    def test_get_existing_order(self, sample_order):
        """get_order should return order by ID."""
        order = get_order(sample_order.id)
        assert order.id == sample_order.id

    def test_get_nonexistent_order(self):
        """get_order should raise NotFoundError for missing order."""
        with pytest.raises(NotFoundError):
            get_order(uuid4())


@pytest.mark.django_db
class TestGetOrders:
    def test_get_orders_empty(self):
        """get_orders should return empty list when no orders exist."""
        orders, total = get_orders()
        assert orders == []
        assert total == 0

    def test_get_orders_with_data(self, sample_orders):
        """get_orders should return all orders."""
        orders, total = get_orders()
        assert total == 5
        assert len(orders) == 5

    def test_get_orders_pagination(self, sample_orders):
        """get_orders should respect page and page_size."""
        orders, total = get_orders(page=2, page_size=2)
        assert total == 5
        assert len(orders) == 2

    def test_get_orders_filter_status(self, sample_order):
        """get_orders should filter by status."""
        orders, total = get_orders(status="pending")
        assert total == 1
        assert orders[0].status == OrderStatus.PENDING


@pytest.mark.django_db
class TestUpdateOrderStatus:
    @patch("apps.orders.services.send_order_notification")
    def test_valid_transition_pending_to_confirmed(self, mock_task, sample_order):
        """Should allow pending -> confirmed."""
        mock_task.delay.return_value = None
        data = OrderStatusUpdateSchema(status="confirmed")
        order = update_order_status(sample_order.id, data)
        assert order.status == OrderStatus.CONFIRMED
        mock_task.delay.assert_called_once()

    @patch("apps.orders.services.send_order_notification")
    def test_valid_transition_confirmed_to_shipped(self, mock_task, db):
        """Should allow confirmed -> shipped."""
        mock_task.delay.return_value = None
        order = Order.objects.create(
            customer_name="Bob",
            product_name="Gadget",
            quantity=1,
            price=Decimal("50.00"),
            status=OrderStatus.CONFIRMED,
        )
        data = OrderStatusUpdateSchema(status="shipped")
        updated = update_order_status(order.id, data)
        assert updated.status == OrderStatus.SHIPPED

    def test_invalid_transition_pending_to_delivered(self, sample_order):
        """Should reject pending -> delivered."""
        data = OrderStatusUpdateSchema(status="delivered")
        with pytest.raises(InvalidStateError):
            update_order_status(sample_order.id, data)

    def test_invalid_transition_delivered_to_any(self, db):
        """Delivered orders should not allow any transitions."""
        order = Order.objects.create(
            customer_name="Carol",
            product_name="Thing",
            quantity=1,
            price=Decimal("10.00"),
            status=OrderStatus.DELIVERED,
        )
        data = OrderStatusUpdateSchema(status="pending")
        with pytest.raises(InvalidStateError):
            update_order_status(order.id, data)

    def test_update_nonexistent_order(self):
        """Should raise NotFoundError for missing order."""
        data = OrderStatusUpdateSchema(status="confirmed")
        with pytest.raises(NotFoundError):
            update_order_status(uuid4(), data)
