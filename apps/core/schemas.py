"""Core Pydantic schemas."""

from ninja import Schema


class HealthSchema(Schema):
    """Schema for health check response."""

    status: str
    database: str
    redis: str
    rabbitmq: str
