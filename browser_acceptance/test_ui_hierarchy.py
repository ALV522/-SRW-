"""#235 deterministic checks for the workbench information hierarchy.

These assert the *structure* the operator needs, not a screenshot:
the next action is on the first screen, there is exactly one back entry per
context, counters are visually demoted and the tool row is secondary.

Browser acceptance on the synthetic workspace. NOT WPF/WebView2 acceptance.
"""
from __future__ import annotations

import json
import sqlite3
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
VIEWPORTS = ((1440, 900), (1366, 768))


def free_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class UiHierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="srw-ui235-", ignore_cleanup_errors=True)
        cls.port = free_loopback_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        evidence = ROOT / "artifacts" / "browser"
        evidence.mkdir(parents=True, exist_ok=True)
        cls.log = open(evidence / "ui235-server.log", "w", encoding="utf-8")
        cls.server = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "scripts" / "start_local_web.py"),
             "--workspace", cls.tmp.name, "--port", str(cls.port),
             "--synthetic", "--no-browser"],
            cwd=ROOT, env={**os.environ, "SRW_SYNTHETIC_BROWSER_ACCEPTANCE": "1"},
            stdout=cls.log, stderr=subprocess.STDOUT,
        )
        for _ in range(150):
            if cls.server.poll() is not None:
                raise RuntimeError("synthetic server exited early")
            try:
                with urllib.request.urlopen(cls.base + "/health/ready", timeout=0.5) as resp:
                    if resp.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("synthetic server not ready")
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
        cls.log.close()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.context = self.browser.new_context(locale="zh-CN")
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)

    def tearDown(self) -> None:
        self.context.close()

    def _post(self, path, payload):
        r = self.context.request.post(self.base + path, data=json.dumps(payload, ensure_ascii=False),
                                     headers={"Content-Type": "application/json"})
        self.assertEqual(r.status, 200, r.text()[:400])
        return r.json()

    def _seed_project(self) -> tuple[str, str]:
        title = "层级-" + uuid.uuid4().hex[:5]
        pid = self._post("/api/v1/projects", {"title": title, "role_title": "分析师",
                                              "brief_summary": "合成"})["project_id"]
        forked = self.context.request.post(self.base + f"/api/v1/projects/{pid}/protocol-drafts")
        revision = forked.json()["revision_id"]
        payload = {
            "brief": {"title": "合成岗位", "summary": "层级"},
            "criteria": [{"criterion_key": "research_reasoning", "name": "研究推理",
                          "definition": "合成", "decision_critical": True,
                          "verification_required": False, "verification_probes": ["样例"], "weight": 1}],
            "assessment_stages": [{"stage_key": "interview", "name": "面试",
                                   "criteria": ["research_reasoning"]}],
            "decision_policy": {"human_final": True},
        }
        self.context.request.patch(self.base + f"/api/v1/protocol-revisions/{revision}",
                                   data=json.dumps({"payload": payload}, ensure_ascii=False),
                                   headers={"Content-Type": "application/json"})
        self.context.request.post(self.base + f"/api/v1/protocol-revisions/{revision}/publish")
        self._post(f"/api/v1/projects/{pid}/candidates", {"display_name": "层级候选人"})
        return pid, title

    def _open_project(self, title: str) -> None:
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        expect(self.page.locator("#content h1")).to_be_visible()
        self.page.locator("aside .nav-item", has_text="招聘项目").click()
        self.page.wait_for_timeout(200)
        self.page.locator("tr").filter(has_text=title).get_by_role(
            "button", name="进入工作区").click()
        self.page.wait_for_timeout(500)

    def test_next_action_is_the_first_block_on_screen(self) -> None:
        _pid, title = self._seed_project()
        for width, height in VIEWPORTS:
            with self.subTest(viewport=f"{width}x{height}"):
                self.page.set_viewport_size({"width": width, "height": height})
                self._open_project(title)
                card = self.page.locator(".next-action-card")
                expect(card).to_be_visible()
                box = card.bounding_box()
                self.assertIsNotNone(box)
                # First screen means: inside the viewport, above the halfway line,
                # and before the counter grid and tool row in document order.
                self.assertLess(box["y"], height * 0.5,
                                f"{width}x{height}: next action starts at y={box['y']}")
                order = self.page.evaluate("""() => {
                  const body = document.getElementById('project-tab-body');
                  const first = body.querySelector('.next-action-card');
                  if (!first) return false;
                  const others = [...body.querySelectorAll('.kpi-card, .actions, .panel')];
                  return others.every(o => (first.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
                }""")
                self.assertTrue(order, f"{width}x{height}: next action is not the first block")

    def test_exactly_one_back_entry_per_context(self) -> None:
        _pid, title = self._seed_project()
        self.page.set_viewport_size({"width": 1440, "height": 900})
        self._open_project(title)
        # Project overview: the top bar carries the only back control.
        self.assertTrue(self.page.locator("#top-back").is_visible())
        self.assertEqual(
            self.page.get_by_role("button", name="返回项目列表").count(), 0,
            "the duplicated in-banner back button must be gone",
        )
        backs = self.page.evaluate("""() => [...document.querySelectorAll('.btn,button')]
          .filter(b => /返回/.test(b.textContent || '')).map(b => (b.textContent||'').trim())""")
        self.assertLessEqual(len(backs), 1, f"more than one back entry: {backs}")

        # Candidate workspace: still exactly one, and it belongs to the top bar.
        self.page.locator(".tabs").get_by_role("button", name="候选人").click()
        self.page.wait_for_timeout(300)
        self.page.locator("tr[data-candidate-id]").first.get_by_role(
            "button", name="打开工作台").click()
        self.page.wait_for_timeout(600)
        self.assertTrue(self.page.locator("#top-back").is_visible())
        self.assertIn("层级候选人", self.page.locator("#top-crumb").inner_text())

    def test_counters_are_demoted_and_tool_row_is_secondary(self) -> None:
        _pid, title = self._seed_project()
        self.page.set_viewport_size({"width": 1440, "height": 900})
        self._open_project(title)
        shadows = self.page.evaluate("""() => [...document.querySelectorAll('.kpi-card')]
          .map(e => getComputedStyle(e).boxShadow)""")
        self.assertTrue(shadows, "expected KPI cards to exist")
        for shadow in shadows:
            self.assertIn(shadow, ("none", ""), f"KPI card still elevated: {shadow}")
        sizes = self.page.evaluate("""() => [...document.querySelectorAll('.actions.tool-row .btn')]
          .map(e => parseFloat(getComputedStyle(e).fontSize))""")
        self.assertTrue(sizes, "expected the demoted tool row to exist")
        for size in sizes:
            self.assertLessEqual(size, 12.5, f"tool row button still primary-sized: {size}px")

    def test_next_action_is_still_first_on_a_second_visit(self) -> None:
        pid, title = self._seed_project()
        self.page.set_viewport_size({"width": 1440, "height": 900})
        self._open_project(title)
        expect(self.page.locator(".next-action-card")).to_be_visible()
        # Leave the project (dashboard) and re-open it: the card must not depend on
        # a first-render side effect or on the list page's scroll position.
        self.page.locator("aside .nav-item", has_text="今日待办").click()
        expect(self.page.locator("#content h1")).to_have_text("今日待办")
        self.page.evaluate("pid => window.openProject(pid)", pid)
        self.page.wait_for_timeout(500)
        card = self.page.locator(".next-action-card")
        expect(card).to_be_visible()
        box = card.bounding_box()
        self.assertIsNotNone(box, "next action disappeared on the second visit")
        self.assertLess(box["y"], 500, f"next action moved down to y={box['y']} on revisit")


    def test_dashboard_direct_project_entry_preserves_candidate_and_active_nav(self) -> None:
        # Reproduces #237 exact HEAD Chromium regression: openProject from
        # dashboard must enter the projects route before scoped candidate reads.
        pid, title = self._seed_project()
        cid = self._post(f"/api/v1/projects/{pid}/candidates",
                         {"display_name": "跨页入口候选人"})["candidate_id"]
        self.page.goto(self.base + "/v1", wait_until="domcontentloaded")
        self.page.wait_for_function("Boolean(window.openProject && window.openCandidate)")
        self.page.evaluate("""async ([pid,cid]) => {
          await window.openProject(pid);
          await window.openCandidate(cid);
        }""", [pid, cid])
        expect(self.page.locator("#content h1")).to_have_text("跨页入口候选人")
        expect(self.page.locator(".candidate-steps")).to_be_visible()
        expect(self.page.locator("aside .nav-item.active")).to_contain_text("招聘项目")
        expect(self.page.locator("#top-crumb")).to_contain_text(title)
        self.page.locator("#top-back").click()
        expect(self.page.locator(".project-banner")).to_be_visible()
        expect(self.page.locator("#top-crumb")).not_to_contain_text("跨页入口候选人")

    def test_topbar_workbench_and_candidate_identity_are_scoped(self) -> None:
        pid, title = self._seed_project()
        second = self._post(f"/api/v1/projects/{pid}/candidates",
                            {"display_name": "第二位合成候选人"})["candidate_id"]
        self._open_project(title)
        self.page.locator("#top-crumb .crumb-link", has_text="工作台").click()
        expect(self.page.locator("#top-title")).to_have_text("今日待办")
        expect(self.page.locator("#content h1")).to_have_text("今日待办")
        expect(self.page.locator("#top-back:visible")).to_have_count(0)
        expect(self.page.locator("#top-crumb .crumb-link")).to_have_count(0)
        self.page.locator("aside .nav-item", has_text="招聘项目").click()
        expect(self.page.locator("#content h1")).to_have_text("招聘项目")
        expect(self.page.locator(".project-banner")).to_have_count(0)
        expect(self.page.locator("tr").filter(has_text=title)).to_have_count(1)

        self.page.locator("tr").filter(has_text=title).get_by_role(
            "button", name="进入工作区").click()
        expect(self.page.locator("#top-crumb")).to_contain_text(title)
        # A direct link may target a candidate outside the current filtered
        # candidateRows. The breadcrumb must come from that scoped Core GET.
        self.page.evaluate("cid => window.openCandidate(cid)", second)
        expect(self.page.locator("#content h1")).to_have_text("第二位合成候选人")
        expect(self.page.locator("#top-crumb")).to_contain_text("第二位合成候选人")
        expect(self.page.locator(".candidate-workspace-breadcrumb button")).to_have_count(0)
        expect(self.page.locator("#top-back:visible")).to_have_count(1)
        self.page.locator("#top-back").click()
        expect(self.page.locator(".project-banner")).to_be_visible()
        self.assertNotIn("第二位合成候选人", self.page.locator("#top-crumb").inner_text())
        self.page.locator("#top-back").click()
        expect(self.page.locator("#content h1")).to_have_text("招聘项目")
        expect(self.page.locator("#top-back:visible")).to_have_count(0)



    def test_project_scheduled_interview_targets_exact_candidate_and_event(self) -> None:
        """Real Core + Chromium: one project overview click targets B's event, never A."""
        from datetime import datetime, timedelta, timezone

        pid, title = self._seed_project()
        cid_b = self._post(f"/api/v1/projects/{pid}/candidates",
                           {"display_name": "面试目标乙"})["candidate_id"]
        foreign_pid, _ = self._seed_project()
        foreign_cid = self._post(f"/api/v1/projects/{foreign_pid}/candidates",
                                 {"display_name": "外项目候选人"})["candidate_id"]
        self._open_project(title)
        self.page.locator(".tabs").get_by_role("button", name="候选人").click()
        row = self.page.locator("tr[data-candidate-id]").filter(has_text="面试目标乙")
        row.get_by_role("button", name="打开工作台").click()
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        self.page.get_by_role("button", name="＋ 面试排期").click()
        self.page.locator("#e-title").fill("乙的真实合成面试")
        future = datetime.now(timezone.utc) + timedelta(days=30)
        self.page.locator("#e-time").fill(future.strftime("%Y-%m-%dT%H:%M"))
        self.page.locator("#modal-root").get_by_role("button", name="保存", exact=True).click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        events = self.context.request.get(self.base + f"/api/v1/candidates/{cid_b}/events").json()["events"]
        eid = next(x["event_id"] for x in events if x["title"] == "乙的真实合成面试")
        self.page.locator("#top-back").click()
        self.page.locator(".tabs").get_by_role("button", name="概览").click()
        expect(self.page.locator(".next-action-card").get_by_role(
            "button", name="查看相关列表")).to_be_visible()
        scheduled = self.page.locator(f'[data-scheduled-event="{eid}"]')
        expect(scheduled).to_have_count(1)
        # Start the operator click budget from the project list, not a hidden
        # script-invoked workspace. Enter project = click 1.
        self.page.locator("#top-back").click()
        self.page.locator("tr").filter(has_text=title).get_by_role(
            "button", name="进入工作区").click()
        expect(self.page.locator(f'[data-scorecard-event="{eid}"]')).to_have_count(1)

        # A foreign candidate cannot reuse B's event ID to enter this project.
        self.page.evaluate("""async ([pid,cid,eid]) =>
            await window.openScheduledInterview(pid,cid,eid)""",
            [pid, foreign_cid, eid])
        expect(self.page.locator(".project-banner")).to_be_visible()
        expect(self.page.locator(".candidate-workspace-page")).to_have_count(0)
        self.page.evaluate("""async ([pid,cid,eid]) =>
            await window.openScheduledInterview(pid,cid,eid,true)""",
            [pid, foreign_cid, eid])
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)

        # Project overview → exact B Scorecard = click 2; submit = click 3.
        # No UUID/criterion_key is typed by the operator.
        self.page.locator(f'[data-scorecard-event="{eid}"]').click()
        expect(self.page.locator("#content h1")).to_have_text("面试目标乙")
        modal = self.page.locator("#modal-root .modal")
        expect(modal.locator("#sc-criteria .criterion-block")).to_have_count(1)
        modal.locator("#sc-evaluator").fill("合成面试官乙")
        modal.locator(".c-rating").select_option("strong")
        modal.locator(".c-obs").fill("合成观察：清晰描述了方法")
        modal.locator("#sc-rec").fill("advance")
        modal.get_by_role("button", name="提交并锁定").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with sqlite3.connect(Path(self.tmp.name) / "data" / "srw_v1.db") as db:
            rows = db.execute(
                "SELECT candidate_id, event_id, feedback_json FROM interview_scorecard_submission "
                "WHERE event_id=?", (eid,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], cid_b)
            self.assertEqual(rows[0][1], eid)
            self.assertEqual(json.loads(rows[0][2])[0]["criterion_key"], "research_reasoning")
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM interview_scorecard_submission WHERE candidate_id=?",
                (foreign_cid,)).fetchone()[0], 0)
        # Reopen the browser page and verify persisted, independently scoped
        # history rather than relying on the modal's in-memory state.
        # Scorecard submission does not complete the scheduled interview.
        # Verify the server projection independently of the browser bootstrap.
        scheduled_after = self.context.request.get(
            self.base + f"/api/v1/projects/{pid}/pipeline").json()["scheduled_events"]
        self.assertIn(eid, {item["event_id"] for item in scheduled_after})
        self.page.reload(wait_until="domcontentloaded")
        # A module-level window.openProject exists before init() finishes its
        # async business-session/health/dashboard bootstrap. Calling it at
        # that point races init(), which can replace the project DOM later.
        expect(self.page.locator("#content h1")).to_have_text("今日待办")
        # Reopen through visible HR navigation, not a scripted deep link.
        self.page.locator("aside .nav-item", has_text="招聘项目").click()
        self.page.locator("tr").filter(has_text=title).get_by_role(
            "button", name="进入工作区").click()
        expect(self.page.locator(".project-banner")).to_be_visible()
        expect(self.page.locator(f'[data-scorecard-event="{eid}"]')).to_have_count(1)
        self.page.locator(f'[data-scorecard-event="{eid}"]').click()
        expect(self.page.locator("#modal-root .scorecard-history")).to_contain_text("合成面试官乙")
        self.page.locator("#modal-root .modal-head .x").click()
        self.page.locator("#top-back").click()
        expect(self.page.locator(".next-action-card")).to_be_visible()

        scheduled = self.page.locator(f'[data-scheduled-event="{eid}"]')
        scheduled.click()
        expect(self.page.locator("#content h1")).to_have_text("面试目标乙")
        expect(self.page.locator(f'.timeline-item[data-event-id="{eid}"]')).to_contain_text(
            "乙的真实合成面试")
        expect(self.page.locator(".candidate-step.active")).to_contain_text("面试")
        self.page.locator("#top-back").click()
        expect(self.page.locator(".next-action-card")).to_be_visible()
        expect(self.page.locator(".candidate-workspace-page")).to_have_count(0)
        self.assertEqual(self.context.request.get(
            self.base + f"/api/v1/candidates/{foreign_cid}/events").json()["events"], [])


    def test_primary_action_uses_exact_candidate_and_rejects_stale_material(self) -> None:
        """Real Core targets one candidate; a stale card cannot open the wrong person."""
        pid, title = self._seed_project()
        self._post(f"/api/v1/projects/{pid}/candidates", {"display_name": "材料待补乙"})
        foreign_pid, _ = self._seed_project()
        foreign_target = self.context.request.get(
            self.base + f"/api/v1/projects/{foreign_pid}/pipeline"
        ).json()["workflow_summary"]["next_action"]["target"]["candidate_id"]
        self._open_project(title)
        pipeline = self.context.request.get(
            self.base + f"/api/v1/projects/{pid}/pipeline").json()
        action = pipeline["workflow_summary"]["next_action"]
        self.assertEqual(action["key"], "complete_materials")
        first = action["target"]["candidate_id"]
        self.assertNotEqual(first, foreign_target)
        expect(self.page.locator("#project-next-action")).to_contain_text("补齐材料")

        # Another operator resolves the first item after the card was rendered.
        self._post(f"/api/v1/candidates/{first}/sources/text",
                   {"text_content": "合成材料更新", "publish_material": True})
        self.page.locator("#project-next-action").click()
        expect(self.page.locator("#toast-root")).to_contain_text("项目待办已变化")
        expect(self.page.locator(".candidate-workspace-page")).to_have_count(0)
        fresh = self.context.request.get(
            self.base + f"/api/v1/projects/{pid}/pipeline").json()
        second = fresh["workflow_summary"]["next_action"]["target"]
        self.assertNotEqual(second["candidate_id"], first)
        self.assertNotEqual(second["candidate_id"], foreign_target)
        self.page.locator("#project-next-action").click()
        expect(self.page.locator("#content h1")).to_have_text(second["candidate_name"])
        expect(self.page.locator("#top-crumb")).to_contain_text(second["candidate_name"])
        self.page.locator("#top-back").click()
        expect(self.page.locator(".next-action-card")).to_be_visible()
        expect(self.page.locator(".candidate-workspace-page")).to_have_count(0)

    def test_primary_action_opens_completed_interview_exact_scorecard(self) -> None:
        """Core event target -> visible candidate -> Scorecard -> SQLite, no IDs typed."""
        pid, title = self._seed_project()
        cid = self.context.request.get(
            self.base + f"/api/v1/projects/{pid}/pipeline"
        ).json()["workflow_summary"]["next_action"]["target"]["candidate_id"]
        self._open_project(title)
        self.page.locator(".tabs").get_by_role("button", name="候选人").click()
        self.page.locator("tr[data-candidate-id]").filter(
            has_text="层级候选人").get_by_role("button", name="打开工作台").click()
        self.page.locator(".candidate-step").filter(has_text="面试").click()
        self.page.get_by_role("button", name="＋ 面试排期").click()
        self.page.locator("#e-title").fill("待反馈的合成面试")
        self.page.locator(".c-q").fill("请描述研究方法")
        self.page.locator("#e-state").select_option("completed")
        self.page.locator("#modal-root").get_by_role(
            "button", name="保存", exact=True).click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        events = self.context.request.get(
            self.base + f"/api/v1/candidates/{cid}/events").json()["events"]
        event = next(x for x in events if x["title"] == "待反馈的合成面试")
        eid = event["event_id"]
        self.assertEqual(event["event_state"], "completed")
        self.page.locator("#top-back").click()
        self.page.locator(".tabs").get_by_role("button", name="概览").click()
        pipeline = self.context.request.get(
            self.base + f"/api/v1/projects/{pid}/pipeline").json()
        action = pipeline["workflow_summary"]["next_action"]
        self.assertEqual(action["key"], "submit_feedback", action)
        self.assertEqual(action["target"]["candidate_id"], cid)
        self.assertEqual(action["target"]["event_id"], eid)
        expect(self.page.locator("#project-next-action")).to_contain_text("填写面评")
        self.page.locator("#project-next-action").click()
        expect(self.page.locator("#content h1")).to_have_text("层级候选人")
        modal = self.page.locator("#modal-root .modal")
        expect(modal.locator("#sc-criteria .criterion-block")).to_have_count(1)
        modal.locator("#sc-evaluator").fill("合成面试官")
        modal.locator(".c-rating").select_option("strong")
        modal.locator(".c-obs").fill("合成观察：明确的方法论")
        modal.locator("#sc-rec").fill("advance")
        modal.get_by_role("button", name="提交并锁定").click()
        expect(self.page.locator("#modal-root .modal")).to_have_count(0)
        with sqlite3.connect(Path(self.tmp.name) / "data" / "srw_v1.db") as db:
            rows = db.execute(
                "SELECT candidate_id, event_id, feedback_json FROM interview_scorecard_submission "
                "WHERE event_id=?", (eid,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], cid)
            self.assertEqual(rows[0][1], eid)
            self.assertEqual(json.loads(rows[0][2])[0]["criterion_key"], "research_reasoning")
        self.page.locator("#top-back").click()
        expect(self.page.locator(".next-action-card")).to_be_visible()


if __name__ == "__main__":
    unittest.main()
