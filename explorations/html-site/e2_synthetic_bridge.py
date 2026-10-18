#!/usr/bin/env python3
"""E2 *synthetic-only* experimental Action Plan concurrency facade.

This server class is NOT a generic proxy, NOT safe for real EXE data, and NOT
part of the production SRW core. Its owning launcher MUST create a disposable
SRW backend and pass an explicit allowlist of freshly synthesized candidate IDs.

Two browser clients using THIS facade get a stable ETag / If-Match contract.
Writes are serialized by a lock in the facade process, and the existing real
SRW Action Plan endpoint performs the business write/audit. A direct backend
writer can still race between facade read and write; this is why E2 is only a
concept experiment. Production needs transactional CAS inside SRW Core.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request
from urllib.parse import urlsplit

from serve_e1 import (
    OPENER, MAX_RESPONSE_BYTES, ReadOnlyBridge, is_allowed_api_path,
)

_ACTION_PLAN = re.compile(r"^/api/v1/candidates/([a-zA-Z0-9_-]{1,128})/action-plan$")
_MUTABLE_FIELDS = frozenset({
    "owner", "priority", "contact_status", "next_contact_at",
    "reason", "last_result",
})
MAX_WRITE_BYTES = 8 * 1024


def etag_for(payload: dict) -> str:
    raw = json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return '"'+hashlib.sha256(raw).hexdigest()+'"'


def _load_plan(upstream: str, candidate_id: str) -> dict:
    req = Request(
        f"{upstream}/api/v1/candidates/{candidate_id}/action-plan",
        method="GET", headers={"Accept": "application/json"},
    )
    with OPENER.open(req, timeout=8) as r:
        raw = r.read(MAX_RESPONSE_BYTES+1)
    if len(raw)>MAX_RESPONSE_BYTES:
        raise ValueError("Action Plan response too large")
    result=json.loads(raw.decode("utf-8"))
    if not isinstance(result,dict) or result.get("candidate_id")!=candidate_id:
        raise ValueError("SRW Action Plan identity mismatch")
    return result


class SyntheticE2Bridge(ReadOnlyBridge):
    """Use only with a backend started by run_e2_demo.py."""
    allowed_candidate_ids: frozenset[str] = frozenset()
    _write_lock = threading.RLock()
    protocol_version = "HTTP/1.1"

    def _reply_json(self, status: int, data: dict, *, etag: str | None = None) -> None:
        payload=json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.close_connection=True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-SRW-Exploration", "e2-synthetic-only")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        if etag is not None:
            self.send_header("ETag", etag)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _candidate(self) -> str | None:
        parsed=urlsplit(self.path)
        match=_ACTION_PLAN.fullmatch(parsed.path)
        if not match or parsed.query or parsed.fragment:
            return None
        candidate_id=match.group(1)
        return candidate_id if candidate_id in self.allowed_candidate_ids else None

    def do_GET(self) -> None:
        if not self._valid_browser_request():
            return
        parsed=urlsplit(self.path)
        if parsed.path in {"/","/e2-live.html"} and not parsed.query:
            from pathlib import Path
            page=Path(__file__).resolve().parent / "e2-live.html"
            if page.is_file():
                self._reply(200,page.read_bytes(),"text/html; charset=utf-8")
            else:
                self._deny(500,"E2 page is missing")
            return
        if self._candidate() is not None:
            cid=self._candidate()
            try:
                plan=_load_plan(self.upstream,cid)
                self._reply_json(200,plan,etag=etag_for(plan))
            except (ValueError,URLError,HTTPError,TimeoutError,OSError):
                self._reply_json(502,{"error":"E2 Action Plan source unavailable"})
            return
        super().do_GET()

    def do_PATCH(self) -> None:
        if not self._valid_browser_request():
            return
        cid=self._candidate()
        if cid is None:
            self._reply_json(404,{"error":"E2 writes allowed for synthesized candidates only"})
            return
        expected=self.headers.get("If-Match","")
        if not re.fullmatch(r'"[0-9a-f]{64}"',expected):
            self._reply_json(428,{"error":"If-Match with current Action Plan ETag is required"})
            return
        length_text=self.headers.get("Content-Length","")
        try:
            n=int(length_text)
        except (TypeError,ValueError):
            n=-1
        if n<1 or n>MAX_WRITE_BYTES:
            self._reply_json(413,{"error":"E2 request must be bounded nonempty JSON"})
            return
        if not self.headers.get("Content-Type","").split(";",1)[0].strip()=="application/json":
            self._reply_json(415,{"error":"E2 requires application/json"})
            return
        raw=self.rfile.read(n)
        try:
            body=json.loads(raw.decode("utf-8"))
        except (ValueError,UnicodeDecodeError):
            self._reply_json(400,{"error":"Invalid JSON body"})
            return
        if not isinstance(body,dict) or not body or any(k not in _MUTABLE_FIELDS for k in body):
            self._reply_json(422,{"error":"Only safe Action Plan fields are writable in E2"})
            return
        if any(not (isinstance(v,str) or v is None and k=="next_contact_at") for k,v in body.items()):
            self._reply_json(422,{"error":"Action Plan values have invalid types"})
            return
        if body.get("priority") and body["priority"] not in {"normal","today","high","low"}:
            self._reply_json(422,{"error":"Unsupported contact priority"})
            return
        if "reason" in body and len(body["reason"])>1000:
            self._reply_json(422,{"error":"Action Plan reason too long"})
            return

        with self._write_lock:
            try:
                current=_load_plan(self.upstream,cid)
                if etag_for(current)!=expected:
                    self._reply_json(412,{
                        "error":"STALE_ACTION_PLAN",
                        "message":"Another E2 client already changed this plan. Refresh before retry.",
                    },etag=etag_for(current))
                    return
                payload={**body,"actor":"human"}
                req=Request(
                    self.upstream+f"/api/v1/candidates/{cid}/action-plan",
                    data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
                    method="PATCH",headers={"Content-Type":"application/json","Accept":"application/json"},
                )
                with OPENER.open(req, timeout=12) as resp:
                    if resp.status!=200:
                        raise ValueError("Backend refused synthetic Action Plan update")
                    # Always fetch persisted data rather than trusting mutation echo.
                    resp.read(MAX_RESPONSE_BYTES+1)
                after=_load_plan(self.upstream,cid)
                self._reply_json(200,after,etag=etag_for(after))
            except HTTPError as exc:
                self._reply_json(409,{"error":"Synthetic SRW rejected Action Plan update","code":exc.code})
            except (ValueError,URLError,TimeoutError,OSError):
                self._reply_json(502,{"error":"Synthetic SRW Action Plan update unavailable"})


def make_synthetic_e2_server(host: str, port: int, *, upstream: str,
                             candidate_ids: set[str]) -> ThreadingHTTPServer:
    if host!="127.0.0.1" or not candidate_ids:
        raise ValueError("E2 only permits loopback with explicit synthetic candidate IDs")
    # A distinct handler class keeps per-server allowed IDs isolated.
    handler=type("BoundSyntheticE2Bridge",(SyntheticE2Bridge,),{
        "upstream":upstream,
        "allowed_candidate_ids":frozenset(candidate_ids),
        "listen_port":0,
        "_write_lock":threading.RLock(),
    })
    server=ThreadingHTTPServer((host,port),handler)
    handler.listen_port=server.server_address[1]
    return server
