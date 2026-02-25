"""Custom exceptions for the application."""


class AppError(Exception):
    """Base exception for application errors."""

    def __init__(self, message: str, code: str = "APP_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, code="NOT_FOUND")


class AppValidationError(AppError):
    """Validation failed."""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, code="VALIDATION_ERROR")


class InvalidStateError(AppError):
    """Invalid state transition."""

    def __init__(self, message: str = "Invalid state transition"):
        super().__init__(message, code="INVALID_STATE")
