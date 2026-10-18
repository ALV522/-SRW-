"""Real C11 + two Chromium browser contexts + disposable E2 Action Plan CAS.

E2 is NOT a production transactional concurrency guarantee. This verifies the
restricted synthetic write facade and the genuine SRW upsert + audit chain,
with exactly one temporary SQLAlchemy/SQLite data source.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from playwright.sync_api import expect,sync_playwright
from test_real_backend import ROOT,HERE,EVIDENCE,free_port,request_json,wait_ready

sys.path.insert(0,str(HERE))
from e2_synthetic_bridge import make_synthetic_e2_server


class E2TwoBrowserContexts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix="srw-e2-browser-disposable-")
        cls.port=free_port()
        cls.api=f"http://127.0.0.1:{cls.port}"
        cls.log=(EVIDENCE/"e2-synthetic-core.log").open("w",encoding="utf-8")
        cls.backend=None
        cls.server=None
        cls.server_thread=None
        cls.browser=None
        cls.playwright=None
        try:
            env={**os.environ,"SRW_SYNTHETIC_BROWSER_ACCEPTANCE":"1","PYTHONUNBUFFERED":"1"}
            cls.backend=subprocess.Popen(
                [sys.executable,"-u",str(ROOT/"browser_acceptance"/"serve.py"),
                 "--workspace",cls.temp.name,"--port",str(cls.port)],
                cwd=ROOT,env=env,stdout=cls.log,stderr=subprocess.STDOUT,
            )
            wait_ready(cls.api+"/health/ready",[cls.backend])
            proj=request_json(cls.api,"/api/v1/projects",{
                "title":"E2双浏览器合成项目-"+uuid.uuid4().hex[:7],
                "role_title":"合成招聘运营",
                "brief_summary":"只在临时数据库中测试 Action Plan 并发写入",
            })
            cls.pid=proj["project_id"]
            candidate=request_json(cls.api,f"/api/v1/projects/{cls.pid}/candidates",{
                "display_name":"模拟候选人（E2并发）",
            })
            cls.cid=candidate["candidate_id"]
            cls.server=make_synthetic_e2_server(
                "127.0.0.1",0,upstream=cls.api,candidate_ids={cls.cid},
            )
            cls.web=f"http://127.0.0.1:{cls.server.server_address[1]}"
            cls.server_thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
            cls.server_thread.start()
            cls.playwright=sync_playwright().start()
            cls.browser=cls.playwright.chromium.launch(headless=True)
        except BaseException:
            cls.cleanup()
            raise

    @classmethod
    def cleanup(cls):
        if cls.browser:
            cls.browser.close();cls.browser=None
        if cls.playwright:
            cls.playwright.stop();cls.playwright=None
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            if cls.server_thread:cls.server_thread.join(timeout=5)
            cls.server=None
        if cls.backend:
            cls.backend.terminate()
            try:cls.backend.wait(timeout=8)
            except subprocess.TimeoutExpired:
                cls.backend.kill();cls.backend.wait(timeout=5)
            cls.backend=None
        if cls.log:cls.log.close();cls.log=None
        if cls.temp:cls.temp.cleanup();cls.temp=None

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    def setUp(self):
        self.contexts=[]
        self.errors=[]

    def tearDown(self):
        outcome=getattr(self,"_outcome",None)
        result=getattr(outcome,"result",None) if outcome else None
        failures=[x for x in (result.errors+result.failures) if x[0] is self] if result else []
        if failures:
            for i,ctx in enumerate(self.contexts):
                try:
                    ctx.pages[0].screenshot(
                        path=str(EVIDENCE/f"{self._testMethodName}-{i}.png"),full_page=True
                    )
                except Exception:pass
        for ctx in self.contexts:ctx.close()

    def new_client(self):
        ctx=self.browser.new_context(locale="zh-CN",viewport={"width":1280,"height":900})
        self.contexts.append(ctx)
        page=ctx.new_page()
        page.set_default_timeout(10000)
        page.on("pageerror",lambda err:self.errors.append(str(err)))
        page.goto(self.web+"/",wait_until="domcontentloaded")
        expect(page.locator("#api-state")).to_have_text("LIVE · web · E2 synthetic")
        page.locator("[data-page=e2]").click()
        expect(page.locator("#e2-candidate")).to_be_visible()
        page.locator("#e2-candidate").select_option(self.cid)
        expect(page.locator("#e2-save")).to_be_visible()
        return page

    def test_01_two_real_browser_clients_reject_stale_write(self):
        a=self.new_client()
        b=self.new_client()
        a.locator("#e2-owner").fill("模拟招聘专员 A")
        a.locator("#e2-reason").fill("A 在浏览器端完成合成跟进")
        a.locator("#e2-save").click()
        expect(a.locator("#e2-editor")).to_contain_text("条件写入成功")
        self.assertEqual(
            request_json(self.api,f"/api/v1/candidates/{self.cid}/action-plan")["owner"],
            "模拟招聘专员 A"
        )
        b.locator("#e2-owner").fill("模拟招聘专员 B")
        b.locator("#e2-reason").fill("不应该覆盖 A")
        b.locator("#e2-save").click()
        expect(b.locator("#e2-editor")).to_contain_text("412 STALE_ACTION_PLAN")
        self.assertEqual(
            request_json(self.api,f"/api/v1/candidates/{self.cid}/action-plan")["owner"],
            "模拟招聘专员 A"
        )
        b.locator("#e2-reload").click()
        expect(b.locator("#e2-owner")).to_have_value("模拟招聘专员 A")
        b.locator("#e2-owner").fill("模拟招聘专员 B")
        b.locator("#e2-reason").fill("在当前版本重新确认的跟进")
        b.locator("#e2-save").click()
        expect(b.locator("#e2-editor")).to_contain_text("条件写入成功")
        self.assertEqual(
            request_json(self.api,f"/api/v1/candidates/{self.cid}/action-plan")["owner"],
            "模拟招聘专员 B"
        )
        dashboard=request_json(self.api,"/api/v1/dashboard")
        events=[x for x in dashboard.get("recent",[])
                if x.get("event_type")=="CANDIDATE_ACTION_PLAN_UPDATED"
                and x.get("entity_id")==self.cid]
        self.assertGreaterEqual(len(events),2)
        self.assertFalse(self.errors,self.errors)
        a.screenshot(path=str(EVIDENCE/"e2-two-client-conditional-write.png"),full_page=True)

    def test_02_e2_cannot_mutate_other_objects_or_candidates(self):
        page=self.new_client()
        rest=page.context.request
        response=rest.post(self.web+"/api/v1/projects",data={"title":"FORBIDDEN"})
        self.assertEqual(response.status,405)
        bad=rest.patch(
            self.web+"/api/v1/candidates/unknown/action-plan",
            headers={"If-Match":'"'+"0"*64+'"',"Content-Type":"application/json"},
            data=json.dumps({"owner":"bad"}),
        )
        self.assertEqual(bad.status,404)
        sensitive=rest.get(self.web+"/api/v1/system/backups")
        self.assertEqual(sensitive.status,404)
        self.assertFalse(self.errors,self.errors)


if __name__=="__main__":
    unittest.main()
