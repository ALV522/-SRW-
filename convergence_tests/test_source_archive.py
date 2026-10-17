import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build_source_archive.py'


class SourceArchiveTest(unittest.TestCase):
    def test_archive_is_reproducible_excludes_user_data_and_binds_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = root / 'module.py'
            code.write_bytes(b'source\n')
            line = hashlib.sha256(code.read_bytes()).hexdigest() + '  module.py\n'
            (root / 'SOURCE_RECOVERY_MANIFEST.sha256').write_text(line)
            (root / 'SOURCE_MANIFEST.sha256').write_text(line)
            (root / 'private-resume.txt').write_text('must not ship')
            archive = root / 'out/source.zip'
            command = [sys.executable, str(SCRIPT), '--root', str(root), '--output', str(archive), '--commit', 'a' * 40]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            first = archive.read_bytes()
            with zipfile.ZipFile(archive) as package:
                self.assertNotIn('private-resume.txt', package.namelist())
                self.assertEqual(json.loads(package.read('BUILD_PROVENANCE.json'))['commit'], 'a' * 40)
                self.assertEqual(package.read('module.py'), b'source\n')
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(first, archive.read_bytes())
            self.assertEqual(archive.with_suffix('.zip.sha256').read_text().split()[0], hashlib.sha256(first).hexdigest())

    def test_tampered_source_cannot_be_packaged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'module.py').write_text('changed')
            line = hashlib.sha256(b'original').hexdigest() + '  module.py\n'
            for name in ('SOURCE_MANIFEST.sha256', 'SOURCE_RECOVERY_MANIFEST.sha256'):
                (root / name).write_text(line)
            output = root / 'out.zip'
            result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), '--output', str(output), '--commit', 'a' * 40], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Hash mismatch', result.stdout + result.stderr)
            self.assertFalse(output.exists())
