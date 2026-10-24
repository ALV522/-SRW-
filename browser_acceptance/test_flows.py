"""Chromium end-to-end acceptance of real SRW browser + Python API + SQLite.

No mocks of business HTTP responses. All data is synthetic and isolated in a
temporary directory. This is browser acceptance, NOT WPF/WebView2 acceptance.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts" / "browser"
BASE_URL = None


def free_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RecruitmentBrowserAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(prefix="srw-browser-acceptance-")
        cls.port = free_loopback_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.server_log = (EVIDENCE / "synthetic-server.log").open("w", encoding="utf-8")
        env = {**os.environ, "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1"}
        cls.server = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "scripts" / "start_local_web.py"),
             "--workspace", cls.tmp.name, "--port", str(cls.port),
             "--synthetic", "--no-browser"],
            cwd=ROOT, env=env, stdout=cls.server_log,
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(100):
                if cls.server.poll() is not None:
                    raise RuntimeError("Synthetic SRW server exited before readiness")
                try:
                    with urllib.request.urlopen(cls.base + "/health/ready", timeout=0.5) as resp:
                        if resp.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Synthetic SRW server failed health/ready")
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except BaseException:
            cls.server.terminate()
            cls.server.wait(timeout=10)
            cls.server_log.close()
            cls.tmp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "browser"):
            cls.browser.close()
            cls.playwright.stop()
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=10)
        cls.server_log.close()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.context = self.browser.new_context(
            locale="zh-CN",
            viewport={"width": 1440, "height": 900},
            accept_downloads=True,
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.console_errors = []
        self.page.on("pageerror", lambda error: self.console_errors.append(str(error)))

    def tearDown(self) -> None:
        outcome = getattr(self, "_outcome", None)
        errors = getattr(outcome, "errors", []) if outcome else []
        result = getattr(outcome, "result", None) if outcome else None
        if result is not None:
            errors = errors + [x for x in (result.errors + result.failures) if x[0] is self]
        if errors:
            try:
                self.page.screenshot(path=str(EVIDENCE / (self._testMethodName + ".png")), full_page=True)
            except Exception:
                pass
        self.context.close()

    def get_json(self, path: str) -> dict:
        r = self.context.request.get(self.base + path)
        self.assertEqual(r.status, 200, r.text()[:1000])
        return r.json()

    def new_project(self, label: str) -> str:
        title = label + "-" + uuid.uuid4().hex[:8]
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        expect(self.page.locator("#content h1")).to_have_text("工作台总览")
        self.page.get_by_role("button", name="＋ 新建招聘项目").click()
        self.page.locator("#np-title").fill(title)
        self.page.locator("#np-role").fill("产品分析师")
        self.page.locator("#np-summary").fill("模拟招聘业务，不含真实个人数据")
        self.page.get_by_role("button", name="创建并进入项目").click()
        expect(self.page.get_by_role("button", name="四步建岗向导")).to_be_visible()
        matches = [x for x in self.get_json("/api/v1/projects")["projects"] if x["title"] == title]
        self.assertEqual(len(matches), 1)
        return matches[0]["project_id"]

    def new_candidate(self, project_id: str, name: str) -> str:
        self.page.locator(".tabs").get_by_role("button", name="候选人收件").click()
        expect(self.page.get_by_role("button", name="＋ 新增候选人")).to_be_visible()
        self.page.get_by_role("button", name="＋ 新增候选人").click()
        self.page.locator("#cand-name").fill(name)
        self.page.locator("#modal-root").get_by_role("button", name="创建", exact=True).click()
        expect(self.page.locator("#paste-material")).to_be_visible()
        rows = self.get_json(f"/api/v1/projects/{project_id}/candidates?limit=25&offset=0")["candidates"]
        candidates = [c for c in rows if c["display_name"] == name]
        self.assertEqual(len(candidates), 1)
        return candidates[0]["candidate_id"]

    def test_01_job_setup_draft_requires_explicit_human_publish(self) -> None:
        pid = self.new_project("建岗验收")
        self.page.get_by_role("button", name="四步建岗向导").click()
        expect(self.page.locator("#js-role")).to_be_visible()
        self.page.locator("#js-role").fill("高级产品分析师")
        self.page.locator("#js-headcount").fill("2")
        self.page.locator("#js-location").fill("北京")
        self.page.locator("#modal-root").get_by_role("button", name="下一步").click()
        self.page.locator("#js-comp").fill("结构化薪酬测试文本")
        self.page.locator("#modal-root").get_by_role("button", name="下一步").click()
        self.page.locator("#js-owner").fill("模拟招聘专员")
        self.page.locator("#js-hm").fill("模拟业务经理")
        self.page.locator("#js-jd").fill("模拟产品数据分析与客户研究")
        self.page.locator("#modal-root").get_by_role("button", name="下一步").click()
        expect(self.page.locator("#modal-root")).to_contain_text("确认建岗草案")
        self.page.locator("#modal-root").get_by_role("button", name="保存 Draft 并继续标准设计").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        data = self.get_json(f"/api/v1/projects/{pid}/protocol-workspace")
        draft = data.get("draft") or {}
        self.assertEqual(draft.get("recruitment_context", {}).get("headcount"), 2)
        self.assertEqual(draft.get("recruitment_context", {}).get("recruiter_owner"), "模拟招聘专员")
        self.assertNotEqual((data.get("current") or {}).get("recruitment_context", {}).get("headcount"), 2)
        self.assertFalse(self.console_errors, self.console_errors)

    def test_02_candidate_material_contact_and_offer_persist(self) -> None:
        pid = self.new_project("候选人闭环")
        cid = self.new_candidate(pid, "模拟候选人乙")
        self.page.locator("#paste-material").fill("模拟简历：5年产品分析经历，熟悉结构化调研与数据分析。")
        self.page.get_by_role("button", name="保存并发布材料版本").click()
        expect(self.page.locator("#paste-material")).to_be_visible()
        workspace = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertTrue(workspace.get("sources"), workspace)
        self.assertFalse(workspace["decision_ready"])
        self.assertEqual(workspace["decision_context_hash"], "")
        expect(self.page.locator(".source-card")).to_contain_text("结构化调研与数据分析")
        expect(self.page.get_by_role("button", name="记录人工决定")).to_be_disabled()

        self.page.locator(".candidate-workspace-tab").filter(has_text="流程与跟进").click()
        expect(self.page.get_by_role("button", name="编辑下一步")).to_be_visible()
        self.page.get_by_role("button", name="编辑下一步").click()
        self.page.locator("#ap-owner").fill("模拟招聘负责人")
        self.page.locator("#ap-priority").select_option("today")
        self.page.locator("#ap-reason").fill("安排人工电话核实")
        self.page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
        plan = self.get_json(f"/api/v1/candidates/{cid}/action-plan")
        self.assertEqual(plan.get("owner"), "模拟招聘负责人")
        self.assertEqual(plan.get("reason"), "安排人工电话核实")

        self.page.locator(".candidate-workspace-tab").filter(has_text="Offer").click()
        expect(self.page.get_by_role("button", name="创建 Offer")).to_be_disabled()
        # Backend enforces actual human pipeline transitions. Test through the UI,
        # not by bypassing the stage gate with direct API calls.
        for next_stage in ("shortlisted", "interview"):
            self.page.get_by_role("button", name="推进阶段").click()
            self.page.locator("#stage-next").select_option(next_stage)
            self.page.locator("#stage-reason").fill("合成验收：人工推进")
            self.page.locator("#modal-root").get_by_role("button", name="确认推进").click()
            expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        stage = self.get_json(f"/api/v1/candidates/{cid}/pipeline")
        self.assertEqual(stage["current_stage"], "interview")
        expect(self.page.get_by_role("button", name="创建 Offer")).to_be_enabled()
        self.page.get_by_role("button", name="创建 Offer").click()
        self.page.locator("#offer-title").fill("产品分析师")
        self.page.locator("#offer-start").fill("2026-12-01")
        self.page.locator("#offer-comp").fill("仅用于验收的模拟薪酬")
        self.page.locator("#modal-root").get_by_role("button", name="创建 Offer 草案").click()
        offers = self.get_json(f"/api/v1/candidates/{cid}/offers")
        self.assertEqual(len(offers.get("offers", [])), 1)
        self.assertEqual(offers["offers"][0]["status"], "draft")
        pipeline = self.get_json(f"/api/v1/candidates/{cid}/pipeline")
        self.assertNotEqual(pipeline["current_stage"], "hired")
        self.assertFalse(self.console_errors, self.console_errors)

    def test_08_archive_restore_preserves_material_and_live_funnel(self) -> None:
        """Archive through real controls; retain evidence and restore live counts.

        Removing the Core dashboard archive filters makes the final rendered
        funnel assertion fail. No business writes are seeded through the API.
        """
        pid = self.new_project("归档恢复验收")
        cid = self.new_candidate(pid, "模拟归档候选人")
        material = "合成归档材料：三年产品分析经验，历史证据必须保留。"
        self.page.locator("#paste-material").fill(material)
        self.page.get_by_role("button", name="保存并发布材料版本").click()
        expect(self.page.locator(".source-card")).to_contain_text(material)
        before = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        counts = self.get_json("/api/v1/dashboard")
        self.page.get_by_role("button", name="← 返回项目工作区").click()
        self.page.locator(".tabs").get_by_role("button", name="候选人收件").click()
        row = self.page.locator("tbody tr").filter(has_text=cid)
        row.get_by_role("button", name="归档", exact=True).click()
        expect(row).to_have_count(0)
        archived = self.get_json("/api/v1/dashboard")
        self.assertEqual(archived["metrics"]["candidates"], counts["metrics"]["candidates"] - 1)
        self.assertEqual(archived["candidates_by_stage"]["new"], counts["candidates_by_stage"]["new"] - 1)

        self.page.locator("#cand-archive").select_option("archived")
        self.page.get_by_role("button", name="应用筛选").click()
        expect(row).to_be_visible()
        row.get_by_role("button", name="恢复", exact=True).click()
        expect(row).to_have_count(0)
        restored = self.get_json("/api/v1/dashboard")
        self.assertEqual(restored["metrics"]["candidates"], counts["metrics"]["candidates"])
        self.assertEqual(restored["candidates_by_stage"]["new"], counts["candidates_by_stage"]["new"])
        self.page.locator("#cand-archive").select_option("active")
        self.page.get_by_role("button", name="应用筛选").click()
        row.get_by_role("button", name="工作区", exact=True).click()
        expect(self.page.locator(".source-card")).to_contain_text(material)
        self.assertEqual(self.get_json(f"/api/v1/candidates/{cid}/workspace")["sources"], before["sources"])

        self.page.get_by_role("button", name="← 返回项目工作区").click()
        self.page.once("dialog", lambda dialog: dialog.dismiss())
        self.page.get_by_role("button", name="归档项目", exact=True).click()
        self.assertEqual(self.get_json("/api/v1/dashboard")["metrics"]["candidates"], counts["metrics"]["candidates"])
        self.page.once("dialog", lambda dialog: dialog.accept())
        with self.page.expect_response(lambda response: response.url.endswith(f"/projects/{pid}/archive") and response.request.method == "POST") as response:
            self.page.get_by_role("button", name="归档项目", exact=True).click()
        self.assertEqual(response.value.status, 200)
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        expect(self.page.locator("#content h1")).to_have_text("工作台总览")
        funnel = self.page.locator(".funnel-step").filter(has=self.page.locator("span", has_text="新候选人"))
        expect(funnel.locator("strong")).to_have_text(str(counts["candidates_by_stage"]["new"] - 1))
        self.assertEqual(self.get_json(f"/api/v1/candidates/{cid}/workspace")["sources"], before["sources"])
        self.assertFalse(self.console_errors, self.console_errors)

    def test_03_interview_is_a_real_persisted_workflow(self) -> None:
        pid = self.new_project("面试闭环")
        cid = self.new_candidate(pid, "模拟候选人丙")
        self.page.locator(".candidate-workspace-tab").filter(has_text="流程与跟进").click()
        self.page.get_by_role("button", name="＋ 面试排期").click()
        self.page.locator("#e-title").fill("模拟一面")
        self.page.locator("#e-time").fill("2026-11-12T14:00")
        self.page.locator("#e-interviewer").fill("模拟面试官")
        self.page.locator("#e-location").fill("线上")
        self.page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
        events = self.get_json(f"/api/v1/candidates/{cid}/events")["events"]
        self.assertTrue(any(x.get("title") == "模拟一面" for x in events), events)
        expect(self.page.locator(".candidate-workspace-content")).to_contain_text("模拟一面")
        self.assertFalse(self.console_errors, self.console_errors)


    def test_04_independent_interview_scorecards_cannot_be_overwritten(self) -> None:
        pid = self.new_project("独立面试评价")
        cid = self.new_candidate(pid, "模拟候选人-双面试官")
        self.page.locator(".candidate-workspace-tab").filter(has_text="流程与跟进").click()
        self.page.get_by_role("button", name="＋ 面试排期").click()
        self.page.locator("#e-title").fill("合成双人结构化面试")
        self.page.locator("#e-time").fill("2026-11-20T10:00")
        self.page.locator("#e-interviewer").fill("模拟面试官甲")
        self.page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        events = self.get_json(f"/api/v1/candidates/{cid}/events")["events"]
        matching = [x for x in events if x["title"] == "合成双人结构化面试"]
        self.assertEqual(len(matching), 1)
        eid = matching[0]["event_id"]

        for evaluator, rating, recommendation in (
            ("模拟面试官甲", "strong", "推进至下一轮"),
            ("模拟面试官乙", "concern", "需进一步核实"),
        ):
            self.page.get_by_role("button", name="独立 Scorecard").click()
            expect(self.page.locator("#sc-evaluator")).to_be_visible()
            self.page.locator("#sc-evaluator").fill(evaluator)
            self.page.locator("#sc-key").fill("research_reasoning")
            self.page.locator("#sc-rating").select_option(rating)
            self.page.locator("#sc-rec").fill(recommendation)
            self.page.locator("#sc-observation").fill("模拟行为观察，纯合成数据")
            self.page.locator("#sc-support").fill("模拟支持性证据")
            self.page.locator("#sc-counter").fill("模拟需要复核的内容")
            self.page.get_by_role("button", name="提交并锁定").click()
            expect(self.page.locator("#modal-root .modal")).to_have_count(0)

        saved = self.get_json(f"/api/v1/events/{eid}/scorecards")
        self.assertEqual(len(saved["scorecards"]), 2, saved)
        self.assertEqual({x["state"] for x in saved["scorecards"]}, {"submitted"})
        self.assertEqual({x["evaluator"] for x in saved["scorecards"]},
                         {"模拟面试官甲", "模拟面试官乙"})
        self.assertTrue(saved["criteria"]["research_reasoning"]["disagreement"])
        self.assertIn("no automatic average", saved["note"].lower())

        # The real API must refuse mutating already-submitted human evaluations.
        blocked = self.context.request.post(
            self.base + f"/api/v1/events/{eid}/scorecards",
            data=json.dumps({
                "evaluator": "模拟面试官甲",
                "feedback": [{"criterion_key": "research_reasoning", "rating": "acceptable"}],
                "recommendation": "非法重写", "submit": True,
            }, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
        )
        self.assertTrue(400 <= blocked.status < 500, blocked.text())
        after = self.get_json(f"/api/v1/events/{eid}/scorecards")
        self.assertEqual(after["scorecards"], saved["scorecards"])
        pipeline = self.get_json(f"/api/v1/candidates/{cid}/pipeline")
        self.assertNotEqual(pipeline["current_stage"], "hired")
        self.assertFalse(self.console_errors, self.console_errors)

    def test_05_offer_lifecycle_requires_human_transitions_and_never_auto_hires(self) -> None:
        pid = self.new_project("Offer 状态闭环")
        cid = self.new_candidate(pid, "模拟候选人-Offer")
        self.page.locator(".candidate-workspace-tab").filter(has_text="Offer").click()
        expect(self.page.get_by_role("button", name="创建 Offer")).to_be_disabled()
        for stage in ("shortlisted", "interview"):
            self.page.get_by_role("button", name="推进阶段").click()
            self.page.locator("#stage-next").select_option(stage)
            self.page.locator("#stage-reason").fill("合成验收人工变更")
            self.page.locator("#modal-root").get_by_role("button", name="确认推进").click()
            expect(self.page.locator("#modal-root .modal")).to_have_count(0)

        expect(self.page.get_by_role("button", name="创建 Offer")).to_be_enabled()
        self.page.get_by_role("button", name="创建 Offer").click()
        self.page.locator("#offer-title").fill("合成产品分析师 Offer")
        self.page.locator("#offer-start").fill("2026-12-01")
        self.page.locator("#offer-comp").fill("仅合成测试，无真实薪酬")
        self.page.get_by_role("button", name="创建 Offer 草案").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        offers = self.get_json(f"/api/v1/candidates/{cid}/offers")["offers"]
        self.assertEqual(len(offers), 1)
        oid = offers[0]["offer_id"]
        self.assertEqual(offers[0]["status"], "draft")

        # Unauthorized state-skipping must fail in the API, not merely in the UI.
        illegal = self.context.request.post(
            self.base + f"/api/v1/offers/{oid}/status",
            data=json.dumps({"status": "accepted", "actor": "human",
                             "reason": "跳过审批的非法状态"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertTrue(400 <= illegal.status < 500, illegal.text())
        self.assertEqual(self.get_json(f"/api/v1/candidates/{cid}/offers")["offers"][0]["status"], "draft")

        for expected in ("approved", "sent", "accepted"):
            self.page.get_by_role("button", name="更新状态").click()
            expect(self.page.locator("#offer-status")).to_be_visible()
            next_allowed = self.page.locator("#offer-status option")
            options = next_allowed.evaluate_all("(rows) => rows.map(x => x.value)")
            self.assertIn(expected, options)
            self.assertNotIn("draft", options[1:])
            if expected == "approved":
                self.assertNotIn("accepted", options)
                self.assertNotIn("sent", options)
            self.page.locator("#offer-status").select_option(expected)
            self.page.locator("#offer-status-reason").fill("合成测试：人工状态批准/发送/接收")
            self.page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
            expect(self.page.locator("#modal-root .modal")).to_have_count(0)
            persisted = self.get_json(f"/api/v1/candidates/{cid}/offers")["offers"][0]
            self.assertEqual(persisted["status"], expected)

        expect(self.page.get_by_role("button", name="更新状态")).to_be_disabled()
        pipeline = self.get_json(f"/api/v1/candidates/{cid}/pipeline")
        self.assertEqual(pipeline["current_stage"], "interview")
        history = self.get_json(f"/api/v1/candidates/{cid}/decision-history")
        self.assertEqual(history["decisions"], [])
        self.assertFalse(self.console_errors, self.console_errors)

    def test_06_human_verification_decision_stale_and_explicit_reaffirmation(self) -> None:
        pid = self.new_project("人工证据决策")
        self.page.locator(".tabs").get_by_role("button", name="建岗与标准").click()
        expect(self.page.get_by_role("button", name="＋ 添加标准")).to_be_visible()
        self.page.get_by_role("button", name="＋ 添加标准").click()
        expect(self.page.locator(".criterion-row")).to_have_count(1)
        self.page.locator(".criterion-row .c-name").fill("合成研究经验")
        self.page.locator(".criterion-row .c-definition").fill("仅依据明确的人工核实记录确认")
        self.page.locator(".criterion-row .c-critical").check()
        self.page.locator(".criterion-row .c-verify").check()
        self.page.locator(".criterion-row .c-probe").fill("请说明项目与个人职责")
        key = self.page.locator(".criterion-row").get_attribute("data-criterion-key")
        self.page.get_by_role("button", name="保存草案").click()
        expect(self.page.get_by_role("button", name="发布当前标准")).to_be_visible()
        protocol = self.get_json(f"/api/v1/projects/{pid}/protocol-workspace")
        criterion = (protocol.get("draft") or {})["criteria"][0]
        key = criterion["criterion_key"]
        self.page.once("dialog", lambda dialog: dialog.accept())
        self.page.get_by_role("button", name="发布当前标准").click()
        expect(self.page.locator(".tabs").get_by_role("button", name="候选人收件")).to_be_visible()
        self.assertEqual(
            self.get_json(f"/api/v1/projects/{pid}/protocol-workspace")["current"]["criteria"][0]["criterion_key"],
            key,
        )

        cid = self.new_candidate(pid, "模拟证据候选人")
        self.page.locator("#paste-material").fill("原始模拟履历：完成过产品用户研究项目。")
        self.page.get_by_role("button", name="保存并发布材料版本").click()
        before = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertTrue(before["decision_context_hash"])
        self.assertFalse(before["decision_ready"])
        self.assertFalse(before["claims"])
        self.assertEqual(before["blocking_count"], 1)

        # Server must not allow advancing without a grounded judgment,
        # even when a client bypasses the UI.
        blocked = self.context.request.post(
            self.base + f"/api/v1/candidates/{cid}/decision",
            data=json.dumps({"decision": "advance", "reason": "不核实直接推进", "actor": "human"},
                            ensure_ascii=False),
            headers={"Content-Type": "application/json"},
        )
        self.assertTrue(400 <= blocked.status < 500, blocked.text())
        self.assertEqual(self.get_json(f"/api/v1/candidates/{cid}/decision-history")["decisions"], [])

        self.page.get_by_role("button", name="人工核实").click()
        self.page.locator("#v-status").select_option("met")
        self.page.locator("#v-evidence").select_option("strong")
        self.page.locator("#v-reason").fill("模拟面试人工核实：明确说明研究过程与职责")
        self.page.get_by_role("button", name="保存人工核实").click()
        verified = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertNotEqual(before["decision_context_hash"], verified["decision_context_hash"])
        self.assertTrue(verified["decision_ready"])
        self.assertEqual(len(verified["criteria"]), 1)
        self.assertTrue(any(c["authority"] == "human" for c in verified["claims"]))
        self.assertTrue(any(s["source_kind"] == "verification_note" for s in verified["sources"]))
        self.assertEqual(verified["criteria"][0]["criterion_key"], key)
        self.assertNotEqual(verified["criteria"][0]["status_label"], "仍需核实")

        self.page.get_by_role("button", name="记录人工决定").click()
        self.page.locator("#d-decision").select_option("advance")
        self.page.locator("#d-reason").fill("模拟人工最终决定：可以推进")
        self.page.get_by_role("button", name="提交人工决定").click()
        made = self.get_json(f"/api/v1/candidates/{cid}/decision-history")["decisions"]
        self.assertEqual(len(made), 1)
        self.assertTrue(made[0]["is_current_context"])
        self.assertEqual(made[0]["decision"], "advance")
        # saveDecision triggers an async full candidateDrawer render. Wait for
        # the new decision to appear before interacting with the replacement DOM.
        expect(self.page.locator(".kpi-value").first).to_contain_text("已决定")

        self.page.locator("#paste-material").fill("新增合成材料：一份待重新核实的项目反馈。")
        expect(self.page.locator("#paste-material")).to_have_value("新增合成材料：一份待重新核实的项目反馈。")
        # Re-render while the operator is typing: unsent material must
        # remain in this candidate's editor and not become an empty POST.
        self.page.evaluate("() => window.setCandidateSection('evidence')")
        expect(self.page.locator("#paste-material")).to_have_value("新增合成材料：一份待重新核实的项目反馈。")
        # Observe the real request completion, instead of treating a stale UI
        # render as persistence failure.
        with self.page.expect_response(
            lambda response: response.url.endswith(f"/api/v1/candidates/{cid}/sources/text")
            and response.request.method == "POST"
        ) as capture:
            self.page.get_by_role("button", name="保存并发布材料版本").click()
        response = capture.value
        self.assertEqual(response.status, 200, response.text())
        stored = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertEqual(len(stored["sources"]), 3, stored)
        expect(self.page.locator(".source-card")).to_have_count(3)
        stale = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertNotEqual(stale["decision_context_hash"], verified["decision_context_hash"])
        self.assertTrue(stale["stale_decision_id"])
        self.assertFalse(stale["decision_reaffirmable"])
        expect(self.page.get_by_role("button", name="按当前证据重申")).to_be_disabled()
        self.assertNotEqual(stale["decision_label"], "继续推进")
        history = self.get_json(f"/api/v1/candidates/{cid}/decision-history")["decisions"]
        self.assertTrue(history[0]["stale"])
        self.assertFalse(history[0]["is_current_context"])

        rejected = self.context.request.post(
            self.base + f"/api/v1/candidates/{cid}/decisions/reaffirm",
            data=json.dumps({"actor": "human", "reason": "跳过新增证据复核"}, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
        )
        self.assertTrue(400 <= rejected.status < 500, rejected.text())
        self.assertEqual(len(self.get_json(f"/api/v1/candidates/{cid}/decision-history")["decisions"]), 1)

        self.page.get_by_role("button", name="人工核实").click()
        self.page.locator("#v-status").select_option("met")
        self.page.locator("#v-evidence").select_option("strong")
        self.page.locator("#v-reason").fill("人工重查新增材料：研究职责得到确认")
        self.page.get_by_role("button", name="保存人工核实").click()
        expect(self.page.locator(".source-card")).to_have_count(4)
        renewed = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertTrue(renewed["decision_ready"])
        self.assertTrue(renewed["stale_decision_id"])
        self.assertTrue(renewed["decision_reaffirmable"])
        expect(self.page.get_by_role("button", name="按当前证据重申")).to_be_enabled()
        self.page.once("dialog", lambda dialog: dialog.accept("已复核新增材料，保留原人工决定"))
        with self.page.expect_response(
            lambda response: response.url.endswith(f"/api/v1/candidates/{cid}/decisions/reaffirm")
            and response.request.method == "POST"
        ) as capture:
            self.page.get_by_role("button", name="按当前证据重申").click()
        self.assertEqual(capture.value.status, 200, capture.value.text())
        final = self.get_json(f"/api/v1/candidates/{cid}/decision-history")["decisions"]
        self.assertEqual(len(final), 2)
        self.assertEqual(final[0]["decision"], "advance")
        self.assertTrue(final[0]["is_current_context"])
        self.assertEqual(final[0]["reaffirmed_from_decision_id"], made[0]["decision_id"])
        self.assertTrue(final[1]["stale"])
        self.assertEqual(final[1]["decision_id"], made[0]["decision_id"])
        self.assertFalse(self.console_errors, self.console_errors)


    def test_07_published_protocol_change_invalidates_previous_human_decision(self) -> None:
        """New verification-critical hiring standard invalidates old approval."""
        pid = self.new_project("标准版本失效")
        self.page.locator(".tabs").get_by_role("button", name="建岗与标准").click()
        self.page.get_by_role("button", name="＋ 添加标准").click()
        expect(self.page.locator(".criterion-row")).to_have_count(1)
        first = self.page.locator(".criterion-row").first
        first.locator(".c-name").fill("模拟分析项目经验")
        first.locator(".c-definition").fill("人工证据核实为准")
        first.locator(".c-critical").check()
        first.locator(".c-verify").check()
        first.locator(".c-probe").fill("请说明项目交付")
        self.page.get_by_role("button", name="保存草案").click()
        expect(self.page.get_by_role("button", name="发布当前标准")).to_be_visible()
        self.page.once("dialog", lambda dialog: dialog.accept())
        with self.page.expect_response(
            lambda response: "/api/v1/protocol-revisions/" in response.url
            and response.url.endswith("/publish")
            and response.request.method == "POST"
        ) as first_publish:
            self.page.get_by_role("button", name="发布当前标准").click()
        self.assertEqual(first_publish.value.status, 200, first_publish.value.text())
        protocol_v1 = self.get_json(f"/api/v1/projects/{pid}/protocol-workspace")
        key = protocol_v1["current"]["criteria"][0]["criterion_key"]

        cid = self.new_candidate(pid, "标准变更测试候选人")
        self.page.locator("#paste-material").fill("合成简历：产品分析与研究项目。")
        with self.page.expect_response(
            lambda response: response.url.endswith(f"/api/v1/candidates/{cid}/sources/text")
            and response.request.method == "POST"
        ) as published_material:
            self.page.get_by_role("button", name="保存并发布材料版本").click()
        self.assertEqual(published_material.value.status, 200)
        expect(self.page.locator(".source-card")).to_have_count(1)
        self.page.get_by_role("button", name="人工核实").click()
        self.page.locator("#v-status").select_option("met")
        self.page.locator("#v-evidence").select_option("strong")
        self.page.locator("#v-reason").fill("人工核实模拟研究记录")
        self.page.get_by_role("button", name="保存人工核实").click()
        expect(self.page.locator(".source-card")).to_have_count(2)
        current = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertTrue(current["decision_ready"])
        self.assertEqual(current["criteria"][0]["criterion_key"], key)
        self.page.get_by_role("button", name="记录人工决定").click()
        self.page.locator("#d-decision").select_option("advance")
        self.page.locator("#d-reason").fill("人工确认旧标准已经满足")
        self.page.get_by_role("button", name="提交人工决定").click()
        expect(self.page.locator(".candidate-summary-strip")).to_contain_text("继续推进")
        original_history = self.get_json(
            f"/api/v1/candidates/{cid}/decision-history"
        )["decisions"]
        self.assertEqual(len(original_history), 1)
        self.assertTrue(original_history[0]["is_current_context"])
        before = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        old_context = before["decision_context_hash"]
        old_sources = {x["source_id"] for x in before["sources"]}

        # Return to the project standards UI and create a new Draft from
        # the published protocol. An unchanged document/material version
        # must not allow the old decision to survive a new critical criterion.
        self.page.evaluate("() => window.closeCandidateWorkspace()")
        self.page.locator(".tabs").get_by_role("button", name="建岗与标准").click()
        expect(self.page.get_by_role(
            "button", name="基于当前版本创建新草案"
        )).to_be_visible()
        self.page.get_by_role("button", name="基于当前版本创建新草案").click()
        expect(self.page.locator(".criterion-row")).to_have_count(1)
        self.page.get_by_role("button", name="＋ 添加标准").click()
        expect(self.page.locator(".criterion-row")).to_have_count(2)
        second = self.page.locator(".criterion-row").last
        second.locator(".c-name").fill("新增合成合规标准")
        second.locator(".c-definition").fill("新标准必须重新核验，不继承旧决定")
        second.locator(".c-critical").check()
        second.locator(".c-verify").check()
        second.locator(".c-probe").fill("新增人工核实要求")
        self.page.get_by_role("button", name="保存草案").click()
        expect(self.page.get_by_role("button", name="发布当前标准")).to_be_visible()
        second_protocol = self.get_json(f"/api/v1/projects/{pid}/protocol-workspace")
        self.assertEqual(len(second_protocol["draft"]["criteria"]), 2)
        self.page.once("dialog", lambda dialog: dialog.accept())
        with self.page.expect_response(
            lambda response: "/api/v1/protocol-revisions/" in response.url
            and response.url.endswith("/publish")
            and response.request.method == "POST"
        ) as second_publish:
            self.page.get_by_role("button", name="发布当前标准").click()
        self.assertEqual(second_publish.value.status, 200, second_publish.value.text())

        protocol_v2 = self.get_json(f"/api/v1/projects/{pid}/protocol-workspace")
        self.assertEqual(len(protocol_v2["current"]["criteria"]), 2)
        self.assertNotEqual(
            protocol_v1["current_revision_id"],
            protocol_v2["current_revision_id"],
        )
        changed = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertEqual({x["source_id"] for x in changed["sources"]}, old_sources)
        self.assertNotEqual(changed["decision_context_hash"], old_context)
        self.assertFalse(changed["decision_ready"])
        self.assertGreaterEqual(changed["blocking_count"], 1)
        self.assertTrue(changed["stale_decision_id"])
        self.assertFalse(changed["decision_reaffirmable"])
        decision_history = self.get_json(
            f"/api/v1/candidates/{cid}/decision-history"
        )["decisions"]
        self.assertEqual(len(decision_history), 1)
        self.assertTrue(decision_history[0]["stale"])
        self.assertFalse(decision_history[0]["is_current_context"])

        # No client may bypass the new critical hiring standard.
        rejected = self.context.request.post(
            self.base + f"/api/v1/candidates/{cid}/decisions/reaffirm",
            data=json.dumps(
                {"actor": "human", "reason": "未按新增标准核实就重申"}, ensure_ascii=False
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertTrue(400 <= rejected.status < 500, rejected.text())
        self.assertEqual(
            len(self.get_json(f"/api/v1/candidates/{cid}/decision-history")["decisions"]),
            1,
        )
        self.page.evaluate("(candidateId) => window.openCandidate(candidateId)", cid)
        expect(self.page.get_by_role("button", name="按当前证据重申")).to_be_disabled()
        self.assertFalse(self.console_errors, self.console_errors)


    def test_09_windows_first_use_health_and_unmaterialized_candidate(self) -> None:
        """Real browser: readiness indicator agrees with backend; new intake has no spurious assessment 409."""
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        expect(self.page.locator("#service-health-text")).to_have_text("服务正常")
        expect(self.page.locator("#side-health")).to_contain_text("服务已就绪")
        icon = self.page.locator("link[rel='icon']").get_attribute("href")
        self.assertTrue(icon and icon.startswith("data:image/svg+xml,"), icon)
        assessment_responses = []
        self.page.on("response", lambda r: assessment_responses.append(r.status)
                     if "/assessment" in r.url and "/api/v1/candidates/" in r.url else None)
        pid = self.new_project("Windows首次启动")
        cid = self.new_candidate(pid, "未收件的模拟候选人")
        expect(self.page.locator("#paste-material")).to_be_visible()
        self.assertFalse(assessment_responses,
                         f"No material/decision context: skip optional Assessment API, got {assessment_responses}")
        data = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertFalse(data["decision_context_hash"])
        self.assertFalse(data["decision_ready"])
        self.assertFalse(self.console_errors, self.console_errors)


    def test_10_completed_interview_correction_replaces_current_evidence_via_ui(self) -> None:
        """Operator revises interview evidence in the real browser without mutating Source history."""
        pid = self.new_project("面试记录更正")
        cid = self.new_candidate(pid, "模拟面试记录校正候选人")
        self.page.locator(".candidate-workspace-tab").filter(has_text="流程与跟进").click()
        self.page.get_by_role("button", name="＋ 面试排期").click()
        self.page.locator("#e-state").select_option("completed")
        self.page.locator("#e-title").fill("模拟已完成面试")
        self.page.locator("#e-questions").fill(" | 请说明工作经验 | 核对客观情况")
        self.page.locator("#e-notes").fill("原先面试记录")
        self.page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        original = self.get_json(f"/api/v1/candidates/{cid}/events")["events"]
        self.assertEqual(len(original), 1)
        self.assertTrue(original[0]["editable_evidence_source"])
        old_source = original[0]["source_id"]
        before = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertEqual({x["source_id"] for x in before["sources"]}, {old_source})
        expect(self.page.get_by_role("button", name="更正证据记录")).to_be_visible()
        self.page.get_by_role("button", name="更正证据记录").click()
        expect(self.page.locator("#corr-notes")).to_have_value("原先面试记录")
        self.page.locator("#corr-notes").fill("更正后的面试记录")
        self.page.locator('[data-corr-answer="0"]').fill("实际为合成回答")
        self.page.get_by_role("button", name="保存更正并发布新证据").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        latest = self.get_json(f"/api/v1/candidates/{cid}/events")["events"][0]
        self.assertNotEqual(latest["source_id"], old_source)
        current = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        sources = current["sources"]
        self.assertEqual({x["source_id"] for x in sources}, {latest["source_id"]})
        self.assertIn("更正后的面试记录", sources[0]["text_preview"])
        self.assertIn("实际为合成回答", sources[0]["text_preview"])
        self.assertFalse(self.console_errors, self.console_errors)


if __name__ == "__main__":
    unittest.main()
