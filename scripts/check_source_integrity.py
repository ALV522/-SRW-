"""Validate current source bytes while retaining the immutable C08 inventory."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CURRENT = 'SOURCE_MANIFEST.sha256'
HISTORICAL = 'SOURCE_RECOVERY_MANIFEST.sha256'


def read_manifest(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        digest, separator, relative = line.partition('  ')
        parts = PurePosixPath(relative).parts
        if (not separator or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or not relative or '\\' in relative or ':' in relative
                or PurePosixPath(relative).is_absolute() or '..' in parts
                or str(PurePosixPath(relative)) != relative):
            raise ValueError(f'{path.name}:{number}: invalid manifest entry')
        if relative in expected:
            raise ValueError(f'{path.name}:{number}: duplicate path {relative}')
        expected[relative] = digest
    return expected


def validate(root: Path, tracked_paths: set[str] | None = None) -> list[str]:
    try:
        expected = read_manifest(root / CURRENT)
        historical = read_manifest(root / HISTORICAL)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    issues = []
    for relative in sorted(set(historical) - set(expected)):
        issues.append(f'Historical source omitted: {relative}')
    if tracked_paths is not None:
        required = tracked_paths - {CURRENT}
        for relative in sorted(required - set(expected)):
            issues.append(f'Tracked file omitted: {relative}')
        for relative in sorted(set(expected) - required):
            issues.append(f'Manifest file not tracked: {relative}')
    for relative, wanted in expected.items():
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            issues.append(f'Unsafe file: {relative}')
        elif not path.is_file():
            issues.append(f'Missing: {relative}')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != wanted:
            issues.append(f'Hash mismatch: {relative}')
    return issues


def main() -> int:
    tracked = None
    if (ROOT / '.git').exists():
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT,
                                capture_output=True, check=True)
        tracked = set(result.stdout.decode('utf-8').rstrip('\0').split('\0'))
    issues = validate(ROOT, tracked)
    if issues:
        print('\n'.join(issues))
        return 1
    print(f'Current source integrity: {len(read_manifest(ROOT / CURRENT))} SHA-256 entries PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
