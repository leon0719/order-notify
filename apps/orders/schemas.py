"""Order Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema
from pydantic import Field


class OrderCreateSchema(Schema):
    """Schema for creating an order."""

    customer_name: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)
    price: Decimal = Field(ge=0, decimal_places=2)


class OrderStatusUpdateSchema(Schema):
    """Schema for updating order status."""

    status: str = Field(pattern=r"^(pending|confirmed|shipped|delivered|cancelled)$")


class OrderSchema(Schema):
    """Schema for order response."""

    id: UUID
    order_number: str
    customer_name: str
    product_name: str
    quantity: int
    price: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


class PaginatedOrdersSchema(Schema):
    """Schema for paginated orders response."""

    items: list[OrderSchema]
    total: int
    page: int
    page_size: int
