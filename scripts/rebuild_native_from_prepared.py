"""Build the next C11 Windows *candidate* from a pinned prior prepared ZIP.

This reduces the practical gap between source-built WPF Host and the existing
verified Runtime/Knowledge. It NEVER makes a release/GUI acceptance claim,
never upgrades an existing user-data workspace, never trusts an arbitrary ZIP
manifest, and never executes extracted Python until a separate acceptance step.

Inputs:
 - complete current *Git checkout* on the exact Host build commit;
 - matching-source Host artifact directory, with both Host truth JSONs;
 - the EXACT, independently recorded d8d032d prepared Native candidate ZIP.
Output: a new, manifest-audited, UNVERIFIED_GUI candidate ZIP.

Fail-closed: no checksum overrides, no manifest regeneration, no input editing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

if __package__ in ("", None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_native_from_source_host import (
    _verify_host, assemble, verified_git_sha,
)
from scripts.check_embedded_runtime_compatibility import check
from scripts.native_payload import (
    KNOWLEDGE, PayloadError, audit_runtime, read_manifest, safe_path,
    sha256_file,
)
from scripts.portable_input_preflight import knowledge_checks

# Historical file identity is fixed by the prior full ZIP's verified delivery
# evidence; accepting an arbitrary --expected-hash would defeat this gate.
BASE_PREPARED_GIT_SHA = "d8d032de255c87839adbeedc5737124d7fbfc3cd"
BASE_PREPARED_ZIP_SHA256 = (
    "27ae4765c035d7855ef69829256eaf33038362e0b28354b6af372c6d2304b2cb"
)
MAX_ENTRIES = 12000
MAX_SINGLE_SIZE = 1024 * 1024 * 1024
MAX_SELECTED_BYTES = 4 * 1024 * 1024 * 1024


def _members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members = {}
    folded = set()
    for info in archive.infolist():
        name = info.filename
        if info.is_dir():
            continue
        if len(members) >= MAX_ENTRIES:
            raise PayloadError("historical ZIP has too many files")
        safe_path(name)
        if name.casefold() in folded:
            raise PayloadError("historical ZIP has duplicate/colliding member")
        folded.add(name.casefold())
        if ((info.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
            raise PayloadError("historical ZIP contains symlink")
        if info.file_size > MAX_SINGLE_SIZE:
            raise PayloadError("historical ZIP contains oversized file")
        members[name] = info
    return members


def _checked_extract(
    archive: zipfile.ZipFile, member: zipfile.ZipInfo,
    target: Path, digest: str,
) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    actual = hashlib.sha256()
    with archive.open(member) as source, target.open("xb") as output:
        while True:
            block = source.read(1 << 20)
            if not block:
                break
            total += len(block)
            if total > MAX_SINGLE_SIZE or total > member.file_size:
                raise PayloadError("historical ZIP member exceeds its declared size")
            actual.update(block)
            output.write(block)
    if total != member.file_size or actual.hexdigest() != digest:
        raise PayloadError("historical Runtime/Knowledge file hash mismatch")
    return total


def stage_attested_inputs(
    base_zip: Path, target: Path, *,
    required_sha256: str = BASE_PREPARED_ZIP_SHA256,
) -> dict:
    """Stage ONLY reviewed runtime/knowledge members from exact predecessor.

    required_sha256 is an internal testing seam, not a CLI option.
    Production main() always requires BASE_PREPARED_ZIP_SHA256.
    """
    if target.exists() or target.is_symlink():
        raise PayloadError("refusing to overwrite staging input root")
    if base_zip.is_symlink() or not base_zip.is_file():
        raise PayloadError("pinned prepared ZIP missing or symbolic link")
    if sha256_file(base_zip) != required_sha256:
        raise PayloadError("prepared d8d032d ZIP SHA-256 mismatch; no fallback")
    with zipfile.ZipFile(base_zip) as zipped:
        members = _members(zipped)
        manifests = ("PRODUCTION_RUNTIME.sha256", "PRODUCTION_KNOWLEDGE.sha256")
        for name in manifests:
            if name not in members or members[name].file_size > 2 * 1024 * 1024:
                raise PayloadError("historical ZIP missing bounded external manifests")
        runtime_raw = zipped.read(manifests[0])
        knowledge_raw = zipped.read(manifests[1])
        target.mkdir(parents=True)
        for name, content in zip(manifests, (runtime_raw, knowledge_raw)):
            (target / name).write_bytes(content)
        runtime_inventory = read_manifest(target / manifests[0], runtime=True)
        knowledge_inventory = read_manifest(target / manifests[1])
        required_knowledge = {f"{name}/knowledge.db" for name in KNOWLEDGE}
        if set(knowledge_inventory) != required_knowledge:
            raise PayloadError("historical ZIP Knowledge manifest not five audited databases")
        selection = {
            "runtime/" + name: digest for name, digest in runtime_inventory.items()
        }
        selection.update({
            "knowledge/active/" + name: digest
            for name, digest in knowledge_inventory.items()
        })
        if not set(selection).issubset(members):
            raise PayloadError("historical ZIP missing attested Runtime/Knowledge members")
        bytes_written = 0
        for relative, digest in sorted(selection.items()):
            info = members[relative]
            bytes_written += info.file_size
            if bytes_written > MAX_SELECTED_BYTES:
                raise PayloadError("selected Runtime/Knowledge data exceeds extraction bound")
            _checked_extract(zipped, info, target.joinpath(*safe_path(relative)), digest)
    runtime_check = audit_runtime(target / "runtime", target / manifests[0])
    knowledge_check = knowledge_checks(
        target / "knowledge" / "active", target / manifests[1]
    )
    if len(knowledge_check) != 6 or any(
        row["status"] != "PASS" for row in knowledge_check
    ):
        raise PayloadError("five Knowledge database integrity checks failed")
    return {
        "source_prepared_sha": BASE_PREPARED_GIT_SHA,
        "source_zip_sha256": required_sha256,
        "runtime_files": runtime_check["files"],
        "knowledge_databases": len(required_knowledge),
        "staged_bytes": bytes_written,
        "external_provenance": "pinned prepared candidate; no manifest regeneration",
    }


def upgrade(
    root: Path, base_zip: Path, host: Path, out: Path, *,
    verify_only: bool = False,
) -> dict:
    root = root.resolve(strict=True)
    host = host.resolve(strict=True)
    out = out.resolve()
    if out.exists() or out.is_symlink():
        raise PayloadError("refusing to overwrite an existing candidate output")
    if base_zip.resolve() == out or out.is_relative_to(root):
        raise PayloadError("candidate output must be outside immutable source checkout")
    sha = verified_git_sha(root)
    # A compiled Host from any other commit is not a valid replacement.
    _verify_host(host, sha)
    with tempfile.TemporaryDirectory(prefix="srw-c11-pinned-native-upgrade-") as td:
        inputs = Path(td) / "attested-inputs"
        recovery = stage_attested_inputs(base_zip, inputs)
        dependency = check(inputs / "runtime", root / "requirements-ci.txt")
        if dependency.get("status") != "PINNED_METADATA_MATCH":
            raise PayloadError("historical runtime does not match current dependency lock")
        if dependency.get("c11_overlay_on_path"):
            # The overlay provenance is tied to the *historical* Runtime
            # from a verified prepared ZIP. Its archived executable smoke is
            # not proof the new binary / current source has passed Windows.
            # Preserve the historical upgrade audit, without re-signing it.
            with zipfile.ZipFile(base_zip) as archive:
                try:
                    historic = archive.read("RUNTIME_UPGRADE_AUDIT.json")
                except KeyError as exc:
                    raise PayloadError("historical runtime overlay audit missing") from exc
            (inputs / "RUNTIME_UPGRADE_AUDIT.json").write_bytes(historic)
        if verify_only:
            return {
                "status": "INPUTS_VERIFIED_ONLY",
                "source_git_sha": sha,
                "assembled": False,
                "windows_gui_accepted": False,
                "inputs": recovery,
            }
        result = assemble(root, inputs, host, out, expected_git_sha=sha)
        if result.get("status") != "CANDIDATE_UNVERIFIED_GUI":
            raise PayloadError("Native assembler returned non-candidate status")
        return {
            **result,
            "base_source_sha": BASE_PREPARED_GIT_SHA,
            "base_zip_sha256": BASE_PREPARED_ZIP_SHA256,
            "runtime_files": recovery["runtime_files"],
            "knowledge_databases": recovery["knowledge_databases"],
            "actual_windows_gui_acceptance": "PENDING",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parents[1],
        help="Complete Git checkout at the SAME SHA as the Host CI artifact"
    )
    parser.add_argument("--base-zip", type=Path, required=True,
                        help="Exact d8d032d prepared Native ZIP, SHA-256 pinned in code")
    parser.add_argument("--host", type=Path, required=True,
                        help="Extracted latest source-built Windows Host CI artifact directory")
    parser.add_argument("--out", type=Path,
                        help="New destination ZIP outside the source checkout; no overwrite")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only and args.out is None:
        parser.error("--out is required except with --verify-only")
    try:
        out = args.out or (Path(tempfile.gettempdir()) / "srw-unused-output.zip")
        result = upgrade(
            args.source, args.base_zip, args.host, out,
            verify_only=args.verify_only,
        )
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except (PayloadError, OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(json.dumps({
            "status": "BLOCKED", "error_type": type(exc).__name__,
            "reason": str(exc), "windows_gui_accepted": False,
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
