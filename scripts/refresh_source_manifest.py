"""Render or incrementally update the authoritative source manifest.

Why the index, not the working tree
-----------------------------------
The manifest pins *committed* bytes. On Windows a working tree can hold CRLF while
the Git index and the CI checkout hold LF (``.gitattributes`` declares
``* text=auto eol=lf``), so hashing the file on disk can produce a manifest that
already disagrees with the blob it claims to describe. Both writing modes
therefore hash the **index blob** (``git cat-file``), and the manifest itself is
always written as LF bytes.

Modes
-----
* no arguments: print the rendered manifest to stdout. Read-only and diagnostic;
  it never refuses and never writes, because CI uses it to produce a candidate
  for diffing while ``check_source_integrity.py`` remains the gate.
* ``--write``: replace the manifest from the index. Strict: refused when a
  manifest entry is no longer tracked (a removal) unless ``--allow-removals`` is
  given explicitly.
* ``--paths a,b`` (repeatable): update only the named entries and leave every
  other line byte-identical, so two PRs touching disjoint files no longer rewrite
  the same 415 lines. A new tracked path is inserted once, in sorted place.
  Removals are refused in this mode.

Both writing modes refuse to hide drift: an unselected tracked file whose index
bytes no longer match its pinned digest, or a manifest entry that is no longer
tracked, is an error rather than a silent rewrite. After writing, the full
``check_source_integrity`` validation runs against the working tree; if it fails,
the previous manifest bytes are restored so a bad write cannot be committed.

Provenance of a digest
----------------------
``--paths`` and ``--write`` hash the index blob. For ``--paths`` the selected
files must also match the working tree, because a digest taken from a divergent
checkout describes bytes nobody will receive; ``--from-index`` is the explicit
opt-in when the divergence is known and intended.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = "SOURCE_MANIFEST.sha256"
PROTECTED = "SOURCE_RECOVERY_MANIFEST.sha256"
SEPARATOR = "  "

#: Index modes we accept: a regular file (executable or not). Symlinks (120000)
#: and submodules (160000) have no stable byte content of their own.
REGULAR_MODES = frozenset({"100644", "100755"})


class RefreshError(Exception):
    """A refusal. The message names the repo-relative path, never a host path."""


def _git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    try:
        return subprocess.run(["git", *args], cwd=root, input=stdin,
                              capture_output=True, check=True).stdout
    except FileNotFoundError as exc:  # git missing entirely
        raise RefreshError("git is not available") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RefreshError(
            f"git {' '.join(args)} failed: {detail[0] if detail else 'unknown'}") from exc


def index_entries(root: Path) -> dict[str, tuple[str, str]]:
    """Tracked path -> (mode, blob sha) straight from the index.

    An unresolved merge has stages 1/2/3 and no stage 0. Collapsing those into
    one record would let ``--from-index`` pin a conflict-stage blob as if it were
    committed source, so any non-zero stage, duplicate record or unmerged path is
    refused before a digest is computed or the manifest is touched.
    """
    raw = _git(root, "ls-files", "-s", "-z").decode("utf-8")
    entries: dict[str, tuple[str, str]] = {}
    for record in raw.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        fields = meta.split()
        if not path or len(fields) != 3:
            raise RefreshError(f"unexpected Git index record for {path or '<unknown>'}")
        mode, sha, stage = fields
        if stage != "0":
            raise RefreshError(
                f"Git index has an unmerged entry (stage {stage}) for {path}; "
                "resolve the merge before touching the manifest")
        if path in entries:
            raise RefreshError(f"Git index has duplicate records for {path}")
        entries[path] = (mode, sha)
    return entries


def index_blobs(root: Path, paths: list[str]) -> dict[str, bytes]:
    """Blob bytes for each path, read through ``git cat-file --batch``."""
    entries = index_entries(root)
    wanted = {path: entries[path][1] for path in paths if path in entries}
    if not wanted:
        return {}
    order = list(dict.fromkeys(wanted.values()))
    out = _git(root, "cat-file", "--batch", stdin=("\n".join(order) + "\n").encode())
    by_sha: dict[str, bytes] = {}
    position = 0
    for sha in order:
        newline = out.index(b"\n", position)
        header = out[position:newline].split()
        if len(header) != 3 or header[1] != b"blob":
            raise RefreshError(f"index object is not a blob: {sha[:12]}")
        size = int(header[2])
        by_sha[sha] = out[newline + 1:newline + 1 + size]
        position = newline + 1 + size + 1
    return {path: by_sha[sha] for path, sha in wanted.items()}


def parse_manifest(text: str) -> dict[str, str]:
    """Parse and validate the existing manifest; refuse anything ambiguous."""
    entries: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line:
            continue
        digest, separator, path = line.partition(SEPARATOR)
        if not separator or len(digest) != 64:
            raise RefreshError(f"{CURRENT}:{number}: not '<64-hex>{SEPARATOR}<path>'")
        if any(char not in "0123456789abcdef" for char in digest):
            raise RefreshError(f"{CURRENT}:{number}: digest is not lowercase hex")
        if (not path or "\\" in path or ":" in path or path.startswith("/")
                or ".." in path.split("/") or unicodedata.normalize("NFC", path) != path):
            raise RefreshError(f"{CURRENT}:{number}: unsafe manifest path")
        if path in entries:
            raise RefreshError(f"{CURRENT}:{number}: duplicate path {path}")
        entries[path] = digest
    if not entries:
        raise RefreshError(f"{CURRENT}: manifest is empty")
    return entries


def _normalise_selection(values: list[str]) -> list[str]:
    """Validate ``--paths`` input; every refusal names the offending value."""
    chosen: list[str] = []
    seen: dict[str, str] = {}
    for group in values:
        for raw in group.split(","):
            path = raw.strip()
            if not path:
                raise RefreshError("--paths contains an empty path")
            if path == CURRENT:
                raise RefreshError(f"{CURRENT} pins the other files and excludes itself")
            if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
                raise RefreshError(f"--paths must be repo-relative: {path}")
            if "\\" in path:
                raise RefreshError(f"--paths must use POSIX separators: {path}")
            if any(segment in {"", ".", ".."} for segment in path.split("/")):
                raise RefreshError(f"--paths rejects empty, '.' or '..' segments: {path}")
            if unicodedata.normalize("NFC", path) != path:
                raise RefreshError(f"--paths must be NFC-normalised: {path!r}")
            alias = unicodedata.normalize("NFC", path).casefold()
            if alias in seen:
                raise RefreshError(
                    f"--paths has an ambiguous alias: {path!r} collides with {seen[alias]!r}")
            seen[alias] = path
            chosen.append(path)
    return chosen


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _render(mapping: dict[str, str]) -> str:
    return "\n".join(f"{digest}{SEPARATOR}{path}" for path, digest in sorted(mapping.items())) + "\n"


def _check_worktree_matches_index(root: Path, blobs: dict[str, bytes]) -> None:
    """A digest read from a divergent working tree describes bytes nobody gets."""
    for path, blob in blobs.items():
        try:
            on_disk = (root / path).read_bytes()
        except OSError as exc:
            raise RefreshError(f"tracked file is unreadable in the working tree: {path}") from exc
        if on_disk != blob:
            raise RefreshError(
                f"working tree differs from the Git index for {path}; "
                "re-checkout the file or pass --from-index to pin the committed blob")


def _integrity_issues(root: Path) -> list[str]:
    module_path = root / "scripts" / "check_source_integrity.py"
    spec = importlib.util.spec_from_file_location("_srw_check_source_integrity", module_path)
    if spec is None or spec.loader is None:
        raise RefreshError("cannot load scripts/check_source_integrity.py")
    module = importlib.util.module_from_spec(spec)
    # Loading the checker must not leave __pycache__ inside the tree we are about
    # to validate: an untracked .pyc can be staged by a later `git add -A` and
    # then look like a manifest omission that has nothing to do with this change.
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module.validate(root, set(index_entries(root)))


def _write_manifest(root: Path, rendered: str, *, ignorable: frozenset[str] = frozenset()) -> None:
    """Write LF bytes atomically, then verify the whole tree; restore on failure.

    ``ignorable`` carries the exact mismatch lines the caller has already
    justified (a selected file whose checkout intentionally differs from the
    pinned index blob under ``--from-index``). Anything else still restores.
    """
    target = root / CURRENT
    previous = target.read_bytes() if target.exists() else b""
    payload = rendered.encode("utf-8")  # never write_text: no ambient newline conversion
    if b"\r\n" in payload:
        raise RefreshError("refusing to write CRLF into the manifest")
    temporary = target.with_name(target.name + ".tmp-refresh")

    def _replace(data: bytes) -> None:
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)

    def _restore() -> None:
        try:
            _replace(previous)
        except OSError as exc:
            # Never hide a failed rollback: the caller must know the manifest on
            # disk is no longer the one it started with.
            raise RefreshError(
                f"ROLLBACK FAILED after a rejected write ({type(exc).__name__}); "
                f"{CURRENT} may be inconsistent") from exc

    _replace(payload)
    try:
        issues = [issue for issue in _integrity_issues(root) if issue not in ignorable]
    except Exception as exc:
        # A raising validator (Git failure, read error, loader problem) must not
        # leave the new bytes behind: the refusal contract is "nothing changed".
        _restore()
        raise RefreshError(
            "validation raised after write; manifest restored: "
            f"{type(exc).__name__}: {exc}") from exc
    if issues:
        _restore()
        raise RefreshError("full source integrity failed after write; manifest restored: "
                           + "; ".join(issues[:5]))


def _divergent(root: Path, paths: list[str]) -> frozenset[str]:
    """Selected files whose checkout differs from the index blob."""
    divergent = set()
    for path, blob in index_blobs(root, paths).items():
        try:
            matches = (root / path).read_bytes() == blob
        except OSError:
            matches = False  # unreadable is not "matching"
        if not matches:
            divergent.add(path)
    return frozenset(divergent)


def update_selected(root: Path, previous: dict[str, str], selected: list[str],
                    *, from_index: bool) -> dict[str, str]:
    """Return the new mapping: selected digests refreshed, everything else kept."""
    entries = index_entries(root)
    for path in selected:
        if path not in entries:
            raise RefreshError(f"--paths names a path that is not tracked: {path}")
        mode = entries[path][0]
        if mode not in REGULAR_MODES:
            raise RefreshError(f"--paths rejects a non-regular index entry ({mode}): {path}")

    blobs = index_blobs(root, selected)
    if not from_index:
        _check_worktree_matches_index(root, blobs)

    # A tracked file that the manifest never listed is drift too: silently
    # leaving it out is how an inventory rots. Answer: select it or run --write.
    unlisted = sorted(path for path in entries
                      if path != CURRENT and path not in previous and path not in selected)
    if unlisted:
        raise RefreshError(
            "tracked path is missing from the manifest and not in --paths: "
            + ", ".join(unlisted[:5]))

    updated = dict(previous)
    for path, blob in blobs.items():
        updated[path] = _digest(blob)

    # Fail closed instead of hiding drift outside the selection.
    unselected = sorted(set(previous) - set(selected))
    for path, blob in index_blobs(root, unselected).items():
        if previous[path] != _digest(blob):
            raise RefreshError(
                f"tracked file changed but is not in --paths: {path}; "
                "add it to --paths or run --write")
    for path in previous:
        if path not in entries:
            raise RefreshError(
                f"manifest lists a path that is no longer tracked: {path}; "
                "removals need --write --allow-removals")
    return updated


def full_mapping(root: Path, previous: dict[str, str] | None, *,
                 allow_removals: bool) -> dict[str, str]:
    entries = {path: mode for path, (mode, _sha) in index_entries(root).items()}
    for path, mode in entries.items():
        if mode not in REGULAR_MODES:
            raise RefreshError(f"tracked path is not a regular file ({mode}): {path}")
    paths = [path for path in entries if path != CURRENT]
    mapping = {path: _digest(blob) for path, blob in index_blobs(root, paths).items()}
    if previous is not None and not allow_removals:
        dropped = sorted(set(previous) - set(mapping))
        if dropped:
            raise RefreshError(
                "refusing to drop manifest entries without --allow-removals: "
                + ", ".join(dropped[:5]))
    return mapping


def main(argv: list[str] | None = None, *, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or update SOURCE_MANIFEST.sha256")
    parser.add_argument("--write", action="store_true", help="replace the manifest")
    parser.add_argument("--paths", action="append", default=[], metavar="a,b",
                        help="only update these tracked paths (repeatable, comma-separated)")
    parser.add_argument("--from-index", action="store_true",
                        help="pin the index blob even when the working tree differs")
    parser.add_argument("--allow-removals", action="store_true",
                        help="with --write, permit dropping entries that are no longer tracked")
    args = parser.parse_args(argv)
    effective_root = ROOT if root is None else root

    try:
        if args.paths and args.allow_removals:
            raise RefreshError("--allow-removals only applies to --write")
        selection = _normalise_selection(args.paths) if args.paths else []
        manifest_path = effective_root / CURRENT
        previous_text = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
        previous = parse_manifest(previous_text) if previous_text is not None else None

        if selection:
            if previous is None:
                raise RefreshError(f"{CURRENT} is missing; run --write once first")
            mapping = update_selected(effective_root, previous, selection,
                                      from_index=args.from_index)
        else:
            mapping = full_mapping(effective_root, previous,
                                   allow_removals=args.allow_removals)

        rendered = _render(mapping)
        if not args.write:
            sys.stdout.buffer.write(rendered.encode("utf-8"))
            return 0
        ignorable: frozenset[str] = frozenset()
        if selection and args.from_index:
            # The caller has explicitly asked to pin the committed blob while the
            # checkout differs; the working-tree check legitimately disagrees for
            # exactly those files until they are re-checked out.
            ignorable = frozenset(f"Hash mismatch: {path}"
                                  for path in _divergent(effective_root, selection))
        _write_manifest(effective_root, rendered, ignorable=ignorable)
        print(f"wrote {CURRENT} with {len(mapping)} entries")
        return 0
    except RefreshError as exc:
        print(f"refresh_source_manifest: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
