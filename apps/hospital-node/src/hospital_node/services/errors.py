"""Failures a service reports; the API layer turns each into one HTTP status."""


class ServiceError(Exception):
    """Base class. The message is safe to return to the caller."""


class Unauthorized(ServiceError):
    pass


class Forbidden(ServiceError):
    pass


class NotFound(ServiceError):
    pass


class Conflict(ServiceError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Unprocessable(ServiceError):
    pass


class RateLimited(ServiceError):
    def __init__(self, message: str, retry_after_s: int) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s
