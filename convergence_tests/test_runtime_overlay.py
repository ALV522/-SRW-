from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.check_embedded_runtime_compatibility import check
from scripts.upgrade_embedded_runtime import configure_isolated_path, validate_wheelhouse
from scripts.native_payload import PayloadError, read_manifest


class C11RuntimeOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        (self.runtime / "python.exe").write_bytes(b"synthetic")
        (self.runtime / "python312.dll").write_bytes(b"synthetic")
        self.site = self.runtime / "Lib" / "site-packages"
        self.site.mkdir(parents=True)
        self.overlay = self.runtime / "Lib" / "c11-overlay"
        self.overlay.mkdir()
        self.pth = self.runtime / "python312._pth"
        self.pth.write_text("python312.zip\n.\nLib\\site-packages\nimport site\n")
        self.lock = self.root / "requirements-ci.txt"
        self.lock.write_text("SQLAlchemy==2.1.5\npsutil==7.2.2\n")
        self._installed(self.site, "SQLAlchemy", "2.0.43")
        self._installed(self.overlay, "SQLAlchemy", "2.1.5")
        self._installed(self.overlay, "psutil", "7.2.2")

    @staticmethod
    def _installed(site: Path, name: str, version: str):
        meta = site / f"{name}-{version}.dist-info"
        meta.mkdir()
        (meta / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n\n")

    def test_overlay_path_has_precedence_and_matches_pins(self):
        configure_isolated_path(self.runtime)
        report = check(self.runtime, self.lock)
        self.assertEqual(report["status"], "PINNED_METADATA_MATCH")
        self.assertEqual(report["matched"], 2)
        self.assertTrue(report["c11_overlay_on_path"])
        self.assertTrue(all(x["origin"] == "c11-overlay" for x in report["dependencies"]))
        self.assertFalse(report["windows_runtime_executed"])

    def test_unconfigured_overlay_cannot_falsely_pass(self):
        with self.assertRaisesRegex(ValueError, "unconfigured"):
            check(self.runtime, self.lock)

    def test_wrong_order_is_blocked(self):
        self.pth.write_text("Lib\\site-packages\nLib\\c11-overlay\nimport site\n")
        with self.assertRaisesRegex(ValueError, "precedence"):
            check(self.runtime, self.lock)

    def test_original_legacy_path_remains_and_double_insertion_refused(self):
        configure_isolated_path(self.runtime)
        lines = self.pth.read_text().splitlines()
        self.assertLess(lines.index("Lib\\c11-overlay"), lines.index("Lib\\site-packages"))
        self.assertIn("import site", lines)
        with self.assertRaisesRegex(PayloadError, "already"):
            configure_isolated_path(self.runtime)

    def test_unreviewed_wheelhouse_is_rejected(self):
        house = self.root / "wheelhouse"
        house.mkdir()
        wheel = house / "psutil-7.2.2-cp312-cp312-win_amd64.whl"
        wheel.write_bytes(b"fake synthetic wheel")
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        (house / "WHEELHOUSE.sha256").write_text(f"{digest}  {wheel.name}\n")
        self.assertEqual(len(validate_wheelhouse(house)), 1)
        wheel.write_bytes(b"tampered")
        with self.assertRaises(PayloadError):
            validate_wheelhouse(house)

    def test_overlay_certifi_ca_allowed_but_private_key_still_rejected(self):
        manifest = self.root / "runtime.sha256"
        f = self.overlay / "certifi" / "cacert.pem"
        f.parent.mkdir()
        f.write_bytes(b"public certificate")
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        manifest.write_text(f"{digest}  Lib/c11-overlay/certifi/cacert.pem\n"
                            f"{hashlib.sha256(b'x').hexdigest()}  python.exe\n")
        self.assertEqual(len(read_manifest(manifest, runtime=True)), 2)
        manifest.write_text(manifest.read_text() + f"{digest}  Lib/c11-overlay/private.pem\n")
        with self.assertRaisesRegex(PayloadError, "private"):
            read_manifest(manifest, runtime=True)


if __name__ == "__main__":
    unittest.main()
