"""E5 real-C11 + Chromium attach security and Core identity tests.

Does NOT attach to a Windows Native EXE or use real records. Each run starts
one disposable C11 Core and two capability-protected browser carrier origins.
"""
from __future__ import annotations

import unittest
from urllib.error import URLError

from playwright.sync_api import expect,sync_playwright

from test_real_backend import EVIDENCE,request_json
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
from e5_owner import launch_e5_owner
from run_e5_demo import client_with_cookies,request_client


class E5ProtectedAttachBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EVIDENCE.mkdir(parents=True,exist_ok=True)
        cls.owner_context=launch_e5_owner()
        cls.owner=cls.owner_context.__enter__()
        cls.playwright=sync_playwright().start()
        cls.browser=cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            cls.owner_context.__exit__(None,None,None)

    def setUp(self):
        self.contexts=[]
        self.errors=[]
        # A bootstrap capability is consumed once. Give each independent
        # browser test freshly issued carrier capabilities (same durable Core).
        for name in ("web","desktop_surrogate"):
            self.owner.detach(name)
            self.owner.attach(name)

    def tearDown(self):
        for ctx in self.contexts:
            ctx.close()

    def fresh_context(self):
        ctx=self.browser.new_context(
            locale="zh-CN",viewport={"width":1280,"height":880}
        )
        self.contexts.append(ctx)
        page=ctx.new_page()
        page.set_default_timeout(12000)
        page.on("pageerror",lambda exc:self.errors.append(str(exc)))
        return page

    def attach_browser(self,carrier: str):
        page=self.fresh_context()
        page.goto(self.owner.attach_url(carrier),wait_until="domcontentloaded")
        expect(page.locator("#api-state")).to_have_text("LIVE · web · E5 attached synthetic")
        self.assertNotIn("/attach/",page.url)
        return page

    def enter_plan(self,page):
        page.locator("[data-page=e3]").click()
        page.locator("#e3-candidate").select_option(self.owner.cid)
        expect(page.locator("#e3-save")).to_be_visible()

    def test_01_unauthorized_and_cross_carrier_access_denied(self):
        web=self.owner.url("web")
        desktop=self.owner.url("desktop_surrogate")
        untrusted=client_with_cookies()
        for url in (web,desktop):
            for path in ("/","/api/v1/projects",
                         f"/api/v1/candidates/{self.owner.cid}/action-plan"):
                status,_,_=request_client(untrusted,url,path)
                self.assertEqual(status,403,(url,path,status))
        status,_,_=request_client(
            untrusted,desktop,"/attach/"+self.owner.attach_url("web").split("/attach/")[1]
        )
        self.assertEqual(status,403)
        status,_,_=request_client(untrusted,web,"/attach/invalid")
        self.assertEqual(status,403)
        page=self.fresh_context()
        response=page.goto(web+"/",wait_until="domcontentloaded")
        self.assertEqual(response.status,403)

        # Browser attach cookie is HttpOnly and absent from JS/document URLs.
        page=self.attach_browser("web")
        cookies=page.context.cookies(web+"/")
        attached=[x for x in cookies if x["name"].startswith("srw_e5_")]
        self.assertEqual(len(attached),1)
        self.assertTrue(attached[0]["httpOnly"])
        self.assertEqual(attached[0]["sameSite"],"Strict")
        self.assertEqual(page.evaluate("document.cookie"),"")
        # Replaying the redeemed bootstrap URL must not grant a new session,
        # while the already attached tab remains functional.
        replay=request_client(client_with_cookies(),web,
                              "/attach/"+self.owner.attach_url("web").split("/attach/")[1])
        self.assertEqual(replay[0],403)
        page.reload()
        expect(page.locator("#api-state")).to_have_text("LIVE · web · E5 attached synthetic")
        self.assertFalse(self.errors,self.errors)

    def test_02_two_authorized_browsers_share_core_and_revoke_on_detach(self):
        web=self.attach_browser("web")
        desktop=self.attach_browser("desktop_surrogate")
        self.enter_plan(web)
        self.enter_plan(desktop)
        web.locator("#e3-owner").fill("E5 专属附着 Web")
        web.locator("#e3-reason").fill("限合成数据")
        web.locator("#e3-save").click()
        expect(web.locator("#e3-editor")).to_contain_text("条件写入成功")
        desktop.locator("#e3-reload").click()
        expect(desktop.locator("#e3-owner")).to_have_value("E5 专属附着 Web")

        old_origin=self.owner.url("web")
        self.owner.detach("web")
        self.assertIsNone(self.owner.core.poll())
        # The other UI uses exactly the same Core after first UI exits.
        desktop.locator("#e3-reload").click()
        expect(desktop.locator("#e3-owner")).to_have_value("E5 专属附着 Web")

        new_origin=self.owner.attach("web")
        new_web=new_origin.split("/attach/")[0]
        # Unauthenticated clients cannot reach the newly attached carrier.
        self.assertEqual(request_client(client_with_cookies(),new_web,"/")[0],403)
        web2=self.attach_browser("web")
        self.enter_plan(web2)
        expect(web2.locator("#e3-owner")).to_have_value("E5 专属附着 Web")
        self.assertFalse(self.errors,self.errors)
        desktop.screenshot(path=str(EVIDENCE/"e5-protected-two-carriers.png"),full_page=True)

    def test_03_pinned_runtime_identity_change_fails_closed(self):
        page=self.attach_browser("desktop_surrogate")
        origin=self.owner.url("desktop_surrogate")
        status,_,_=request_client(client_with_cookies(),origin,"/")
        self.assertEqual(status,403)
        cls=self.owner._servers["desktop_surrogate"].RequestHandlerClass
        old=dict(cls._identity)
        try:
            cls._identity={**old,"instanceId":"incorrect-core-instance"}
            response=page.context.request.get(origin+"/api/v1/runtime/info")
            self.assertEqual(response.status,503)
            response=page.context.request.patch(
                origin+f"/api/v1/candidates/{self.owner.cid}/action-plan",
                data='{"owner":"MUST_NOT_PERSIST"}',
                headers={"Content-Type":"application/json","If-Match":'"e3-ap-v0"'}
            )
            self.assertEqual(response.status,503)
        finally:
            cls._identity=old
        # Both requests were rejected before they reached the business Core.
        expect(page.locator("#api-state")).to_have_text("LIVE · web · E5 attached synthetic")
        self.assertFalse(self.errors,self.errors)

    def test_99_dead_core_is_not_replaced_silently(self):
        origin=self.owner.url("desktop_surrogate")
        page=self.attach_browser("desktop_surrogate")
        self.owner.core.terminate()
        self.owner.core.wait(timeout=10)
        response=page.context.request.get(origin+"/api/v1/runtime/info",timeout=10000)
        self.assertEqual(response.status,503)
        response=page.context.request.get(origin+"/",timeout=10000)
        self.assertEqual(response.status,503)
        self.assertFalse(self.errors,self.errors)


if __name__=="__main__":
    unittest.main()
