"""Response serialisation helpers shared by the HTTP adapters."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any


def jsonable(value: Any) -> Any:
    """Convert dataclass payloads into plain structures Starlette can encode."""
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
