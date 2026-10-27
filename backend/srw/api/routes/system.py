"""Backup, restore-scheduling and diagnostics routes (ADR-0002 R2, fourth slice).

These are the operator's data-safety surfaces: take a backup, inspect it,
download it, schedule a restore, cancel a pending restore, and export a
privacy-safe diagnostic bundle. Behaviour is intentionally identical to the code
that lived inside ``install_full_workbench_routes``.

Deliberate boundary: scheduling a restore only validates the archive manifest and
writes ``pending_restore.json``. The actual restore runs at startup, before
SQLite is opened, so this module never touches live data. That is also why these
routes matter for the Windows/Portable acceptance work (#42): they are the API
half of the recovery contract, not a substitute for on-device acceptance.
"""
from __future__ import annotations

import json
import threading
import shutil
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError
from srw.modules.fullworkbench import create_backup, diagnostics
from srw.release import get_release_state
from srw.runtime.backup_truth import BackupTruthError, validate_backup_archive
from srw.runtime.backup_download import (
    VerifiedBackupFileResponse, validated_download_snapshot,
)
from srw.runtime.db.schema import V1_SCHEMA_REVISION
from srw.runtime.diagnostic_bundle import build_privacy_safe_diagnostic_bundle


def system_routes(*, factory, data_dir: Path, knowledge_dir: Path,
                  database_path: Path, frontend_dist: Path | None) -> list[Route]:
    """Bind the system endpoints to one Core workspace."""

    async def backups(_r: Request) -> JSONResponse:
        try:
            path = create_backup(data_dir, database_path)
        except BackupTruthError as exc:
            # Surface unsupported atomic filesystems as an actionable
            # invariant error, rather than an unhandled HTTP 500.
            raise V1InvariantError(str(exc)) from exc
        return JSONResponse({"filename": path.name, "size_bytes": path.stat().st_size})

    def is_published_backup_name(name: str) -> bool:
        # Preserve legacy named ZIPs; dot-prefixed staging/private files
        # are never operator-visible backup archives.
        return bool(name) and not name.startswith(".") and name.endswith(".zip") and Path(name).name == name

    async def backup_list(_r: Request) -> JSONResponse:
        root = data_dir / "backups"
        root.mkdir(parents=True, exist_ok=True)
        return JSONResponse({"backups": [
            {"filename": p.name, "size_bytes": p.stat().st_size}
            for p in sorted(root.glob("*.zip"), reverse=True)
            if is_published_backup_name(p.name) and p.is_file() and not p.is_symlink()
        ]})

    # Each validated snapshot can occupy up to 512 MiB on disk; only one
    # download at a time prevents unbounded workspace disk amplification.
    download_slot = threading.BoundedSemaphore(1)

    async def backup_download(request: Request) -> Response:
        name = Path(request.path_params["filename"]).name
        path = data_dir / "backups" / name
        if not is_published_backup_name(name) or not path.is_file() or path.is_symlink():
            raise HTTPException(404)
        if not download_slot.acquire(blocking=False):
            raise V1InvariantError("backup download already in progress; retry after it finishes")
        snapshot = temporary = None
        try:
            # Handle a possible name replacement by copying from one opened FD;
            # neither validation nor HTTP serving reopens the published ZIP.
            snapshot, temporary = await run_in_threadpool(
                validated_download_snapshot, path, path.parent,
            )
            try:
                return VerifiedBackupFileResponse(
                    snapshot, temporary, filename=name, release_slot=download_slot.release,
                )
            except BaseException:
                shutil.rmtree(temporary, ignore_errors=True)
                snapshot = None
                raise
        except FileNotFoundError as exc:
            raise HTTPException(404) from exc
        except (OSError, ValueError, BackupTruthError) as exc:
            raise V1InvariantError("backup download rejected: invalid or unstable archive") from exc
        finally:
            # On success, the response owns the slot until the last ASGI send.
            # On setup failure, no response exists to release it.
            if snapshot is None:
                download_slot.release()


    async def schedule_restore(request: Request) -> JSONResponse:
        name = Path(request.path_params["filename"]).name
        path = data_dir / "backups" / name
        if not is_published_backup_name(name) or not path.is_file() or path.is_symlink():
            raise HTTPException(404)
        try:
            # Share startup's manifest/member validation before accepting a plan.
            truth = validate_backup_archive(path)
            schema_revision = truth["schema_revision"]
            current = int(V1_SCHEMA_REVISION.split("_")[-1])
            allowed = {f"v1_{i:04d}" for i in range(1, current + 1)}
            if schema_revision not in allowed:
                raise V1InvariantError(f"backup schema is not compatible: {schema_revision}")
        except BackupTruthError as exc:
            raise V1InvariantError(str(exc)) from exc
        marker = data_dir / "pending_restore.json"
        digest = truth["archive_sha256"]
        marker.write_text(
            json.dumps({"backup": name, "sha256": digest, "schema_revision": schema_revision},
                       ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return JSONResponse({"scheduled": True, "filename": name, "sha256": digest,
                             "schema_revision": schema_revision, "restart_required": True})

    async def cancel_restore(_r: Request) -> JSONResponse:
        marker = data_dir / "pending_restore.json"
        if marker.exists():
            marker.unlink()
        return JSONResponse({"scheduled": False})

    async def diag(_r: Request) -> JSONResponse:
        with factory() as session:
            release = get_release_state()
            return JSONResponse(diagnostics(
                session, data_dir=data_dir, knowledge_dir=knowledge_dir,
                database_path=database_path, frontend_dist=frontend_dist,
                version=release["version"], schema_revision=V1_SCHEMA_REVISION,
            ))

    async def diag_export(_r: Request) -> Response:
        with factory() as session:
            release = get_release_state()
            payload = diagnostics(
                session, data_dir=data_dir, knowledge_dir=knowledge_dir,
                database_path=database_path, frontend_dist=frontend_dist,
                version=release["version"], schema_revision=V1_SCHEMA_REVISION,
            )
            raw = build_privacy_safe_diagnostic_bundle(payload, release)
        headers = {
            "Content-Disposition": f'attachment; filename="srw-diagnostics-{release["version"]}.zip"',
            "Cache-Control": "no-store",
        }
        return Response(raw, media_type="application/zip", headers=headers)

    return [
        Route("/api/v1/system/backups", backups, methods=["POST"]),
        Route("/api/v1/system/backups", backup_list, methods=["GET"]),
        Route("/api/v1/system/backups/{filename:str}", backup_download, methods=["GET"]),
        Route("/api/v1/system/backups/{filename:str}/restore", schedule_restore, methods=["POST"]),
        Route("/api/v1/system/restore/cancel", cancel_restore, methods=["POST"]),
        Route("/api/v1/system/diagnostics", diag, methods=["GET"]),
        Route("/api/v1/system/diagnostics/export", diag_export, methods=["GET"]),
    ]
