"""Strict external Runtime staging and assembled Native ZIP verification.

A checksum inventory is supplied by a separate audit, never generated as a
trust decision from unknown production binaries. Passing is NOT GUI acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

KNOWLEDGE = ("taxonomy", "job_info", "competency", "market_reference", "reference")
PROVENANCE = "verification/INHERITED_WINDOWS_HOST_PROVENANCE.json"
LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")
PRIVATE_DIRS = {"data", "backups", "backup", "uploads", "workspace", "candidates", "secrets", "credentials", "private", "logs"}
PRIVATE_FILES = {".env", "provider_secrets.json", "secrets.json", "credentials.json"}


class PayloadError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def safe_path(path: str) -> tuple[str, ...]:
    if not path or "\\" in path or ":" in path or "\x00" in path:
        raise PayloadError("invalid path")
    p = PurePosixPath(path)
    parts = p.parts
    reserved = {"con", "prn", "nul", "aux"} | {"com" + str(i) for i in range(1, 10)} | {"lpt" + str(i) for i in range(1, 10)}
    if (p.is_absolute() or p.as_posix() != path or not parts or
        any(x in ("", ".", "..") or x.endswith((" ", ".")) or x.casefold().split(".")[0] in reserved for x in parts)):
        raise PayloadError("unsafe path")
    return parts


def read_manifest(path: Path, *, runtime: bool = False) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise PayloadError("manifest missing or symlink")
    result: dict[str, str] = {}
    folded = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        match = LINE.fullmatch(line)
        if match is None:
            raise PayloadError("malformed SHA inventory")
        name = match[2]
        parts = safe_path(name)
        if name.casefold() in folded:
            raise PayloadError("duplicate or case-colliding inventory path")
        folded.add(name.casefold())
        if runtime and (any(x.casefold() in PRIVATE_DIRS for x in parts) or
                        parts[-1].casefold() in PRIVATE_FILES or
                        parts[-1].lower().endswith((".pem", ".key", ".pfx", ".p12", ".db", ".sqlite"))):
            raise PayloadError("private file prohibited in runtime inventory")
        result[name] = match[1].lower()
    if not result or (runtime and "python.exe" not in result):
        raise PayloadError("empty inventory or missing python.exe")
    return result


def verified_input(root: Path, relative: str, digest: str) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise PayloadError("asset root missing or symbolic link")
    target = root
    for segment in safe_path(relative):
        target = target / segment
        if target.is_symlink():
            raise PayloadError("input contains symbolic link")
    if not target.is_file() or sha256_file(target) != digest:
        raise PayloadError("missing or mismatched input")
    return target


def audit_runtime(root: Path, manifest: Path) -> dict:
    expected = read_manifest(manifest, runtime=True)
    for name, digest in expected.items():
        verified_input(root, name, digest)
    return {"status": "PASS", "files": len(expected), "external_provenance_verified": False}


def stage_runtime(root: Path, manifest: Path, destination: Path) -> dict:
    summary = audit_runtime(root, manifest)
    if destination.exists() and (destination.is_symlink() or not destination.is_dir() or any(destination.iterdir())):
        raise PayloadError("destination is not empty")
    destination.mkdir(parents=True, exist_ok=True)
    for name, digest in read_manifest(manifest, runtime=True).items():
        original = verified_input(root, name, digest)
        target = destination.joinpath(*safe_path(name))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if sha256_file(target) != digest:
            raise PayloadError("staged runtime hash mismatch")
    return summary


def _host_members(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise PayloadError("carrier Host missing or symbolic link")
    result: dict[str, str] = {}
    for file in root.rglob("*"):
        if file.is_symlink():
            raise PayloadError("carrier Host has symbolic link")
        if file.is_file():
            rel = file.relative_to(root).as_posix()
            safe_path(rel)
            result["windows-host/" + rel] = sha256_file(file)
    if not {"windows-host/SmartRecruitmentWorkbench.exe", "windows-host/DOTNET_BUILD_TRUTH.json"} <= set(result):
        raise PayloadError("carrier Host incomplete")
    return result


def audit_zip(archive: Path, source: Path, host: Path) -> dict:
    source_m = source / "SOURCE_MANIFEST.sha256"
    runtime_m = source / "PRODUCTION_RUNTIME.sha256"
    knowledge_m = source / "PRODUCTION_KNOWLEDGE.sha256"
    expected = dict(read_manifest(source_m))
    expected["SOURCE_MANIFEST.sha256"] = sha256_file(source_m)
    expected["PRODUCTION_RUNTIME.sha256"] = sha256_file(runtime_m)
    expected["PRODUCTION_KNOWLEDGE.sha256"] = sha256_file(knowledge_m)
    for name, digest in read_manifest(runtime_m, runtime=True).items():
        expected["runtime/" + name] = digest
    know = read_manifest(knowledge_m)
    if set(know) != {f"{x}/knowledge.db" for x in KNOWLEDGE}:
        raise PayloadError("Knowledge manifest must list exactly five DBs")
    for name, digest in know.items():
        expected["knowledge/active/" + name] = digest
    expected.update(_host_members(host))
    if not archive.is_file() or archive.is_symlink():
        raise PayloadError("Native ZIP missing")
    try:
        with zipfile.ZipFile(archive) as z:
            members = {}
            collision = set()
            for info in z.infolist():
                name = info.filename.rstrip("/") if info.is_dir() else info.filename
                safe_path(name)
                if ((info.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
                    raise PayloadError("symbolic link ZIP member")
                if info.is_dir():
                    continue
                if name.casefold() in collision:
                    raise PayloadError("duplicate or colliding ZIP member")
                collision.add(name.casefold())
                members[name] = info
            if set(members) != set(expected) | {PROVENANCE}:
                raise PayloadError("ZIP member allowlist mismatch")
            for name, digest in expected.items():
                h = hashlib.sha256()
                with z.open(members[name]) as stream:
                    for part in iter(lambda: stream.read(1 << 20), b""):
                        h.update(part)
                if h.hexdigest() != digest:
                    raise PayloadError("ZIP member hash mismatch")
            try:
                provenance = json.loads(z.read(PROVENANCE).decode("utf-8-sig"))
                version = z.read("VERSION").decode("utf-8-sig").strip()
            except (UnicodeError, ValueError) as exc:
                raise PayloadError("invalid ZIP provenance") from exc
            if (provenance.get("artifact_status") != "UNVERIFIED_GUI" or
                provenance.get("target_version") != version or
                provenance.get("source_manifest_sha256") != expected["SOURCE_MANIFEST.sha256"] or
                provenance.get("runtime_manifest_sha256") != expected["PRODUCTION_RUNTIME.sha256"] or
                provenance.get("host_executable_sha256") != expected["windows-host/SmartRecruitmentWorkbench.exe"]):
                raise PayloadError("ZIP provenance mismatch")
    except zipfile.BadZipFile as exc:
        raise PayloadError("invalid candidate ZIP") from exc
    return {"status": "PASS", "files_verified": len(members),
            "candidate_sha256": sha256_file(archive),
            "artifact_status": "UNVERIFIED_GUI", "gui_accepted": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="cmd", required=True)
    stage = commands.add_parser("stage-runtime")
    stage.add_argument("--runtime", type=Path, required=True)
    stage.add_argument("--manifest", type=Path, required=True)
    stage.add_argument("--destination", type=Path, required=True)
    audit = commands.add_parser("audit-zip")
    audit.add_argument("--zip", type=Path, required=True)
    audit.add_argument("--source-root", type=Path, required=True)
    audit.add_argument("--host-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (stage_runtime(args.runtime, args.manifest, args.destination)
                  if args.cmd == "stage-runtime"
                  else audit_zip(args.zip, args.source_root, args.host_root))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PayloadError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
