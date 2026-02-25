"""URL configuration for the project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import DatabaseError, IntegrityError
from django.http import HttpRequest
from django.urls import path
from ninja import NinjaAPI

from apps.core.api import router as core_router
from apps.core.exceptions import AppValidationError, InvalidStateError, NotFoundError
from apps.core.log_config import logger
from apps.orders.api import router as orders_router

api = NinjaAPI(
    title="Order Notify API",
    version="1.0.0",
    description="Django Ninja + Celery Order Notification System",
)


@api.exception_handler(NotFoundError)
def handle_not_found(request: HttpRequest, exc: NotFoundError):
    return api.create_response(request, {"error": exc.message, "code": exc.code}, status=404)


@api.exception_handler(AppValidationError)
def handle_validation_error(request: HttpRequest, exc: AppValidationError):
    return api.create_response(request, {"error": exc.message, "code": exc.code}, status=400)


@api.exception_handler(InvalidStateError)
def handle_invalid_state(request: HttpRequest, exc: InvalidStateError):
    return api.create_response(request, {"error": exc.message, "code": exc.code}, status=409)


@api.exception_handler(IntegrityError)
def handle_integrity_error(request: HttpRequest, exc: IntegrityError):
    logger.warning("Integrity error: {}", exc)
    return api.create_response(
        request,
        {"error": "Resource already exists or constraint violated", "code": "INTEGRITY_ERROR"},
        status=400,
    )


@api.exception_handler(DatabaseError)
def handle_database_error(request: HttpRequest, exc: DatabaseError):
    logger.exception("Database error: {}", exc)
    return api.create_response(
        request,
        {"error": "Database error occurred", "code": "DATABASE_ERROR"},
        status=500,
    )


api.add_router("", core_router, tags=["health"])
api.add_router("/orders", orders_router, tags=["orders"])

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    *static(settings.STATIC_URL, document_root=settings.STATIC_ROOT),
]
