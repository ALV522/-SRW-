"""Deterministic, synthetic contracts for the #159 shutdown-phase probe."""
from __future__ import annotations

import asyncio
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from shutdown_phase_probe import observe_shutdown, ShutdownPhaseProbeServer  # noqa: E402


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


    def test_uvicorn_stages_are_marked_without_changing_delegate_order(self):
        import uvicorn

        async def scenario():
            server = ShutdownPhaseProbeServer(uvicorn.Config(lambda s, r, send: None))
            server.server_state = SimpleNamespace(connections=set(), tasks=set())
            sequence = []

            async def lifespan_shutdown():
                sequence.append("lifespan")

            lifespan = SimpleNamespace(shutdown=lifespan_shutdown)
            server.lifespan = lifespan
            original = lifespan.shutdown

            async def fake_drain(self):
                sequence.append("drain")

            async def fake_shutdown(self, sockets=None):
                await self._wait_tasks_to_complete()
                await self.lifespan.shutdown()

            sink = StringIO()
            with redirect_stderr(sink), patch.object(uvicorn.Server, "_wait_tasks_to_complete", fake_drain), \
                    patch.object(uvicorn.Server, "shutdown", fake_shutdown):
                await server.shutdown()
            return sequence, sink.getvalue(), lifespan.shutdown is original

        sequence, text, restored = asyncio.run(scenario())
        self.assertEqual(sequence, ["drain", "lifespan"])
        self.assertTrue(restored)
        for marker in ("drain_enter", "drain_exit", "lifespan_enter", "lifespan_exit"):
            self.assertIn("stage=" + marker, text)
        self.assertIn("event=completed", text)

    def test_uvicorn_lifespan_failure_is_not_hidden_and_wrapper_is_restored(self):
        import uvicorn

        async def scenario():
            server = ShutdownPhaseProbeServer(uvicorn.Config(lambda s, r, send: None))
            server.server_state = SimpleNamespace(connections=set(), tasks=set())

            async def fail_lifespan():
                raise RuntimeError("private-exception-detail")

            lifespan = SimpleNamespace(shutdown=fail_lifespan)
            server.lifespan = lifespan
            original = lifespan.shutdown

            async def fake_shutdown(self, sockets=None):
                await self.lifespan.shutdown()

            sink = StringIO()
            with redirect_stderr(sink), patch.object(uvicorn.Server, "shutdown", fake_shutdown):
                with self.assertRaisesRegex(RuntimeError, "private-exception-detail"):
                    await server.shutdown()
            return sink.getvalue(), lifespan.shutdown is original

        text, restored = asyncio.run(scenario())
        self.assertTrue(restored)
        self.assertIn("stage=lifespan_enter", text)
        self.assertIn("stage=lifespan_exit", text)
        self.assertIn("event=exception", text)
        self.assertNotIn("private-exception-detail", text)

if __name__ == "__main__":
    unittest.main()
