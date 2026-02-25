"""Order models."""

import random
import string
from decimal import Decimal

from django.db import models
from uuid6 import uuid7


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.CONFIRMED: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
    OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED: [],
    OrderStatus.CANCELLED: [],
}


def generate_order_number() -> str:
    """Generate a unique order number like ORD-A3X7K9."""
    from apps.orders.models import Order

    for _ in range(5):
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        order_number = f"ORD-{suffix}"
        if not Order.objects.filter(order_number=order_number).exists():
            return order_number
    # Final attempt — if collision, unique constraint will catch it
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{suffix}"


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    order_number = models.CharField(max_length=20, unique=True, default=generate_order_number)
    customer_name = models.CharField(max_length=100)
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_number} - {self.customer_name}"
