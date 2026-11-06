"""Deterministic, synthetic contracts for the #159 shutdown-phase probe."""
from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from shutdown_phase_probe import observe_shutdown  # noqa: E402


class ShutdownPhaseProbeTests(unittest.TestCase):
    def test_aggregate_ticks_and_completion_do_not_include_private_data(self):
        async def scenario():
            sink = StringIO()
            state = SimpleNamespace(connections={"private-candidate": True},
                                    tasks={"private-token"})
            result = await observe_shutdown(
                asyncio.sleep(0.03, result="normal"), state,
                stream=sink, interval_s=0.005,
            )
            return result, sink.getvalue()

        result, text = asyncio.run(scenario())
        self.assertEqual(result, "normal")
        self.assertIn("event=start", text)
        self.assertIn("event=tick", text)
        self.assertIn("event=completed", text)
        self.assertIn("connections=1 tasks=1", text)
        self.assertNotIn("private-candidate", text)
        self.assertNotIn("private-token", text)
        self.assertLess(len(text.encode("utf-8")), 2500)

    def test_delegate_failure_propagates_without_suppression(self):
        async def fail():
            raise RuntimeError("synthetic shutdown failed")

        async def scenario():
            sink = StringIO()
            with self.assertRaisesRegex(RuntimeError, "synthetic shutdown failed"):
                await observe_shutdown(fail(), SimpleNamespace(
                    connections=set(), tasks=set()), stream=sink,
                    interval_s=0.01)
            return sink.getvalue()

        self.assertIn("event=exception", asyncio.run(scenario()))

    def test_broken_probe_stream_cannot_change_shutdown_result(self):
        class Broken:
            def write(self, _text):
                raise OSError("synthetic probe sink closed")
            def flush(self):
                raise OSError("synthetic probe sink closed")

        async def scenario():
            return await observe_shutdown(
                asyncio.sleep(0, result=3),
                SimpleNamespace(connections=[], tasks=[]),
                stream=Broken(), interval_s=0.01,
            )

        self.assertEqual(asyncio.run(scenario()), 3)


if __name__ == "__main__":
    unittest.main()
