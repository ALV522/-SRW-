from __future__ import annotations

import shutil
from pathlib import Path


def cleanup_stale_backup_artifacts(data_dir: str | Path) -> dict[str, int]:
    """Remove only SRW-owned interrupted backup/restore staging artifacts.

    Deliberately does not remove valid .zip backups or arbitrary user files.
    """
    root = Path(data_dir)
    backup_dir = root / "backups"
    removed_dirs = 0
    removed_files = 0

    for pattern in (".backup-snapshot-*", ".restore-staging-*"):
        for path in root.glob(pattern):
            if path.is_symlink() or path.is_file():
                try:
                    path.unlink()
                    removed_files += 1
                except FileNotFoundError:
                    pass
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                if not path.exists():
                    removed_dirs += 1

    if backup_dir.is_dir():
        for pattern in (".backup-import-*", "*.partial", ".restore-import-*"):
            for path in backup_dir.glob(pattern):
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path, ignore_errors=True)
                    if not path.exists():
                        removed_dirs += 1
                else:
                    try:
                        path.unlink()
                        removed_files += 1
                    except FileNotFoundError:
                        pass

    return {"directories": removed_dirs, "files": removed_files}
