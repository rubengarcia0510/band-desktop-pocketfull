"""Error response builders.

Per spec §5, every 4xx/5xx response carries
`{"error": {"code": "<code>", "message": "<human readable>"}}`.
The HTTP status and `code` are fixed by the spec; only `message` is free-form.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


def raise_error(status: int, code: str, message: str) -> "HTTPException":
    """Raise an HTTPException carrying the spec-shaped error body."""

    exc = HTTPException(status_code=status, detail={"code": code, "message": message})
    raise exc


def http_exc_to_response(exc: HTTPException, request: Any) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return error_response(exc.status_code, detail["code"], detail["message"])
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": _fallback_code(exc.status_code), "message": str(detail)}},
    )


def _fallback_code(status: int) -> str:
    return {
        400: "malformed_request",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        409: "idempotency_key_reuse",
        422: "validation_failed",
    }.get(status, "error")


__all__ = ["error_response", "raise_error", "http_exc_to_response"]
