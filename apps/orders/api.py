"""Order API endpoints."""

from uuid import UUID

from ninja import Query, Router

from apps.orders import services
from apps.orders.schemas import (
    OrderCreateSchema,
    OrderSchema,
    OrderStatusUpdateSchema,
    PaginatedOrdersSchema,
)

router = Router()


@router.post("/", response={201: OrderSchema})
def create_order(request, data: OrderCreateSchema):
    """Create a new order and trigger async Slack notification."""
    order = services.create_order(data)
    return 201, order


@router.get("/", response={200: PaginatedOrdersSchema})
def list_orders(
    request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
):
    """List orders with pagination and optional status filter."""
    orders, total = services.get_orders(page=page, page_size=page_size, status=status)
    return 200, {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{order_id}/", response={200: OrderSchema})
def get_order(request, order_id: UUID):
    """Get a single order by ID."""
    order = services.get_order(order_id)
    return 200, order


@router.patch("/{order_id}/status/", response={200: OrderSchema})
def update_order_status(request, order_id: UUID, data: OrderStatusUpdateSchema):
    """Update order status and trigger async Slack notification."""
    order = services.update_order_status(order_id, data)
    return 200, order
