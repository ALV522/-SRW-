"""Real Chromium E4: two independent UI carrier origins, ONE disposable Core.

Desktop is a browser surrogate here, NOT a Windows WPF/WebView2 EXE.
Tests exercise Core identity, shared Action Plan, UI detachment and reattach.
"""
from __future__ import annotations

import unittest

from playwright.sync_api import expect,sync_playwright
from test_real_backend import EVIDENCE,request_json

import sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from e4_shared_core import launch_shared_e4


class E4TwoCarrierBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        cls.owner=launch_shared_e4()
        cls.session=cls.owner.__enter__()
        cls.playwright=sync_playwright().start()
        cls.browser=cls.playwright.chromium.launch(headless=True)
        cls.web=cls.session.url("web")
        cls.desktop=cls.session.url("desktop_surrogate")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            cls.owner.__exit__(None,None,None)

    def setUp(self):
        self.contexts=[]
        self.errors=[]

    def tearDown(self):
        for context in self.contexts:
            context.close()

    def page_at(self,origin):
        ctx=self.browser.new_context(locale="zh-CN",viewport={"width":1360,"height":850})
        self.contexts.append(ctx)
        page=ctx.new_page()
        page.on("pageerror",lambda exc:self.errors.append(str(exc)))
        page.set_default_timeout(10000)
        page.goto(origin+"/",wait_until="domcontentloaded")
        expect(page.locator("#api-state")).to_have_text("LIVE · web · E3 atomic synthetic")
        return page

    def select_plan(self,page):
        page.locator("[data-page=e3]").click()
        page.locator("#e3-candidate").select_option(self.session.cid)
        expect(page.locator("#e3-save")).to_be_visible()

    def test_01_real_two_carrier_browser_identity_and_shared_write(self):
        web=self.page_at(self.web)
        desktop=self.page_at(self.desktop)
        identity_a=request_json(self.web,"/api/v1/runtime/info")
        identity_b=request_json(self.desktop,"/api/v1/runtime/info")
        for field in ("instanceId","sessionId","dataScopeId"):
            self.assertEqual(identity_a[field],identity_b[field],field)

        self.select_plan(web)
        self.select_plan(desktop)
        web.locator("#e3-owner").fill("同一核心的 Web 浏览器")
        web.locator("#e3-reason").fill("只存在一次数据库级写入")
        web.locator("#e3-save").click()
        expect(web.locator("#e3-editor")).to_contain_text("条件写入成功")
        desktop.locator("#e3-reload").click()
        expect(desktop.locator("#e3-owner")).to_have_value("同一核心的 Web 浏览器")
        persisted=request_json(self.session.api,f"/api/v1/candidates/{self.session.cid}/action-plan")
        self.assertEqual(persisted["owner"],"同一核心的 Web 浏览器")
        desktop.screenshot(path=str(EVIDENCE/"e4-shared-core-two-carriers.png"),full_page=True)
        self.assertFalse(self.errors,self.errors)

    def test_02_independent_ui_detach_keeps_core_and_other_browser_alive(self):
        core_pid=self.session.core.pid
        desktop=self.page_at(self.desktop)
        self.select_plan(desktop)
        self.session.detach("web")
        self.assertEqual(self.session.core.pid,core_pid)
        self.assertIsNone(self.session.core.poll())
        desktop.locator("#e3-reload").click()
        expect(desktop.locator("#e3-editor")).to_contain_text(self.session.cid)

        self.web=self.session.attach("web")
        web=self.page_at(self.web)
        self.select_plan(web)
        expected=request_json(self.session.api,f"/api/v1/candidates/{self.session.cid}/action-plan")
        expect(web.locator("#e3-owner")).to_have_value(expected["owner"])
        self.assertFalse(self.errors,self.errors)


if __name__=="__main__":
    unittest.main()
