from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError
from srw.kernel.hashing import decision_context_hash
from srw.modules.candidate.repository import get_current_material_identity
from srw.modules.protocol.repository import get_current_protocol_identity


@dataclass(frozen=True, slots=True)
class DecisionContext:
    candidate_id: str
    project_id: str
    protocol_revision_id: str
    material_revision_id: str
    evaluation_policy_revision: str
    hash: str


def get_current_decision_context(
    session: Session,
    candidate_id: str,
    *,
    evaluation_policy_revision: str,
) -> DecisionContext:
    material = get_current_material_identity(session, candidate_id)
    protocol = get_current_protocol_identity(session, material.project_id)
    if protocol.project_id != material.project_id:
        raise V1InvariantError("protocol/material project mismatch")
    digest = decision_context_hash(
        protocol.protocol_revision_id,
        material.material_revision_id,
        evaluation_policy_revision,
    )
    return DecisionContext(
        candidate_id=material.candidate_id,
        project_id=material.project_id,
        protocol_revision_id=protocol.protocol_revision_id,
        material_revision_id=material.material_revision_id,
        evaluation_policy_revision=evaluation_policy_revision,
        hash=digest,
    )
