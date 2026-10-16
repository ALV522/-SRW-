from __future__ import annotations

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError
from srw.modules.candidate.models import Candidate, MaterialRevision
from srw.modules.decision.context import get_current_decision_context
from srw.modules.protocol.models import Project, ProtocolRevision


def verify_v1_import(engine: Engine, *, evaluation_policy_revision: str = "policy.import.v1") -> list[str]:
    errors: list[str] = []
    with engine.connect() as conn:
        fk_violations = conn.execute(text("PRAGMA foreign_key_check")).all()
        if fk_violations:
            errors.append(f"foreign_key_check failed: {fk_violations}")

    with Session(engine) as session:
        for project in session.scalars(select(Project)).all():
            if not project.current_protocol_revision_id:
                errors.append(f"project {project.id} has no current protocol")
                continue
            protocol = session.get(ProtocolRevision, project.current_protocol_revision_id)
            if protocol is None or protocol.state != "published":
                errors.append(f"project {project.id} current protocol is invalid")
        for candidate in session.scalars(select(Candidate)).all():
            if not candidate.current_material_revision_id:
                errors.append(f"candidate {candidate.id} has no current material revision")
                continue
            material = session.get(MaterialRevision, candidate.current_material_revision_id)
            if material is None or material.candidate_id != candidate.id:
                errors.append(f"candidate {candidate.id} current material is invalid")
                continue
            try:
                get_current_decision_context(
                    session,
                    candidate.id,
                    evaluation_policy_revision=evaluation_policy_revision,
                )
            except V1InvariantError as exc:
                errors.append(f"candidate {candidate.id} decision context invalid: {exc}")
    return errors
