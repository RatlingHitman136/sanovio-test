"""Maps service errors to HTTP responses."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

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


class ErrorBody(BaseModel):
    """Every refusal has this shape; a 409 adds its `code` and may add ids to act on."""

    model_config = ConfigDict(extra="allow")

    detail: str
    code: str | None = Field(
        default=None, description="Why a 409 happened, e.g. VERSION_CONFLICT or ASSESSMENT_OPEN."
    )


def _documented(description: str) -> dict[str, Any]:
    return {"model": ErrorBody, "description": description}


# Attached to each service's API router, so OpenAPI shows what a client must handle.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: _documented("Missing, expired or revoked token"),
    status.HTTP_403_FORBIDDEN: _documented("The caller's role may not do this"),
    status.HTTP_404_NOT_FOUND: _documented("Not found, or another tenant's"),
    status.HTTP_409_CONFLICT: _documented("A state or version conflict; see `code`"),
}


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _handle)  # type: ignore[arg-type]


def _handle(_: Request, error: ServiceError) -> JSONResponse:
    body: dict[str, object] = {"detail": str(error)}
    headers: dict[str, str] = {}
    if isinstance(error, Conflict):
        body["code"] = error.code
        body |= error.details
    if isinstance(error, Unauthorized):
        headers["WWW-Authenticate"] = "Bearer"
    if isinstance(error, RateLimited):
        headers["Retry-After"] = str(error.retry_after_s)
    return JSONResponse(body, status_code=_STATUS[type(error)], headers=headers)
