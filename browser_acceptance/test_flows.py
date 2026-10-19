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
            [sys.executable, "-u", str(ROOT / "browser_acceptance" / "serve.py"),
             "--workspace", cls.tmp.name, "--port", str(cls.port)],
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

        self.page.locator("#paste-material").fill("新增合成材料：一份待重新核实的项目反馈。")
        self.page.get_by_role("button", name="保存并发布材料版本").click()
        stale = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertNotEqual(stale["decision_context_hash"], verified["decision_context_hash"])
        self.assertTrue(stale["stale_decision_id"])
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
        renewed = self.get_json(f"/api/v1/candidates/{cid}/workspace")
        self.assertTrue(renewed["decision_ready"])
        self.assertTrue(renewed["stale_decision_id"])
        self.page.once("dialog", lambda dialog: dialog.accept("已复核新增材料，保留原人工决定"))
        self.page.get_by_role("button", name="按当前证据重申").click()
        final = self.get_json(f"/api/v1/candidates/{cid}/decision-history")["decisions"]
        self.assertEqual(len(final), 2)
        self.assertEqual(final[0]["decision"], "advance")
        self.assertTrue(final[0]["is_current_context"])
        self.assertEqual(final[0]["reaffirmed_from_decision_id"], made[0]["decision_id"])
        self.assertTrue(final[1]["stale"])
        self.assertEqual(final[1]["decision_id"], made[0]["decision_id"])
        self.assertFalse(self.console_errors, self.console_errors)


if __name__ == "__main__":
    unittest.main()
