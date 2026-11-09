"""Test-only, bounded Uvicorn shutdown phase visibility for #159.

Never enabled in a product run unless the synthetic acceptance fixture explicitly
sets SRW_TEST_SHUTDOWN_PHASE_PROBE=1. It changes no shutdown timeouts, locks,
credentials, HTTP behaviour or cancellation decisions. Values are aggregate
connection/task counts and whole-second elapsed times; never IDs or paths.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import sys
import time
from typing import Any, Awaitable, TextIO, TypeVar

import uvicorn

T = TypeVar("T")


def emit_stage(event: str) -> None:
    """Fixed-name, best-effort markers; no objects, IDs, paths or exceptions."""
    try:
        sys.stderr.write(f"SRW_SHUTDOWN_PHASE stage={event}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


async def observe_shutdown(
    shutdown: Awaitable[T], state: Any, *,
    stream: TextIO, interval_s: float = 2.0,
) -> T:
    """Run the *unaltered* shutdown coroutine with bounded, aggregate telemetry.

    The observer is cancelled on every exit path; it neither delays shutdown
    nor catches the underlying exception. If the event loop itself stalls,
    the absence of further ticks remains diagnostic evidence.
    """
    started = time.monotonic()

    def emit(event: str) -> None:
        try:
            connections = len(state.connections)
            tasks = len(state.tasks)
            elapsed = int(max(0, time.monotonic() - started))
            stream.write(
                f"SRW_SHUTDOWN_PHASE event={event} elapsed_s={elapsed} "
                f"connections={connections} tasks={tasks}\n"
            )
            stream.flush()
        except (OSError, ValueError, AttributeError, TypeError):
            # Probe output is best effort; never override shutdown semantics.
            return

    async def observe() -> None:
        while True:
            await asyncio.sleep(interval_s)
            emit("tick")

    emit("start")
    observer = asyncio.create_task(observe())
    try:
        result = await shutdown
    except BaseException:
        emit("exception")
        raise
    else:
        emit("completed")
        return result
    finally:
        observer.cancel()
        with suppress(asyncio.CancelledError):
            await observer


class ShutdownPhaseProbeServer(uvicorn.Server):
    """Test-only stage markers around Uvicorn's unchanged shutdown delegates."""

    async def _wait_tasks_to_complete(self) -> None:
        emit_stage("drain_enter")
        try:
            return await super()._wait_tasks_to_complete()
        finally:
            emit_stage("drain_exit")

    async def shutdown(self, sockets=None) -> None:
        original_lifespan_shutdown = self.lifespan.shutdown

        async def traced_lifespan_shutdown() -> None:
            emit_stage("lifespan_enter")
            try:
                return await original_lifespan_shutdown()
            finally:
                emit_stage("lifespan_exit")

        self.lifespan.shutdown = traced_lifespan_shutdown
        try:
            await observe_shutdown(
                super().shutdown(sockets=sockets),
                self.server_state,
                stream=sys.stderr,
            )
        finally:
            self.lifespan.shutdown = original_lifespan_shutdown
