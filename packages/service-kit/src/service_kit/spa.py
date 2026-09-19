"""Serves a built single-page app next to the API (ARCHITECTURE §20, D2).

The node serves the purchaser app and the hub the supplier app, each from its own origin.
Every path that is not an API path and not a built file gets `index.html`, so the app's own
router handles deep links and reloads.
"""

from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


class MissingBuild(RuntimeError):
    """The configured UI directory holds no build: run `make ui-build` first."""


def security_headers(connect_to: Sequence[str]) -> dict[str, str]:
    """Scripts and styles only from this origin; API calls only here and to `connect_to`."""
    connect = " ".join(["'self'", *connect_to])
    policy = (
        "default-src 'self'; "
        "script-src 'self'; "
        # Radix positions popovers with inline styles.
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        f"connect-src {connect}; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return {
        "Content-Security-Policy": policy,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
    }


def mount_spa(app: FastAPI, directory: Path, *, connect_to: Sequence[str] = ()) -> None:
    """Call after every API router is included: the fallback route catches what is left."""
    index = directory / "index.html"
    if not index.is_file():
        raise MissingBuild(f"no index.html in {directory}; run `make ui-build`")
    headers = security_headers(connect_to)
    root = directory.resolve()
    if (directory / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=directory / "assets"), name="spa-assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate, headers=headers)
        return FileResponse(index, headers=headers)
