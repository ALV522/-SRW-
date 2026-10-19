"""Synthetic workspace cleanup must retry Windows locks and fail closed."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("srw_synthetic_workspace", HERE/"synthetic_workspace.py")
assert SPEC and SPEC.loader
work=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(work)


class E3SyntheticWorkspaceTests(unittest.TestCase):
    def test_cleanup_deletes_temporary_database(self):
        folder=None
        with work.synthetic_temporary_directory("srw-e3-unit-",attempts=3,retry_seconds=0) as td:
            folder=Path(td)
            (folder/"synthetic.db").write_bytes(b"not real SQLite")
        self.assertFalse(folder.exists())

    def test_cleanup_retries_transient_windows_permission_error(self):
        original=work.shutil.rmtree
        calls=[]
        def simulated_rmtree(path):
            calls.append(path)
            if len(calls)<3:
                raise PermissionError("[WinError 32] simulated temporary lock")
            return original(path)
        with patch.object(work.shutil,"rmtree",side_effect=simulated_rmtree):
            with work.synthetic_temporary_directory(
                "srw-e3-unit-",attempts=3,retry_seconds=0
            ) as td:
                folder=Path(td)
        self.assertEqual(len(calls),3)
        self.assertFalse(folder.exists())

    def test_cleanup_does_not_suppress_permanent_lock(self):
        folder=None
        with patch.object(work.shutil,"rmtree",side_effect=PermissionError("locked")):
            with self.assertRaisesRegex(RuntimeError,"cleanup failed"):
                with work.synthetic_temporary_directory(
                    "srw-e3-unit-",attempts=2,retry_seconds=0
                ) as td:
                    folder=Path(td)
        self.assertTrue(folder.exists())
        import shutil
        shutil.rmtree(folder)

    def test_rejects_non_exploration_directory_prefix(self):
        with self.assertRaisesRegex(ValueError,"temporary prefixes"):
            with work.synthetic_temporary_directory("production-"):
                pass


if __name__=="__main__":
    unittest.main()
