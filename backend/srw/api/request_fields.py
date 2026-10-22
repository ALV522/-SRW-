"""Request-field parsing for the HTTP adapters.

These helpers used to live in ``api/app.py``. They raise
``V1RequestValidationError`` (HTTP 422, ``invalid_request``), which is a different
contract from :mod:`srw.api.http_utils` (``V1InvariantError``, 409). The two are
deliberately kept apart: ``http_utils`` serves routes that report input problems
as invariant conflicts, while these serve routes that follow the schema-validation
envelope.

Bodies are copied verbatim from the original closures-free helpers, including the
``None`` handling and the whitespace strip in :func:`body_string`. Changing those
details would alter status codes on existing routes, so do not "tidy" them.

Moving them here lets newly extracted route modules reuse the exact semantics
instead of copying validation rules that would then drift.
"""
from __future__ import annotations

from typing import Any

from starlette.requests import Request

from srw.kernel.errors import V1RequestValidationError


async def body_dict(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception as exc:  # malformed JSON belongs to the HTTP adapter, not the domain
        raise V1RequestValidationError("request body must be valid JSON") from exc
    if not isinstance(value, dict):
        raise V1RequestValidationError("request body must be an object")
    return value


def body_string(body: dict[str, Any], key: str, *, default: str | None = None,
                required: bool = False) -> str:
    value = body.get(key, default)
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise V1RequestValidationError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise V1RequestValidationError(f"{key} is required")
    return value


def body_choice(body: dict[str, Any], key: str, allowed: set[str], *, default: str) -> str:
    value = body_string(body, key, default=default)
    if value not in allowed:
        raise V1RequestValidationError(f"{key} must be one of: {', '.join(sorted(allowed))}")
    return value


def body_object(body: dict[str, Any], key: str, *,
                default: dict[str, Any] | None = None) -> dict[str, Any]:
    value = body.get(key, default if default is not None else {})
    if not isinstance(value, dict):
        raise V1RequestValidationError(f"{key} must be an object")
    return value


def body_boolean(body: dict[str, Any], key: str, *, default: bool = False,
                 required: bool = False) -> bool:
    if key not in body:
        if required:
            raise V1RequestValidationError(f"{key} is required")
        return default
    value = body[key]
    if not isinstance(value, bool):
        raise V1RequestValidationError(f"{key} must be a boolean")
    return value
