from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _schema_revision() -> str:
    path = ROOT / "backend" / "srw" / "runtime" / "db" / "schema.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "V1_SCHEMA_REVISION":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    raise RuntimeError("V1_SCHEMA_REVISION not found")


def validate() -> list[str]:
    errors: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    build = json.loads((ROOT / "BUILD_INFO.json").read_text(encoding="utf-8"))
    release = json.loads((ROOT / "backend" / "srw" / "release_state.json").read_text(encoding="utf-8"))
    portable = json.loads((ROOT / "PORTABLE_MANIFEST.json").read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "VERIFICATION_TRUTH.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "VERIFICATION_INVENTORY.json").read_text(encoding="utf-8"))
    windows = json.loads((ROOT / "WINDOWS_NATIVE_HOST_STATUS.json").read_text(encoding="utf-8"))
    schema = _schema_revision()

    version_values = {
        "VERSION": version,
        "BUILD_INFO.version": str(build.get("version", "")),
        "BUILD_INFO.release_id": str(build.get("release_id", "")),
        "release_state.version": str(release.get("version", "")),
        "PORTABLE_MANIFEST.version": str(portable.get("version", "")),
        "VERIFICATION_TRUTH.version": str(truth.get("version", "")),
        "VERIFICATION_INVENTORY.release": str(inventory.get("release", "")),
        "WINDOWS_NATIVE_HOST_STATUS.release": str(windows.get("release", "")),
    }
    for name, value in version_values.items():
        if value != version:
            errors.append(f"version mismatch: {name}={value!r}, VERSION={version!r}")

    schema_values = {
        "release_state.schema_revision": str(release.get("schema_revision", "")),
        "PORTABLE_MANIFEST.schema_revision": str(portable.get("schema_revision", "")),
        "VERIFICATION_TRUTH.schema_revision": str(truth.get("schema_revision", "")),
        "VERIFICATION_INVENTORY.schema_revision": str(inventory.get("schema_revision", "")),
    }
    for name, value in schema_values.items():
        if value != schema:
            errors.append(f"schema mismatch: {name}={value!r}, code={schema!r}")
    return errors


if __name__ == "__main__":
    issues = validate()
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("release truth binding: PASS")
