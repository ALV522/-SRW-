from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ImportedDocument:
    text_content: str
    metadata: dict = field(default_factory=dict)


class DocumentImporter(Protocol):
    def extract(self, *, content: bytes, filename: str, media_type: str) -> ImportedDocument: ...
