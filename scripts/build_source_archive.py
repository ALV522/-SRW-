"""Build a deterministic, manifest-only source ZIP. No runtime/user-data crawl."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from check_source_integrity import CURRENT, read_manifest, validate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        parser.error('--commit must be an exact Git commit SHA')
    issues = validate(args.root)
    if issues:
        print('\n'.join(issues))
        return 1
    names = set(read_manifest(args.root / CURRENT)) | {CURRENT}
    if 'BUILD_PROVENANCE.json' in names:
        raise ValueError('BUILD_PROVENANCE.json is reserved for the source packager')
    # Read and recheck bytes before creating output; the ZIP contains exactly these bytes.
    payloads = {name: (args.root / name).read_bytes() for name in names}
    for name, digest in read_manifest(args.root / CURRENT).items():
        if hashlib.sha256(payloads[name]).hexdigest() != digest:
            raise ValueError(f'Source changed during packaging: {name}')
    payloads['BUILD_PROVENANCE.json'] = (json.dumps({
        'artifact_kind': 'source', 'commit': args.commit,
        'source_manifest_sha256': hashlib.sha256(payloads[CURRENT]).hexdigest(),
        'portable_runtime_included': False, 'native_gui_verified': False,
    }, indent=2) + '\n').encode('utf-8')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + '.sha256').write_text(f'{digest}  {args.output.name}\n', encoding='utf-8')
    print(f'Source archive: {args.output.name}; SHA-256 {digest}; commit {args.commit}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
