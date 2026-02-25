"""Loguru logging configuration."""

import sys
from contextvars import ContextVar

from loguru import logger

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


def formatter(record):
    request_id = request_id_var.get()
    record["extra"]["request_id"] = request_id
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[request_id]}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n"
    )


# Remove default logger and add custom one
logger.remove()
logger.add(sys.stderr, format=formatter, level="DEBUG", colorize=True)

__all__ = ["logger", "request_id_var", "user_id_var"]
