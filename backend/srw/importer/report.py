from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class ImportWarning:
    scope: str
    code: str
    message: str


@dataclass(slots=True)
class ImportReport:
    status: str = "pending"
    source_sha256_before: str = ""
    source_sha256_after: str = ""
    source_counts: dict[str, int] = field(default_factory=dict)
    mapped_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[ImportWarning] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
