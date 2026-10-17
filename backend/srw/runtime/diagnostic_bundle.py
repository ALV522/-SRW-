from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

_FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def _safe_payload(diagnostics: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    """Project only non-sensitive diagnostic facts into a support-safe schema."""
    checks = []
    for row in diagnostics.get("checks", []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        status = str(row.get("status") or "")
        detail = row.get("detail")
        # Paths, raw task payloads and arbitrary strings are intentionally excluded.
        if name == "database_integrity":
            detail = str(detail)[:80]
        elif name == "background_tasks" and isinstance(detail, dict):
            detail = {str(k): int(v) for k, v in detail.items() if isinstance(v, int)}
        elif name == "backups" and isinstance(detail, dict):
            detail = {
                "count": int(detail.get("count", 0) or 0),
                "retention": int(detail.get("retention", 0) or 0),
            }
        elif name == "knowledge" and isinstance(detail, list):
            detail = [
                {
                    "name": str(item.get("name") or ""),
                    "available": bool(item.get("available")),
                    "size_bytes": int(item.get("size_bytes", 0) or 0),
                }
                for item in detail
                if isinstance(item, dict)
            ]
        else:
            detail = None
        checks.append({"name": name, "status": status, "detail": detail})

    knowledge = [
        {
            "name": str(item.get("name") or ""),
            "available": bool(item.get("available")),
            "size_bytes": int(item.get("size_bytes", 0) or 0),
        }
        for item in diagnostics.get("knowledge", [])
        if isinstance(item, dict)
    ]
    return {
        "schema": "srw.privacy-safe-diagnostics.v1",
        "release": {
            "version": str(release.get("version") or diagnostics.get("version") or ""),
            "schema_revision": str(
                release.get("schema_revision") or diagnostics.get("schema_revision") or ""
            ),
        },
        "overall_status": str(diagnostics.get("overall_status") or "unknown"),
        "local_only": bool(diagnostics.get("local_only", True)),
        "checks": checks,
        "counts": {
            str(k): int(v)
            for k, v in (diagnostics.get("counts") or {}).items()
            if isinstance(v, int)
        },
        "database": {
            "quick_check": str((diagnostics.get("database") or {}).get("quick_check") or ""),
            "size_bytes": int((diagnostics.get("database") or {}).get("size_bytes", 0) or 0),
        },
        "tasks": {
            "by_status": {
                str(k): int(v)
                for k, v in ((diagnostics.get("tasks") or {}).get("by_status") or {}).items()
                if isinstance(v, int)
            },
            "open": int((diagnostics.get("tasks") or {}).get("open", 0) or 0),
            "total": int((diagnostics.get("tasks") or {}).get("total", 0) or 0),
        },
        "storage": {
            key: int((diagnostics.get("storage") or {}).get(key, 0) or 0)
            for key in ("data_bytes", "blob_files", "blob_bytes", "missing_source_blobs")
        },
        "pending_restore": bool(diagnostics.get("pending_restore", False)),
        "knowledge": knowledge,
        "privacy": {
            "contains_candidate_content": False,
            "contains_source_blobs": False,
            "contains_database_bytes": False,
            "contains_provider_secrets": False,
            "contains_local_paths": False,
        },
    }


def _zip_entry(name: str, raw: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info, raw


def build_privacy_safe_diagnostic_bundle(
    diagnostics: dict[str, Any], release: dict[str, Any]
) -> bytes:
    """Return a deterministic support ZIP with no candidate/source/secret payloads."""
    summary = json.dumps(
        _safe_payload(diagnostics, release),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "schema": "srw.diagnostic-bundle-manifest.v1",
        "files": {
            "summary.json": {
                "sha256": hashlib.sha256(summary).hexdigest(),
                "size_bytes": len(summary),
            }
        },
    }
    manifest_raw = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, raw in (("summary.json", summary), ("manifest.json", manifest_raw)):
            info, payload = _zip_entry(name, raw)
            archive.writestr(info, payload)
    return stream.getvalue()
