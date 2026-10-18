"""E2 guarded synthetic Action Plan proxy tests with a fake SRW backend."""
from __future__ import annotations

import importlib.util
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from e2_synthetic_bridge import make_synthetic_e2_server


class MutablePlanSRW(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    state={
        "candidate_id":"synthetic-1","project_id":"p1","owner":"",
        "priority":"normal","contact_status":"to_contact",
        "next_contact_at":None,"reason":"","last_result":"",
    }
    mutations=0

    def log_message(self,*_args):pass

    def send_json(self,status,body):
        raw=json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Connection","close")
        self.end_headers()
        self.close_connection=True
        self.wfile.write(raw)

    def do_GET(self):
        if self.path=="/api/v1/candidates/synthetic-1/action-plan":
            return self.send_json(200,type(self).state)
        self.send_json(404,{"error":"not found"})

    def do_PATCH(self):
        if self.path!="/api/v1/candidates/synthetic-1/action-plan":
            return self.send_json(404,{})
        length=int(self.headers.get("Content-Length","0"))
        obj=json.loads(self.rfile.read(length))
        type(self).state={**self.state,**obj}
        type(self).mutations+=1
        self.send_json(200,type(self).state)


class E2ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core=ThreadingHTTPServer(("127.0.0.1",0),MutablePlanSRW)
        cls.core_thread=threading.Thread(target=cls.core.serve_forever,daemon=True)
        cls.core_thread.start()
        cls.bridge=make_synthetic_e2_server(
            "127.0.0.1",0,upstream=f"http://127.0.0.1:{cls.core.server_address[1]}",
            candidate_ids={"synthetic-1"},
        )
        cls.bridge_thread=threading.Thread(target=cls.bridge.serve_forever,daemon=True)
        cls.bridge_thread.start()
        cls.base=f"http://127.0.0.1:{cls.bridge.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.bridge.shutdown();cls.bridge.server_close();cls.bridge_thread.join(timeout=5)
        cls.core.shutdown();cls.core.server_close();cls.core_thread.join(timeout=5)

    def setUp(self):
        MutablePlanSRW.mutations=0
        MutablePlanSRW.state={
            "candidate_id":"synthetic-1","project_id":"p1","owner":"",
            "priority":"normal","contact_status":"to_contact",
            "next_contact_at":None,"reason":"","last_result":"",
        }

    def req(self,path,method="GET",body=None,headers=None):
        content=json.dumps(body).encode("utf-8") if body is not None else None
        hs={"Accept":"application/json"}
        if body is not None:hs["Content-Type"]="application/json"
        hs.update(headers or {})
        req=Request(self.base+path,data=content,headers=hs,method=method)
        try:
            with urlopen(req,timeout=5) as resp:
                raw=resp.read()
                try: payload=json.loads(raw)
                except ValueError: payload={"text":raw.decode("utf-8",errors="replace")}
                return resp.status,payload,resp.headers.get("ETag","")
        except HTTPError as exc:
            raw=exc.read()
            try: payload=json.loads(raw)
            except ValueError: payload={"text":raw.decode("utf-8",errors="replace")}
            return exc.code,payload,exc.headers.get("ETag","")

    def test_two_clients_share_etag_and_stale_writer_rejected(self):
        path="/api/v1/candidates/synthetic-1/action-plan"
        old_a=self.req(path);old_b=self.req(path)
        self.assertEqual(old_a[0],200)
        self.assertEqual(old_a[2],old_b[2])
        self.assertTrue(old_a[2].startswith('"'))
        saved=self.req(path,"PATCH",{"owner":"Client A","priority":"high"},{"If-Match":old_a[2]})
        self.assertEqual(saved[0],200,saved)
        self.assertEqual(saved[1]["owner"],"Client A")
        rejected=self.req(path,"PATCH",{"owner":"Client B"},{"If-Match":old_b[2]})
        self.assertEqual(rejected[0],412,rejected)
        self.assertEqual(rejected[1]["error"],"STALE_ACTION_PLAN")
        self.assertEqual(MutablePlanSRW.state["owner"],"Client A")
        self.assertEqual(MutablePlanSRW.mutations,1)
        self.assertNotEqual(saved[2],old_a[2])

    def test_two_simultaneous_old_etags_only_one_writer_commits(self):
        path="/api/v1/candidates/synthetic-1/action-plan"
        initial=self.req(path)[2]
        def write(owner):
            return self.req(path,"PATCH",{"owner":owner},{"If-Match":initial})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,["Concurrent A","Concurrent B"]))
        self.assertEqual(sorted(x[0] for x in results),[200,412],results)
        self.assertEqual(MutablePlanSRW.mutations,1)
        self.assertIn(MutablePlanSRW.state["owner"],{"Concurrent A","Concurrent B"})

    def test_missing_if_match_unsafe_fields_and_other_methods_denied(self):
        path="/api/v1/candidates/synthetic-1/action-plan"
        self.assertEqual(self.req(path,"PATCH",{"owner":"bad"})[0],428)
        tag=self.req(path)[2]
        self.assertEqual(self.req(path,"PATCH",{"decision":"hired"},{"If-Match":tag})[0],422)
        self.assertEqual(self.req(path,"PATCH",{"priority":"urgent"},{"If-Match":tag})[0],422)
        self.assertEqual(self.req(path,"POST",{"owner":"bad"})[0],405)
        self.assertEqual(self.req("/api/v1/candidates/other/action-plan")[0],404)
        self.assertEqual(MutablePlanSRW.mutations,0)

    def test_e2_page_served_and_host_boundary_enforced(self):
        req=Request(self.base+"/")
        with urlopen(req,timeout=5) as resp:
            self.assertEqual(resp.status,200)
            self.assertIn(b"E2",resp.read())
        status,_,_=self.req("/api/v1/candidates/synthetic-1/action-plan",
                            headers={"Origin":"https://attacker.example"})
        self.assertEqual(status,403)
        self.assertEqual(MutablePlanSRW.mutations,0)


if __name__=="__main__":
    unittest.main()
