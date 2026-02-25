"""Custom middleware for the application."""

import re
import uuid

from apps.core.log_config import request_id_var, user_id_var

_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


class RequestContextMiddleware:
    """Middleware to add request context for structured logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_id = request.headers.get("X-Request-ID", "")
        if raw_id and _VALID_REQUEST_ID.match(raw_id):
            request_id = raw_id
        else:
            request_id = str(uuid.uuid4())[:8]
        request_id_token = request_id_var.set(request_id)

        if hasattr(request, "user") and request.user.is_authenticated:
            user_id_token = user_id_var.set(str(request.user.id))
        else:
            user_id_token = user_id_var.set("-")

        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(request_id_token)
            user_id_var.reset(user_id_token)
