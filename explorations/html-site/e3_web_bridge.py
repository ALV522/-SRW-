"""E3 browser carrier: forwards only synthetic Action Plan conditional writes.

Unlike E2, this does NOT validate CAS in the proxy. If-Match travels unchanged
to E3's temporary C11 Core; the database transaction decides stale vs commit.
Nothing here can attach to a pre-existing SRW workspace or EXE.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request

from serve_e1 import ReadOnlyBridge, OPENER
from e2_synthetic_bridge import SyntheticE2Bridge, MAX_WRITE_BYTES

ACTION_PLAN=re.compile(r"^/api/v1/candidates/([a-zA-Z0-9_-]{1,128})/action-plan$")
CORE_TAG=re.compile(r'^"e3-ap-v(0|[1-9][0-9]{0,17})"$')
MAX_CORE_REPLY_BYTES=1024*1024


class SyntheticE3Bridge(SyntheticE2Bridge):
    def _core_request(self, method: str, payload: bytes | None = None,
                      etag: str = ""):
        headers={"Accept":"application/json","User-Agent":"SRW-E3-Synthetic-Lab"}
        if payload is not None:
            headers["Content-Type"]="application/json"
        if etag:
            headers["If-Match"]=etag
        req=Request(self.upstream+self.path,data=payload,method=method,headers=headers)
        try:
            with OPENER.open(req,timeout=12) as response:
                raw=response.read(MAX_CORE_REPLY_BYTES+1)
                status=response.status
                tag=response.headers.get("ETag")
        except HTTPError as exc:
            raw=exc.read(MAX_CORE_REPLY_BYTES+1)
            status=exc.code
            tag=exc.headers.get("ETag")
        if len(raw)>MAX_CORE_REPLY_BYTES:
            raise ValueError("Core response exceeds synthetic E3 bounds")
        body=json.loads(raw.decode("utf-8"))
        if not isinstance(body,dict):
            raise ValueError("E3 response must be an object")
        if tag is not None and CORE_TAG.fullmatch(tag) is None:
            raise ValueError("Invalid atomic Core ETag")
        return status,body,tag

    def do_GET(self):
        if not self._valid_browser_request():
            return
        parsed=urlsplit(self.path)
        if parsed.path in {"/","/e3-live.html"} and not parsed.query:
            doc=Path(__file__).resolve().parent/"e3-live.html"
            if not doc.is_file():
                self._deny(500,"E3 HTML missing")
            else:
                self._reply(200,doc.read_bytes(),"text/html; charset=utf-8")
            return
        if self._candidate() is not None:
            try:
                status,body,tag=self._core_request("GET")
                self._reply_json(status,body,etag=tag)
            except (URLError,HTTPError,ValueError,TimeoutError,OSError):
                self._reply_json(502,{"error":"E3 Core Action Plan GET failed"})
            return
        # Preserve the original reviewed GET-only API allowlist.
        ReadOnlyBridge.do_GET(self)

    def do_PATCH(self):
        if not self._valid_browser_request():
            return
        cid=self._candidate()
        if cid is None:
            self._reply_json(404,{"error":"Unknown E3 synthetic candidate"})
            return
        expected=self.headers.get("If-Match","")
        if CORE_TAG.fullmatch(expected) is None:
            self._reply_json(428,{"error":"Current E3 If-Match ETag required"})
            return
        if self.headers.get("Content-Type","").split(";",1)[0].strip()!="application/json":
            self._reply_json(415,{"error":"application/json required"})
            return
        try:
            length=int(self.headers.get("Content-Length","-1"))
        except ValueError:
            length=-1
        if length<1 or length>MAX_WRITE_BYTES:
            self._reply_json(413,{"error":"E3 request body not bounded"})
            return
        payload=self.rfile.read(length)
        try:
            body=json.loads(payload.decode("utf-8"))
            if not isinstance(body,dict):
                raise ValueError("Expected object")
        except (ValueError,UnicodeDecodeError):
            self._reply_json(400,{"error":"E3 JSON body invalid"})
            return
        try:
            # Do not hold a Python proxy lock: the E3 Core itself owns
            # transactional revision enforcement.
            status,data,tag=self._core_request("PATCH",payload,expected)
            self._reply_json(status,data,etag=tag)
        except (URLError,HTTPError,ValueError,TimeoutError,OSError):
            self._reply_json(502,{"error":"E3 atomic Core PATCH unavailable"})


def make_synthetic_e3_server(host: str,port: int,*,upstream: str,
                             candidate_ids: set[str]) -> ThreadingHTTPServer:
    if host!="127.0.0.1" or not candidate_ids:
        raise ValueError("E3 only binds loopback and fresh candidate IDs")
    handler=type("BoundSyntheticE3Bridge",(SyntheticE3Bridge,),{
        "upstream":upstream,
        "allowed_candidate_ids":frozenset(candidate_ids),
        "listen_port":0,
    })
    server=ThreadingHTTPServer((host,port),handler)
    handler.listen_port=server.server_address[1]
    return server
