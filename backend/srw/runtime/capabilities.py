from __future__ import annotations
from collections.abc import Callable
from typing import Any

class CapabilityRegistry:
    def __init__(self) -> None:
        self._loaders: dict[str, Callable[[], Any]] = {}
        self._instances: dict[str, Any] = {}
    def register(self, name: str, loader: Callable[[], Any]) -> None:
        if not name or name in self._loaders: raise ValueError(f'capability already registered or invalid: {name}')
        self._loaders[name]=loader
    def available(self, name: str) -> bool: return name in self._loaders
    def loaded(self, name: str) -> bool: return name in self._instances
    def names(self) -> tuple[str, ...]: return tuple(sorted(self._loaders))
    def unload(self, name: str) -> None: self._instances.pop(name, None)
    def resolve(self, name: str) -> Any:
        if name in self._instances: return self._instances[name]
        if name not in self._loaders: raise KeyError(name)
        value=self._loaders[name](); self._instances[name]=value; return value
