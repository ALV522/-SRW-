"""E5 safe synthetic attach owner: two browser carriers, one disposable Core.

Builds on the E4 independent process owner, but replaces E4 open proxy URLs
with E5 per-carrier attach capabilities and pinned Core instance identity.
No Windows Native EXE, real users, or production database is involved.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass,field
from typing import Iterator

from e4_shared_core import launch_shared_e4
from e5_attach import make_e5_carrier_server


@dataclass
class E5Owner:
    _e4: object
    _servers: dict = field(default_factory=dict)
    _threads: dict = field(default_factory=dict)
    _tokens: dict = field(default_factory=dict)

    @property
    def api(self):
        return self._e4.api

    @property
    def core(self):
        return self._e4.core

    @property
    def pid(self):
        return self._e4.pid

    @property
    def cid(self):
        return self._e4.cid

    def attach(self, carrier: str) -> str:
        if carrier not in {"web","desktop_surrogate"}:
            raise ValueError("Only two named synthetic E5 carriers are permitted")
        if carrier in self._servers:
            raise ValueError("Carrier already attached")
        if self.core.poll() is not None:
            raise RuntimeError("Cannot attach to a dead synthetic Core")
        server,token=make_e5_carrier_server(
            upstream=self.api, candidate_ids=set(self._e4._candidates)
        )
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self._servers[carrier]=server
        self._threads[carrier]=thread
        self._tokens[carrier]=token
        return self.attach_url(carrier)

    def url(self, carrier: str) -> str:
        if carrier not in self._servers:
            raise ValueError("Carrier not attached")
        return f"http://127.0.0.1:{self._servers[carrier].server_address[1]}"

    def attach_url(self, carrier: str) -> str:
        """Sensitive, synthetic-only capability URL: never persist or log it."""
        return self.url(carrier)+"/attach/"+self._tokens[carrier]

    def detach(self, carrier: str) -> None:
        server=self._servers.pop(carrier,None)
        thread=self._threads.pop(carrier,None)
        self._tokens.pop(carrier,None)
        if server:
            server.RequestHandlerClass._active=False
            server.shutdown()
            server.server_close()
        if thread:
            thread.join(timeout=5)

    def close(self):
        for carrier in tuple(self._servers):
            self.detach(carrier)


@contextmanager
def launch_e5_owner() -> Iterator[E5Owner]:
    with launch_shared_e4() as e4:
        # E4's two permissive prototype proxies are deliberately discarded:
        # E5 serves ONLY protected per-carrier attach endpoints.
        e4.detach("web")
        e4.detach("desktop_surrogate")
        e5=E5Owner(e4)
        try:
            e5.attach("web")
            e5.attach("desktop_surrogate")
            yield e5
        finally:
            e5.close()
