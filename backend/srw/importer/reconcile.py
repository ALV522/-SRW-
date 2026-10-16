from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text

from srw.kernel.errors import ImportReconciliationError
from srw.kernel.hashing import content_hash


@dataclass(frozen=True, slots=True)
class LegacyProtocolSnapshot:
    project_id: str
    context_id: str
    criteria_id: str
    plan_id: str
    payload: dict[str, Any]
    provenance: dict[str, Any]
    content_hash: str


def _one(conn: Connection, sql: str, params: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute(text(sql), params).mappings().first()
    if row is None:
        raise ImportReconciliationError(f"legacy row not found for query: {sql.split('FROM', 1)[-1].strip()}")
    return dict(row)


def _json_object(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(raw: Any) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _criterion_payload(row: dict[str, Any]) -> dict[str, Any]:
    def value(name: str, default: Any = "") -> Any:
        return row[name] if name in row and row[name] is not None else default

    return {
        "criterion_key": value("criterion_key"),
        "name": value("name"),
        "definition": value("criterion_definition", value("description")),
        "why_it_matters": value("why_it_matters"),
        "positive_anchors": _json_list(value("positive_anchors_json", "[]")),
        "boundary_anchors": _json_list(value("boundary_anchors_json", "[]")),
        "insufficient_anchors": _json_list(value("insufficient_anchors_json", "[]")),
        "acceptable_evidence_sources": _json_list(value("acceptable_evidence_sources_json", "[]")),
        "verification_probes": _json_list(value("verification_probes_json", "[]")),
        "contradiction_signals": _json_list(value("contradiction_signals_json", "[]")),
        "adjudication_notes": value("adjudication_notes"),
        "minimum_evidence": value("minimum_evidence_for_decision", "weak"),
        "decision_critical": bool(value("decision_critical", 0)),
        "primary_assessment_stage": value("primary_assessment_stage", "resume"),
        "position": int(value("position", 0)),
    }


def reconcile_project_protocol(conn: Connection, project_id: str) -> LegacyProtocolSnapshot:
    project = _one(conn, "SELECT * FROM recruitment_projects WHERE id=:id", {"id": project_id})
    context_id = project.get("current_recruitment_context_version_id")
    criteria_id = project.get("current_criteria_version_id")
    plan_id = project.get("current_assessment_plan_version_id")
    if not context_id or not criteria_id or not plan_id:
        raise ImportReconciliationError(
            f"project {project_id} has incomplete current protocol pointers; refusing to fabricate lineage"
        )

    context = _one(conn, "SELECT * FROM recruitment_context_versions WHERE id=:id", {"id": context_id})
    criteria = _one(conn, "SELECT * FROM job_criteria_versions WHERE id=:id", {"id": criteria_id})
    plan = _one(conn, "SELECT * FROM assessment_plan_versions WHERE id=:id", {"id": plan_id})

    if context.get("project_id") != project_id:
        raise ImportReconciliationError(f"current context belongs to another project: {context_id}")
    if criteria.get("project_id") != project_id:
        raise ImportReconciliationError(f"current criteria belongs to another project: {criteria_id}")
    if plan.get("project_id") != project_id:
        raise ImportReconciliationError(f"current plan belongs to another project: {plan_id}")
    if criteria.get("recruitment_context_version_id") != context_id:
        raise ImportReconciliationError(
            f"current criteria {criteria_id} does not reference current context {context_id}"
        )
    if plan.get("recruitment_context_version_id") != context_id:
        raise ImportReconciliationError(f"current plan {plan_id} does not reference current context {context_id}")
    if plan.get("criteria_version_id") != criteria_id:
        raise ImportReconciliationError(f"current plan {plan_id} criteria lineage does not match {criteria_id}")

    criterion_rows = conn.execute(
        text("SELECT * FROM requirement_criteria WHERE version_id=:version_id ORDER BY position, id"),
        {"version_id": criteria_id},
    ).mappings().all()
    context_json = _json_object(context.get("context_json"))
    brief = context_json.get("brief") if isinstance(context_json.get("brief"), dict) else context_json
    payload: dict[str, Any] = {
        "brief": brief,
        "criteria": [_criterion_payload(dict(row)) for row in criterion_rows],
        "assessment_stages": _json_list(plan.get("stages_json")),
        "decision_policy": {},
    }
    provenance = {
        "legacy_project_id": project_id,
        "legacy_context_id": context_id,
        "legacy_criteria_id": criteria_id,
        "legacy_plan_id": plan_id,
        "context_provenance": _json_object(context.get("provenance_json")),
        "source": "v0.8.12-R2",
    }
    return LegacyProtocolSnapshot(
        project_id=project_id,
        context_id=context_id,
        criteria_id=criteria_id,
        plan_id=plan_id,
        payload=payload,
        provenance=provenance,
        content_hash=content_hash(payload),
    )
