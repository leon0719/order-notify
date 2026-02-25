"""Celery tasks for order notifications."""

import httpx
from celery import shared_task
from django.conf import settings

from apps.core.log_config import logger
from apps.orders.models import Order

SLACK_API_URL = "https://slack.com/api/chat.postMessage"

STATUS_COLORS = {
    "pending": "#FFA500",  # Orange
    "confirmed": "#2196F3",  # Blue
    "shipped": "#9C27B0",  # Purple
    "delivered": "#4CAF50",  # Green
    "cancelled": "#F44336",  # Red
}

STATUS_EMOJIS = {
    "pending": ":hourglass_flowing_sand:",
    "confirmed": ":white_check_mark:",
    "shipped": ":package:",
    "delivered": ":tada:",
    "cancelled": ":x:",
}


def _build_slack_payload(order, event: str, channel: str) -> dict:
    """Build Slack chat.postMessage payload with Block Kit."""
    status = order.status
    color = STATUS_COLORS.get(status, "#757575")
    emoji = STATUS_EMOJIS.get(status, ":memo:")

    if event == "created":
        title = f"{emoji} New Order Created"
    else:
        title = f"{emoji} Order Status Updated"

    text = f"{title}: {order.order_number} - {order.customer_name} ({order.status.upper()})"

    return {
        "channel": channel,
        "text": text,
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": title},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Order Number:*\n{order.order_number}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Customer:*\n{order.customer_name}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Product:*\n{order.product_name}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Quantity:*\n{order.quantity}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Price:*\n${order.price}",
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Status:*\n{order.status.upper()}",
                            },
                        ],
                    },
                ],
            }
        ],
    }


@shared_task(
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    ignore_result=True,
    reject_on_worker_lost=True,
)
def send_order_notification(order_id: str, event: str):
    """Send order notification to Slack via chat.postMessage API."""
    slack_enabled = getattr(settings, "SLACK_ENABLED", False)
    if not slack_enabled:
        logger.info("Slack disabled, skipping notification for order {}", order_id)
        return {"status": "skipped", "reason": "slack_disabled"}

    slack_bot_token = getattr(settings, "SLACK_BOT_TOKEN", "")
    slack_channel = getattr(settings, "SLACK_CHANNEL", "")
    if not slack_bot_token or not slack_channel:
        logger.warning("SLACK_BOT_TOKEN or SLACK_CHANNEL not configured")
        return {"status": "skipped", "reason": "no_slack_config"}

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order {} not found for notification", order_id)
        return {"status": "error", "reason": "order_not_found"}

    payload = _build_slack_payload(order, event, slack_channel)
    headers = {
        "Authorization": f"Bearer {slack_bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    timeout = httpx.Timeout(10.0, connect=5.0)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(SLACK_API_URL, headers=headers, json=payload)
        response.raise_for_status()

        data = response.json()
        if not data.get("ok"):
            error_code = data.get("error", "unknown")
            non_retriable = {"invalid_auth", "channel_not_found", "not_in_channel", "is_archived"}
            if error_code in non_retriable:
                logger.error(
                    "Slack non-retriable error for order {}: {}", order.order_number, error_code
                )
                return {"status": "error", "reason": error_code}
            raise httpx.HTTPError(f"Slack API error: {error_code}")

    logger.info("Slack notification sent for order {} ({})", order.order_number, event)
    return {"status": "sent", "order_number": order.order_number}
