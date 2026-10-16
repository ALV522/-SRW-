from __future__ import annotations

from io import BytesIO
from pathlib import Path
import importlib

from srw.intake.contracts import ImportedDocument


class OptionalRichDocumentImporter:
    """Optional rich-document extractor. Heavy libraries are imported per requested format."""

    def extract(self, *, content: bytes, filename: str, media_type: str) -> ImportedDocument:
        suffix = Path(filename).suffix.lower()
        if media_type == "application/pdf" or suffix == ".pdf":
            return self._pdf(content)
        if media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or suffix == ".docx":
            return self._docx(content)
        if media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" or suffix == ".xlsx":
            return self._xlsx(content)
        raise ValueError(f"unsupported rich document type: {media_type or suffix}")

    @staticmethod
    def _pdf(content: bytes) -> ImportedDocument:
        try:
            fitz = importlib.import_module("fitz")
        except ImportError as exc:
            raise RuntimeError("PyMuPDF is required for PDF intake") from exc
        parts: list[str] = []
        blocks_meta: list[dict] = []
        empty_pages: list[int] = []
        cursor = 0
        with fitz.open(stream=content, filetype="pdf") as document:
            for number, page in enumerate(document, 1):
                blocks = page.get_text("blocks", sort=True)
                usable = [block for block in blocks if len(block) >= 5 and str(block[4] or "").strip()]
                if not usable:
                    empty_pages.append(number)
                    continue
                if parts:
                    sep = "\n\n"
                    parts.append(sep); cursor += len(sep)
                prefix = f"[Page {number}]\n"
                parts.append(prefix); cursor += len(prefix)
                for block_index, block in enumerate(usable):
                    if block_index:
                        parts.append("\n"); cursor += 1
                    block_text = str(block[4]).strip()
                    start = cursor
                    parts.append(block_text); cursor += len(block_text)
                    bbox = [round(float(block[i]), 2) for i in range(4)]
                    blocks_meta.append({"page": number, "block_index": block_index, "bbox": bbox, "char_start": start, "char_end": cursor})
            return ImportedDocument(
                text_content="".join(parts),
                metadata={"format": "pdf", "pages": len(document), "empty_pages": empty_pages, "grounding_blocks": blocks_meta, "grounding_version": "srw.pdf.blocks.v1"},
            )

    @staticmethod
    def _docx(content: bytes) -> ImportedDocument:
        try:
            document_class = importlib.import_module("docx").Document
        except ImportError as exc:
            raise RuntimeError("python-docx is required for DOCX intake") from exc
        document = document_class(BytesIO(content))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        table_lines = []
        cells = 0
        for table in document.tables:
            for row in table.rows:
                values = [cell.text.strip() for cell in row.cells]
                cells += sum(bool(v) for v in values)
                if any(values):
                    table_lines.append("\t".join(values))
        return ImportedDocument(
            text_content="\n".join([*paragraphs, *table_lines]),
            metadata={"format": "docx", "paragraphs": len(paragraphs), "table_cells": cells},
        )

    @staticmethod
    def _xlsx(content: bytes) -> ImportedDocument:
        try:
            openpyxl = importlib.import_module("openpyxl")
        except ImportError as exc:
            raise RuntimeError("openpyxl is required for XLSX intake") from exc
        workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
        lines: list[str] = []
        cells = 0
        try:
            for sheet in workbook.worksheets:
                lines.append(f"[{sheet.title}]")
                for row in sheet.iter_rows(values_only=True):
                    values = ["" if value is None else str(value) for value in row]
                    cells += sum(bool(value) for value in values)
                    if any(values):
                        lines.append("\t".join(values))
        finally:
            workbook.close()
        return ImportedDocument(text_content="\n".join(lines), metadata={"format": "xlsx", "cells": cells})


def build_rich_document_importer() -> OptionalRichDocumentImporter:
    return OptionalRichDocumentImporter()
