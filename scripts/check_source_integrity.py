"""Verify the exact C08 source-recovery baseline from repository source files.

The C08 source recovery manifest lists 212 immutable files, while .gitignore and
CI/repair scripts are outside the frozen baseline.
"""
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"SOURCE_RECOVERY_MANIFEST.sha256"

def main()->int:
    lines=MANIFEST.read_text(encoding="utf-8").splitlines()
    expected={}
    for line in lines:
        digest,rel=line.split("  ",1)
        if rel in expected:
            raise SystemExit(f"Duplicate manifest path: {rel}")
        expected[rel]=digest
    if len(expected)!=212:
        raise SystemExit(f"Expected 212 C08 source files, got {len(expected)}")
    missing=[];mismatched=[]
    for rel,wanted in expected.items():
        path=ROOT/rel
        if not path.is_file():
            missing.append(rel)
        else:
            got=hashlib.sha256(path.read_bytes()).hexdigest()
            if wanted!=got:mismatched.append(rel)
    if missing or mismatched:
        print("Missing:",missing)
        print("Hash mismatches:",mismatched)
        return 1
    print("C08 source integrity: 212/212 SHA-256 PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
