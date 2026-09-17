"""Maps service errors to HTTP responses."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from service_kit.errors import (
    Conflict,
    Forbidden,
    NotFound,
    RateLimited,
    ServiceError,
    Unauthorized,
    Unprocessable,
)

_STATUS: dict[type[ServiceError], int] = {
    Unauthorized: status.HTTP_401_UNAUTHORIZED,
    Forbidden: status.HTTP_403_FORBIDDEN,
    NotFound: status.HTTP_404_NOT_FOUND,
    Conflict: status.HTTP_409_CONFLICT,
    Unprocessable: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RateLimited: status.HTTP_429_TOO_MANY_REQUESTS,
}


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _handle)  # type: ignore[arg-type]


def _handle(_: Request, error: ServiceError) -> JSONResponse:
    body: dict[str, object] = {"detail": str(error)}
    headers: dict[str, str] = {}
    if isinstance(error, Conflict):
        body["code"] = error.code
    if isinstance(error, Unauthorized):
        headers["WWW-Authenticate"] = "Bearer"
    if isinstance(error, RateLimited):
        headers["Retry-After"] = str(error.retry_after_s)
    return JSONResponse(body, status_code=_STATUS[type(error)], headers=headers)
