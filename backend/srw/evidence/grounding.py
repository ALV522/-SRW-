from __future__ import annotations

import json
from typing import Any

from srw.modules.candidate.models import Source


def _metadata(source: Source) -> dict[str, Any]:
    try:
        value = json.loads(source.metadata_json or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def enrich_source_locator(source: Source, locator: dict) -> dict | None:
    if not isinstance(locator, dict):
        return None
    quote = str(locator.get("quote") or "").strip()
    if not quote:
        return None
    text = source.text_content
    raw_start = locator.get("char_start")
    if isinstance(raw_start, int) and raw_start >= 0 and text[raw_start:raw_start + len(quote)] == quote:
        start = raw_start
    else:
        occurrences: list[int] = []
        cursor = 0
        while True:
            found = text.find(quote, cursor)
            if found < 0:
                break
            occurrences.append(found)
            cursor = found + max(1, len(quote))
        if not occurrences:
            return None
        if len(occurrences) == 1:
            start = occurrences[0]
        else:
            # A provider may supply a page hint. Use it only when page metadata narrows
            # the repeated quote to exactly one occurrence; otherwise reject ambiguity.
            page_hint = locator.get("page")
            meta = _metadata(source)
            extractor = meta.get("extractor") if isinstance(meta.get("extractor"), dict) else {}
            blocks = extractor.get("grounding_blocks") if isinstance(extractor, dict) else None
            candidates: list[int] = []
            if isinstance(page_hint, int) and isinstance(blocks, list):
                page_ranges = [(b.get("char_start"), b.get("char_end")) for b in blocks if isinstance(b, dict) and b.get("page") == page_hint]
                for pos in occurrences:
                    if any(isinstance(a, int) and isinstance(b, int) and a <= pos < b for a, b in page_ranges):
                        candidates.append(pos)
            if len(candidates) != 1:
                return None
            start = candidates[0]
    end = start + len(quote)
    out = dict(locator)
    out["quote"] = text[start:end]
    out["char_start"] = start
    out["char_end"] = end

    meta = _metadata(source)
    extractor = meta.get("extractor") if isinstance(meta.get("extractor"), dict) else {}
    blocks = extractor.get("grounding_blocks") if isinstance(extractor, dict) else None
    if isinstance(blocks, list):
        best = None
        best_overlap = 0
        for block in blocks:
            if not isinstance(block, dict):
                continue
            bs, be = block.get("char_start"), block.get("char_end")
            if not isinstance(bs, int) or not isinstance(be, int):
                continue
            overlap = max(0, min(end, be) - max(start, bs))
            if overlap > best_overlap:
                best, best_overlap = block, overlap
        if best and best_overlap:
            if isinstance(best.get("page"), int): out["page"] = best["page"]
            if isinstance(best.get("bbox"), list) and len(best["bbox"]) == 4: out["bbox"] = best["bbox"]
            if isinstance(best.get("block_index"), int): out["block_index"] = best["block_index"]
    out["grounding_version"] = "srw.source_locator.v1"
    return out
