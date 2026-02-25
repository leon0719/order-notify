"""Tests for Celery order notification tasks."""

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from apps.orders.models import Order
from apps.orders.tasks import SLACK_API_URL, send_order_notification


@pytest.mark.django_db
class TestSendOrderNotification:
    @patch("apps.orders.tasks.settings")
    def test_skip_when_slack_disabled(self, mock_settings, sample_order):
        """Task should skip when SLACK_ENABLED is False."""
        mock_settings.SLACK_ENABLED = False
        result = send_order_notification(str(sample_order.id), "created")
        assert result["status"] == "skipped"
        assert result["reason"] == "slack_disabled"

    @patch("apps.orders.tasks.settings")
    def test_skip_when_no_slack_config(self, mock_settings, sample_order):
        """Task should skip when SLACK_BOT_TOKEN or SLACK_CHANNEL is empty."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = ""
        mock_settings.SLACK_CHANNEL = ""
        result = send_order_notification(str(sample_order.id), "created")
        assert result["status"] == "skipped"
        assert result["reason"] == "no_slack_config"

    @patch("apps.orders.tasks.settings")
    def test_order_not_found(self, mock_settings):
        """Task should return error when order doesn't exist."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = "xoxb-test-token"
        mock_settings.SLACK_CHANNEL = "#test"
        result = send_order_notification(str(uuid4()), "created")
        assert result["status"] == "error"
        assert result["reason"] == "order_not_found"

    @patch("apps.orders.tasks.httpx.Client")
    @patch("apps.orders.tasks.settings")
    def test_send_notification_success(self, mock_settings, mock_client_cls, sample_order):
        """Task should send notification to Slack successfully."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = "xoxb-test-token"
        mock_settings.SLACK_CHANNEL = "#orders"

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = send_order_notification(str(sample_order.id), "created")

        assert result["status"] == "sent"
        assert result["order_number"] == sample_order.order_number
        # Verify called with Slack API URL and Bearer token
        call_args = mock_client.post.call_args
        assert call_args[0][0] == SLACK_API_URL
        assert call_args[1]["headers"]["Authorization"] == "Bearer xoxb-test-token"
        assert call_args[1]["json"]["channel"] == "#orders"

    @patch("apps.orders.tasks.httpx.Client")
    @patch("apps.orders.tasks.settings")
    def test_send_notification_for_status_update(self, mock_settings, mock_client_cls, db):
        """Task should send notification for status update events."""
        mock_settings.SLACK_ENABLED = True
        mock_settings.SLACK_BOT_TOKEN = "xoxb-test-token"
        mock_settings.SLACK_CHANNEL = "#orders"

        order = Order.objects.create(
            customer_name="Test",
            product_name="Product",
            quantity=1,
            price=Decimal("25.00"),
            status="confirmed",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = send_order_notification(str(order.id), "status_updated")

        assert result["status"] == "sent"
        # Verify Block Kit payload with channel
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["channel"] == "#orders"
        assert "attachments" in payload
