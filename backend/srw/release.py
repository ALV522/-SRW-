from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def get_release_state() -> dict[str, object]:
    resource = files('srw').joinpath('release_state.json')
    value = json.loads(resource.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError('invalid v1 release state')
    return value
