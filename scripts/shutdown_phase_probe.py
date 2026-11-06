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
    """Uvicorn's normal implementation plus synthetic-test-only observation."""

    async def shutdown(self, sockets=None) -> None:
        await observe_shutdown(
            super().shutdown(sockets=sockets),
            self.server_state,
            stream=sys.stderr,
        )
