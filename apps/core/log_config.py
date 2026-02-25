"""Loguru logging configuration."""

import sys

from loguru import logger


def formatter(record):
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[request_id]}</cyan> | "
        "<cyan>{extra[user_id]}</cyan> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>\n"
    )


# Remove default logger and add custom one
logger.remove()
logger.add(
    sys.stderr,
    format=formatter,
    level="DEBUG",
    colorize=True,
    enqueue=True,
    backtrace=True,
    diagnose=False,
)

# Configure default extra values for when contextualize() is not active
logger = logger.bind(request_id="-", user_id="-")

__all__ = ["logger"]
