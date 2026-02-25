"""Order admin configuration."""

from django.contrib import admin

from apps.orders.models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer_name",
        "product_name",
        "quantity",
        "price",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order_number", "customer_name", "product_name")
    readonly_fields = ("id", "order_number", "created_at", "updated_at")
    ordering = ("-created_at",)
