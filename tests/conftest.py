"""Shared test fixtures."""

from decimal import Decimal

import pytest
from django.test import Client

from apps.orders.models import Order


@pytest.fixture
def api_client():
    """Django test client for API requests."""
    return Client()


@pytest.fixture
def sample_order(db):
    """Create a sample order for testing."""
    return Order.objects.create(
        customer_name="Test Customer",
        product_name="Test Product",
        quantity=2,
        price=Decimal("99.99"),
    )


@pytest.fixture
def sample_orders(db):
    """Create multiple sample orders for testing."""
    orders = []
    for i in range(5):
        order = Order.objects.create(
            customer_name=f"Customer {i}",
            product_name=f"Product {i}",
            quantity=i + 1,
            price=Decimal(f"{(i + 1) * 10}.00"),
        )
        orders.append(order)
    return orders
