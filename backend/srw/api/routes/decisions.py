"""Reevaluation routes: draft, list and apply (ADR-0002 R2, sixth slice).

This is the reassessment path that keeps a human decision honest when material or
protocol changes. Behaviour is identical to the code that lived inside
``install_full_workbench_routes``; the invariants it enforces are the product's
core semantics and are documented here so a route move cannot quietly soften
them:

* a draft compares against the **latest prior human judgment per criterion key**,
  not only the judgments in the current decision context. A new MaterialRevision
  intentionally changes the context hash; pretending the earlier assessment never
  existed would hide the delta the operator needs to see;
* applying a draft re-checks the context hash and marks the draft `stale`
  (HTTP 409) instead of writing assessments against a context that no longer
  exists;
* apply writes `pre_reevaluation` and `post_reevaluation` snapshots and records
  assessments with actor `human:reevaluation`. It never records a HumanDecision -
  the decision stays with the operator.
"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from srw.api.http_utils import json_body, s_field
from srw.kernel.clock import utc_now
from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.modules.audit.models import AuditEvent
from srw.modules.audit.repository import append_audit_event
from srw.modules.candidate.models import Candidate
from srw.modules.decision.commands import record_assessment
from srw.modules.decision.context import get_current_decision_context
from srw.modules.decision.models import CriterionJudgment, CriterionJudgmentEvidence
from srw.modules.fullworkbench import EvaluationSnapshot, ReevaluationDraft
from srw.modules.protocol.repository import ProtocolRepository
from srw.runtime.db.session import v1_session_scope

JUDGMENT_STATUSES = {"met", "partial", "missing", "conflict", "not_met"}
EVIDENCE_LEVELS = {"strong", "medium", "weak", "none"}


def judgment_payload(session, row) -> dict:
    claim_ids = sorted(session.scalars(select(CriterionJudgmentEvidence.claim_id).where(
        CriterionJudgmentEvidence.judgment_id == row.id)).all())
    return {"criterion_key": row.criterion_key, "status": row.status,
            "evidence_level": row.evidence_level, "reason": row.reason, "gap": row.gap,
            "claim_ids": claim_ids}


def judgment_revision(session, row) -> dict | None:
    """Durable per-criterion edit token, including same-value ABA writes.

    The audit event count advances every time record_assessment writes an
    assessment, even if all visible fields return to the previous values.
    The row identity and timestamp additionally reject recreation and edits
    made outside the usual write path. These are not HTTP authentication tokens.
    """
    if row is None:
        return None
    count = session.scalar(select(func.count(AuditEvent.id)).where(
        AuditEvent.entity_type == "criterion_judgment",
        AuditEvent.entity_id == row.id,
        AuditEvent.event_type == "CRITERION_JUDGMENT_RECORDED",
    )) or 0
    return {"judgment_id": row.id, "updated_at": row.updated_at.isoformat(),
            "write_count": int(count)}


def reevaluation_routes(*, factory, evaluation_policy_revision: str) -> list[Route]:
    """Bind the reevaluation endpoints to one Core session factory."""

    async def reevaluations(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        with factory() as session:
            rows = session.scalars(
                select(ReevaluationDraft).where(ReevaluationDraft.candidate_id == cid)
                .order_by(ReevaluationDraft.created_at.desc())
            ).all()
            return JSONResponse({"drafts": [{
                "draft_id": x.id, "state": x.state, "summary": x.summary,
                "proposal": json.loads(x.proposal_json),
                "diff": json.loads(x.diff_json or "[]"),
                "decision_context_hash": x.decision_context_hash,
                "created_at": x.created_at.isoformat(),
                "applied_at": x.applied_at.isoformat() if x.applied_at else None,
            } for x in rows]})

    async def reevaluation_create(request: Request) -> JSONResponse:
        cid = request.path_params["candidate_id"]
        body = await json_body(request)
        proposal = body.get("proposal") if isinstance(body.get("proposal"), dict) else {}
        proposed = proposal.get("judgments") or []
        if not isinstance(proposed, list):
            raise V1InvariantError("proposal.judgments must be an array")
        with v1_session_scope(factory) as session:
            candidate = session.get(Candidate, cid)
            if not candidate:
                raise V1NotFoundError(f"candidate not found: {cid}")
            context = get_current_decision_context(
                session, cid, evaluation_policy_revision=evaluation_policy_revision)
            if "expected_context_hash" in body and body["expected_context_hash"] != context.hash:
                raise V1InvariantError("material or protocol changed; reopen reevaluation editor")
            current = {x.criterion_key: x for x in session.scalars(
                select(CriterionJudgment).where(
                    CriterionJudgment.candidate_id == cid,
                    CriterionJudgment.decision_context_hash == context.hash)
            ).all()}
            protocol = ProtocolRepository(session).get_payload(context.protocol_revision_id)
            known = {str(x.get("criterion_key") or "")
                     for x in protocol.get("criteria", []) if isinstance(x, dict)}
            # A new MaterialRevision intentionally changes the decision context. Reevaluation must still
            # compare against the latest prior human judgment for the same stable criterion key, rather
            # than pretending the prior assessment never existed. Current-context judgments win.
            baseline = dict(current)
            previous = session.scalars(
                select(CriterionJudgment).where(
                    CriterionJudgment.candidate_id == cid,
                    CriterionJudgment.criterion_key.in_(known))
                .order_by(CriterionJudgment.updated_at.desc(), CriterionJudgment.id.desc())
            ).all() if known else []
            for row in previous:
                baseline.setdefault(row.criterion_key, row)
            diff = []
            for item in proposed:
                if not isinstance(item, dict):
                    raise V1InvariantError("reevaluation judgment must be an object")
                key = str(item.get("criterion_key") or "").strip()
                if not key or key not in known:
                    raise V1InvariantError(f"unknown criterion_key: {key}")
                before = baseline.get(key)
                before_view = judgment_payload(session, before) if before else {
                    "criterion_key": key, "status": "missing",
                    "evidence_level": "none", "reason": "", "gap": "", "claim_ids": []}
                after = {
                    "criterion_key": key,
                    "status": str(item.get("status") or "missing"),
                    "evidence_level": str(item.get("evidence_level") or "none"),
                    "reason": str(item.get("reason") or ""),
                    "gap": str(item.get("gap") or ""),
                    "claim_ids": sorted({str(x) for x in (item.get("claim_ids") or [])}),
                }
                if after["status"] not in JUDGMENT_STATUSES:
                    raise V1InvariantError("invalid reevaluation status")
                if after["evidence_level"] not in EVIDENCE_LEVELS:
                    raise V1InvariantError("invalid reevaluation evidence_level")
                # Omission retains the legacy no-op contract for unchanged text;
                # only an explicit reference set requests an evidence-only edit.
                fields = ("status", "evidence_level", "reason", "gap")
                if "claim_ids" in item:
                    fields += ("claim_ids",)
                if any(before_view.get(k) != after.get(k) for k in fields):
                    # Persist the server-observed CURRENT-context revision, not
                    # the cross-context display baseline. An absent current row
                    # is itself a precondition; any concurrent first write
                    # makes this draft stale even if its visible value matches.
                    diff.append({"criterion_key": key, "before": before_view, "after": after,
                                 "expected_current_revision": judgment_revision(session, current.get(key))})
            draft = ReevaluationDraft(
                candidate_id=cid, summary=s_field(body, "summary"),
                proposal_json=json.dumps(proposal, ensure_ascii=False),
                protocol_revision_id=context.protocol_revision_id,
                material_revision_id=context.material_revision_id,
                decision_context_hash=context.hash,
                diff_json=json.dumps(diff, ensure_ascii=False, separators=(",", ":")),
            )
            session.add(draft)
            session.flush()
            append_audit_event(
                session, event_type="REEVALUATION_DRAFT_CREATED", entity_type="reevaluation",
                entity_id=draft.id, actor=s_field(body, "actor", default="human"),
                payload={"diff_count": len(diff), "context_hash": context.hash},
                project_id=context.project_id, candidate_id=cid,
            )
            return JSONResponse({"draft_id": draft.id, "state": draft.state,
                                 "diff": diff, "decision_context_hash": context.hash})

    async def reevaluation_apply(request: Request) -> JSONResponse:
        did = request.path_params["draft_id"]
        with v1_session_scope(factory) as session:
            # Reserve the one SQLite writer BEFORE reading the draft and its
            # judgment revisions. This prevents two clients from interleaving
            # a revision check and the authoritative assessment update.
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            draft = session.get(ReevaluationDraft, did)
            if not draft:
                raise V1NotFoundError(f"draft not found: {did}")
            diff = json.loads(draft.diff_json or "[]")
            if draft.state == "applied":
                return JSONResponse({"draft_id": draft.id, "state": "applied",
                                     "applied_changes": len(diff), "idempotent": True})
            if draft.state == "stale":
                return JSONResponse({"draft_id": draft.id, "state": "stale",
                                     "detail": "reevaluation context is stale"}, status_code=409)
            if draft.state != "draft":
                raise V1InvariantError("draft is not applicable")
            context = get_current_decision_context(
                session, draft.candidate_id, evaluation_policy_revision=evaluation_policy_revision)
            if context.hash != draft.decision_context_hash:
                draft.state = "stale"
                return JSONResponse({
                    "draft_id": draft.id, "state": "stale",
                    "detail": "material or protocol changed; recalculate reevaluation",
                }, status_code=409)
            before_rows = session.scalars(
                select(CriterionJudgment).where(
                    CriterionJudgment.candidate_id == draft.candidate_id,
                    CriterionJudgment.decision_context_hash == context.hash)
            ).all()
            current_by_key = {row.criterion_key: row for row in before_rows}
            for change in diff:
                if ("expected_current_revision" not in change
                        or judgment_revision(session, current_by_key.get(change["criterion_key"]))
                        != change["expected_current_revision"]):
                    draft.state = "stale"
                    return JSONResponse({
                        "draft_id": draft.id, "state": "stale",
                        "detail": "judgment changed since the reevaluation draft; recreate draft",
                    }, status_code=409)
            before_payload = [judgment_payload(session, row) for row in before_rows]
            session.add(EvaluationSnapshot(
                candidate_id=draft.candidate_id, project_id=context.project_id,
                decision_context_hash=context.hash, reevaluation_id=draft.id,
                snapshot_kind="pre_reevaluation",
                payload_json=json.dumps({"judgments": before_payload},
                                        ensure_ascii=False, separators=(",", ":")),
            ))
            for change in diff:
                after = change.get("after") or {}
                record_assessment(
                    session, draft.candidate_id, str(change.get("criterion_key") or ""),
                    status=str(after.get("status") or "missing"),
                    evidence_level=str(after.get("evidence_level") or "none"),
                    reason=str(after.get("reason") or ""),
                    gap=str(after.get("gap") or ""),
                    claim_ids=[str(v) for v in (after.get("claim_ids") or [])],
                    actor="human:reevaluation",
                    evaluation_policy_revision=evaluation_policy_revision,
                )
            after_rows = session.scalars(
                select(CriterionJudgment).where(
                    CriterionJudgment.candidate_id == draft.candidate_id,
                    CriterionJudgment.decision_context_hash == context.hash)
            ).all()
            session.add(EvaluationSnapshot(
                candidate_id=draft.candidate_id, project_id=context.project_id,
                decision_context_hash=context.hash, reevaluation_id=draft.id,
                snapshot_kind="post_reevaluation",
                payload_json=json.dumps({"judgments": [judgment_payload(session, row) for row in after_rows]},
                                        ensure_ascii=False, separators=(",", ":")),
            ))
            draft.state = "applied"
            draft.applied_at = utc_now()
            append_audit_event(
                session, event_type="REEVALUATION_APPLIED", entity_type="reevaluation",
                entity_id=draft.id, actor="human",
                payload={"diff_count": len(diff), "context_hash": context.hash},
                project_id=context.project_id, candidate_id=draft.candidate_id,
            )
            return JSONResponse({"draft_id": draft.id, "state": draft.state,
                                 "applied_changes": len(diff), "human_decision_unchanged": True})

    return [
        Route("/api/v1/candidates/{candidate_id:str}/reevaluations", reevaluations, methods=["GET"]),
        Route("/api/v1/candidates/{candidate_id:str}/reevaluations", reevaluation_create, methods=["POST"]),
        Route("/api/v1/reevaluations/{draft_id:str}/apply", reevaluation_apply, methods=["POST"]),
    ]
