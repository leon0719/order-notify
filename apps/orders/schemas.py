"""Order Pydantic schemas."""

from decimal import Decimal

from ninja import ModelSchema, Schema
from pydantic import Field

from apps.orders.models import Order


class OrderCreateSchema(Schema):
    """Schema for creating an order."""

    customer_name: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)
    price: Decimal = Field(ge=0, decimal_places=2)


class OrderStatusUpdateSchema(Schema):
    """Schema for updating order status."""

    status: str = Field(pattern=r"^(pending|confirmed|shipped|delivered|cancelled)$")


class OrderSchema(ModelSchema):
    """Schema for order response."""

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer_name",
            "product_name",
            "quantity",
            "price",
            "status",
            "created_at",
            "updated_at",
        ]


class PaginatedOrdersSchema(Schema):
    """Schema for paginated orders response."""

    items: list[OrderSchema]
    total: int
    page: int
    page_size: int
