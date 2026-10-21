"""Shared HTTP request helpers for route modules.

These used to live inside ``api/fullworkbench.py``. They are transport-level
utilities with no business meaning, so extracted route modules can depend on
them without depending on the fullworkbench aggregate (which would create an
import cycle as more domains move out under ADR-0002).
"""
from __future__ import annotations

from typing import Any

from starlette.requests import Request

from srw.kernel.errors import V1InvariantError


def body_dict(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise V1InvariantError("request body must be an object")
    return body


async def json_body(request: Request) -> dict[str, Any]:
    try:
        return body_dict(await request.json())
    except V1InvariantError:
        raise
    except Exception as exc:
        raise V1InvariantError("request body must be valid JSON") from exc


def s_field(body: dict[str, Any], key: str, default: str = "", required: bool = False) -> str:
    value = body.get(key, default)
    if not isinstance(value, str):
        raise V1InvariantError(f"{key} must be a string")
    value = value.strip()
    if required and not value:
        raise V1InvariantError(f"{key} is required")
    return value
