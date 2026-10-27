"""Bounded, verified, per-request backup download snapshot (issue #131).

The published backup name is not the payload authority while it can be replaced.
Copy from one opened file descriptor into a private temporary directory first,
then validate and serve only the snapshot. No large ZIP enters Python RAM.
"""
from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path

from starlette.responses import FileResponse

from srw.runtime.backup_truth import MAX_COMPRESSED_BYTES, validate_backup_archive

_CHUNK = 1024 * 1024


def validated_download_snapshot(path: Path, backups_dir: Path) -> tuple[Path, Path]:
    """Return (validated_private_zip, temporary_directory) or raise.

    Caller owns cleanup in *every* exception and response path. Keep the
    file-descriptor bound to one inode even if its published name is replaced.
    """
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    work = Path(tempfile.mkdtemp(prefix=".backup-download-", dir=backups_dir))
    dest = work / "snapshot.zip"
    try:
        # O_NOFOLLOW is not available on Windows. Compare the checked path
        # identity with the opened handle on *both* platforms, and never
        # follow a path that was already a symlink when checked.
        published_stat = os.lstat(path)
        if not stat.S_ISREG(published_stat.st_mode):
            raise ValueError("backup name no longer refers to a regular file")
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            source_stat = os.fstat(source.fileno())
            if not os.path.samestat(published_stat, source_stat):
                raise ValueError("backup name changed while opening")
            if not stat.S_ISREG(source_stat.st_mode):
                raise ValueError("backup source is not a regular file")
            if source_stat.st_size > MAX_COMPRESSED_BYTES:
                raise ValueError("backup source exceeds the compressed size cap")
            total = 0
            with dest.open("xb") as output:
                for chunk in iter(lambda: source.read(_CHUNK), b""):
                    total += len(chunk)
                    if total > MAX_COMPRESSED_BYTES:
                        raise ValueError("backup read exceeds compressed size cap")
                    output.write(chunk)
        # Validate the same immutable-by-ownership copy FileResponse will serve.
        validate_backup_archive(dest)
        return dest, work
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise


class VerifiedBackupFileResponse(FileResponse):
    """FileResponse with deterministic cleanup, including 400/416 Range exits.

    Starlette's FileResponse can return before BackgroundTask on malformed
    Range headers, so cleanup belongs in an ASGI-level try/finally here.
    """
    def __init__(self, path: Path, directory: Path, *, filename: str, release_slot):
        self._backup_work_directory = directory
        self._release_slot = release_slot
        super().__init__(path, filename=filename, headers={"Cache-Control": "no-store"})

    async def __call__(self, scope, receive, send) -> None:
        # Starlette's pathsend hands the private filename to the ASGI server.
        # That server may open it *after* this coroutine returns, when finally
        # has already removed our snapshot. Force the ordinary awaited file
        # stream instead; preserve every unrelated ASGI extension.
        if "http.response.pathsend" in scope.get("extensions", {}):
            scope = dict(scope)
            scope["extensions"] = {
                name: spec for name, spec in scope["extensions"].items()
                if name != "http.response.pathsend"
            }
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                shutil.rmtree(self._backup_work_directory, ignore_errors=True)
            finally:
                self._release_slot()
