"""Failures a service reports; `http_errors` turns each into one HTTP status."""

from collections.abc import Mapping
from typing import Any


class ServiceError(Exception):
    """Base class. The message is safe to return to the caller."""


class Unauthorized(ServiceError):
    pass


class Forbidden(ServiceError):
    pass


class NotFound(ServiceError):
    pass


class Conflict(ServiceError):
    """`details` carries what the caller needs to recover, e.g. the id of what already exists."""

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


class Unprocessable(ServiceError):
    pass


class RateLimited(ServiceError):
    def __init__(self, message: str, retry_after_s: int) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s
