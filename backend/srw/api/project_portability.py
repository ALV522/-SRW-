from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from srw.kernel.errors import V1InvariantError
from srw.modules.project_portability.service import (
    MAX_PACKAGE_BYTES,
    export_project_package,
    import_project_package,
    inspect_project_package,
)

CHUNK = 1024 * 1024


async def _request_to_temp(request: Request) -> tuple[Path, str, int]:
    fd, raw = tempfile.mkstemp(prefix="srw-project-package-http-", suffix=".zip")
    os.close(fd)
    path = Path(raw)
    h = hashlib.sha256()
    total = 0
    try:
        with path.open("wb") as f:
            async for chunk in request.stream():
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_PACKAGE_BYTES:
                    raise V1InvariantError("project package exceeds 512 MB limit")
                h.update(chunk)
                f.write(chunk)
        if total <= 0:
            raise V1InvariantError("project package body is empty")
        return path, h.hexdigest(), total
    except Exception:
        path.unlink(missing_ok=True)
        raise


def install_project_portability_routes(app, factory, *, data_dir: Path):
    async def export_package(request: Request):
        project_id = request.path_params["project_id"]
        fd, raw = tempfile.mkstemp(prefix="srw-project-export-", suffix=".srwproject.zip")
        os.close(fd)
        path = Path(raw)
        try:
            with factory() as session:
                manifest = export_project_package(session, project_id, data_dir=data_dir, output_path=path)
            title = str(manifest.get("project_title") or "project").replace('"', "").replace("\r", " ").replace("\n", " ")
            filename = f"SRW_Project_{project_id}.srwproject.zip"
            return FileResponse(
                path,
                media_type="application/zip",
                filename=filename,
                headers={
                    "X-SRW-Project-Package-SHA256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "X-SRW-Contains-Personal-Data": "true",
                    "X-SRW-Project-Title": title.encode("ascii", "ignore").decode("ascii")[:120],
                    "Cache-Control": "no-store",
                },
                background=BackgroundTask(path.unlink, missing_ok=True),
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise

    async def preview_import(request: Request):
        path, digest, size = await _request_to_temp(request)
        try:
            preview = inspect_project_package(path)
            preview["sha256"] = digest
            preview["size_bytes"] = size
            preview["warning"] = "项目包包含候选人个人数据和招聘业务记录；仅在受控环境中传输和导入。"
            preview["commit_requires_exact_digest"] = True
            return JSONResponse(preview)
        finally:
            path.unlink(missing_ok=True)

    async def commit_import(request: Request):
        expected = request.headers.get("X-SRW-Package-SHA256", "").strip().lower()
        if not expected:
            raise V1InvariantError("X-SRW-Package-SHA256 is required; preview the exact package before import")
        path, actual, size = await _request_to_temp(request)
        try:
            if actual != expected:
                raise V1InvariantError("project package digest mismatch; preview the exact package again before import")
            # Re-run all ZIP/path/blob/schema checks on the exact bytes at commit time.
            inspect_project_package(path)
            with factory.begin() as session:
                result = import_project_package(session, path, data_dir=data_dir, actor=request.headers.get("X-SRW-Actor", "human") or "human")
            result["size_bytes"] = size
            result["contains_personal_data"] = True
            return JSONResponse(result)
        finally:
            path.unlink(missing_ok=True)

    app.routes.extend([
        Route("/api/v1/projects/{project_id:str}/export-package", export_package, methods=["GET"]),
        Route("/api/v1/projects/import-package/preview", preview_import, methods=["POST"]),
        Route("/api/v1/projects/import-package", commit_import, methods=["POST"]),
    ])
