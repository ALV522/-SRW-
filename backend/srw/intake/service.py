from __future__ import annotations

from sqlalchemy.orm import Session

from srw.intake.contracts import ImportedDocument
from srw.kernel.errors import V1InvariantError
from srw.kernel.hashing import content_hash
from srw.modules.candidate.commands import add_source
from srw.modules.candidate.models import Source
from srw.runtime.settings import CapabilityManager


def normalize_extracted_text(value: str) -> str:
    """Normalize only transport-level text differences; preserve semantic spacing/content."""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


class CandidateIntakeService:
    def __init__(self, session: Session, *, capability_manager: CapabilityManager | None = None) -> None:
        self.session = session
        self.capability_manager = capability_manager

    def add_text_source(
        self,
        candidate_id: str,
        text_content: str,
        *,
        filename: str = "",
        source_kind: str = "resume",
        media_type: str = "text/plain",
        blob_hash: str | None = None,
        metadata: dict | None = None,
    ) -> Source:
        normalized = normalize_extracted_text(text_content)
        if not normalized:
            raise V1InvariantError("source text is empty after normalization")
        provenance = {
            "filename": filename.strip(),
            "intake_method": "text",
            **(metadata or {}),
        }
        return add_source(
            self.session,
            candidate_id,
            source_kind=source_kind,
            content_hash=content_hash(normalized),
            text_content=normalized,
            media_type=media_type,
            blob_hash=blob_hash,
            metadata=provenance,
        )

    def import_document(
        self,
        candidate_id: str,
        *,
        content: bytes,
        filename: str,
        media_type: str,
        source_kind: str = "resume",
        blob_hash: str | None = None,
        metadata: dict | None = None,
    ) -> Source:
        if media_type.startswith("text/") or filename.lower().endswith((".txt", ".md", ".csv")):
            try:
                decoded = content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise V1InvariantError("text document must be UTF-8") from exc
            return self.add_text_source(
                candidate_id,
                decoded,
                filename=filename,
                source_kind=source_kind,
                media_type=media_type,
                blob_hash=blob_hash,
                metadata={"intake_method": "text_document", **(metadata or {})},
            )

        if self.capability_manager is None:
            raise V1InvariantError("rich document importer is not configured")
        importer = self.capability_manager.resolve("document_importer")
        extracted = importer.extract(content=content, filename=filename, media_type=media_type)
        if not isinstance(extracted, ImportedDocument):
            raise V1InvariantError("document importer returned an invalid result")
        return self.add_text_source(
            candidate_id,
            extracted.text_content,
            filename=filename,
            source_kind=source_kind,
            media_type=media_type,
            blob_hash=blob_hash,
            metadata={
                "intake_method": "rich_document",
                "extractor": extracted.metadata,
                **(metadata or {}),
            },
        )
