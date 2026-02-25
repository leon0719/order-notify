"""Order business logic (service layer)."""

from uuid import UUID

from django.db import transaction

from apps.core.exceptions import AppValidationError, InvalidStateError, NotFoundError
from apps.core.log_config import logger
from apps.orders.models import VALID_TRANSITIONS, Order, OrderStatus
from apps.orders.schemas import OrderCreateSchema, OrderStatusUpdateSchema
from apps.orders.tasks import send_order_notification


def create_order(data: OrderCreateSchema) -> Order:
    """Create a new order and trigger Slack notification."""
    with transaction.atomic():
        order = Order.objects.create(
            customer_name=data.customer_name,
            product_name=data.product_name,
            quantity=data.quantity,
            price=data.price,
        )
        logger.info("Order created: {}", order.order_number)

        transaction.on_commit(lambda: send_order_notification.delay(str(order.id), "created"))

    return order


def get_order(order_id: UUID) -> Order:
    """Get a single order by ID."""
    try:
        return Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        raise NotFoundError(f"Order {order_id} not found") from None


def get_orders(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
) -> tuple[list[Order], int]:
    """Get paginated orders with optional status filter."""
    qs = Order.objects.all()

    if status:
        if status not in OrderStatus.values:
            raise AppValidationError(f"Invalid status: {status}")
        qs = qs.filter(status=status)

    total = qs.count()
    offset = (page - 1) * page_size
    orders = list(qs[offset : offset + page_size])

    return orders, total


def update_order_status(order_id: UUID, data: OrderStatusUpdateSchema) -> Order:
    """Update order status with transition validation."""
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(id=order_id)
        except Order.DoesNotExist:
            raise NotFoundError(f"Order {order_id} not found") from None

        new_status = data.status

        allowed = VALID_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            raise InvalidStateError(
                f"Cannot transition from '{order.status}' to '{new_status}'. Allowed: {allowed}"
            )

        old_status = order.status
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        logger.info("Order {}: {} -> {}", order.order_number, old_status, new_status)

        transaction.on_commit(
            lambda: send_order_notification.delay(str(order.id), "status_updated")
        )

    return order
