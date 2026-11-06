"""Read-only check that a Windows wheelhouse matches reviewed, pinned bytes.

No wheel execution, dependency installation, network access, or private inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*\.whl)$")


class WheelLockError(ValueError):
    """Wheelhouse content does not match the reviewed lock."""


def read_lock(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise WheelLockError("reviewed wheel lock missing or symlinked")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise WheelLockError("reviewed wheel lock unreadable") from exc
    if not lines:
        raise WheelLockError("reviewed wheel lock empty")
    result: dict[str, str] = {}
    seen: set[str] = set()
    for line in lines:
        match = LINE.fullmatch(line)
        if match is None:
            raise WheelLockError("invalid wheel lock entry")
        digest, name = match.groups()
        if name.casefold() in seen:
            raise WheelLockError("duplicate or case-colliding wheel lock entry")
        seen.add(name.casefold())
        result[name] = digest
    if list(result) != sorted(result):
        raise WheelLockError("wheel lock must be sorted")
    return result


def verify(wheelhouse: Path, lock: Path) -> dict[str, object]:
    if wheelhouse.is_symlink() or not wheelhouse.is_dir():
        raise WheelLockError("wheelhouse missing or symlinked")
    expected = read_lock(lock)
    try:
        entries = list(wheelhouse.iterdir())
    except OSError as exc:
        raise WheelLockError("wheelhouse cannot be enumerated") from exc
    names: set[str] = set()
    normalized: set[str] = set()
    for path in entries:
        if path.is_symlink() or not path.is_file():
            raise WheelLockError("wheelhouse contains symlink or non-file")
        if path.name == "WHEELHOUSE.sha256":
            continue
        if path.suffix != ".whl":
            raise WheelLockError("wheelhouse contains an unlisted file")
        if path.name.casefold() in normalized:
            raise WheelLockError("case-colliding wheel filename")
        normalized.add(path.name.casefold())
        names.add(path.name)
    if names != set(expected):
        raise WheelLockError("wheel filename set differs from reviewed lock")
    for name, digest in expected.items():
        try:
            with (wheelhouse / name).open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as exc:
            raise WheelLockError("cannot read reviewed wheel") from exc
        if actual != digest:
            raise WheelLockError("wheel bytes changed: " + name)
    return {
        "status": "PINNED_WINDOWS_WHEELS_VERIFIED",
        "wheel_count": len(expected),
        "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify(args.wheelhouse, args.lock)
    except (WheelLockError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
