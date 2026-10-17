from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = "SOURCE_MANIFEST.sha256"


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    paths = result.stdout.decode("utf-8").rstrip("\0").split("\0")
    return sorted(path for path in paths if path and path != CURRENT)


def render_manifest() -> str:
    lines = []
    for relative in tracked_paths():
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"tracked source is missing or unsafe: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="replace SOURCE_MANIFEST.sha256")
    args = parser.parse_args()
    rendered = render_manifest()
    if args.write:
        (ROOT / CURRENT).write_text(rendered, encoding="utf-8")
        print(f"wrote {CURRENT} with {len(rendered.splitlines())} entries")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
