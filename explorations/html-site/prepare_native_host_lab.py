"""Prepare a distinctly labeled WPF SOURCE-LAB host, without touching originals.

Only substitute AppPaths' embedded-Python lookup with the standard Scripts/
location of a Python 3.12 virtual environment. Both substitutions are
required; if source structure changes, fail rather than patching heuristically.

Official desktop source and its exact binary output are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"desktop"/"SRW.Desktop"
TARGET="Runtime/AppPaths.cs"
FROM='Path.Combine(ApplicationRoot, "runtime", "python.exe")'
TO='Path.Combine(ApplicationRoot, "runtime", "Scripts", "python.exe")'
FROM_REQUIRE='Path.Combine(applicationRoot, "runtime", "python.exe")'
TO_REQUIRE='Path.Combine(applicationRoot, "runtime", "Scripts", "python.exe")'


def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def prepare(output:Path):
    dest=output.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Refusing to overwrite existing WPF lab source")
    shutil.copytree(SRC,dest,dirs_exist_ok=True)
    file=dest/TARGET
    original=file.read_text(encoding="utf-8")
    if original.count(FROM)!=1 or original.count(FROM_REQUIRE)!=1:
        raise ValueError("Current AppPaths no longer matches explicitly reviewed lab patch")
    modified=original.replace(FROM,TO).replace(FROM_REQUIRE,TO_REQUIRE)
    file.write_text(modified,encoding="utf-8")
    manifest={
        "schema":"srw.native-lab-wpf-source-patch.v1",
        "source_modified":True,
        "production_source_modified":False,
        "original_source":TARGET,
        "purpose":"Source-only virtual-environment discovery instead of embedded Python Runtime",
        "replacements":[{"old":FROM,"new":TO},{"old":FROM_REQUIRE,"new":TO_REQUIRE}],
        "original_sha256":sha(original.encode("utf-8")),
        "patched_sha256":sha(modified.encode("utf-8")),
        "release_approved":False,
    }
    (dest/"NATIVE_LAB_CSHARP_PATCH.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PASS: isolated WPF Source Lab virtualenv path adaptation; main desktop sources unchanged.",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    prepare(args.output)
