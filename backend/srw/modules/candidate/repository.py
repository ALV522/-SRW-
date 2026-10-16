from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from srw.kernel.errors import V1InvariantError, V1NotFoundError
from srw.kernel.hashing import content_hash
from srw.modules.candidate.models import Candidate, MaterialRevision, MaterialSourceBinding, Source


class MaterialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def publish_revision(
        self,
        candidate_id: str,
        source_ids: list[str],
        provenance: dict | None = None,
    ) -> MaterialRevision:
        candidate = self.session.get(Candidate, candidate_id)
        if candidate is None:
            raise V1NotFoundError(f"candidate not found: {candidate_id}")
        unique_ids = sorted(set(source_ids))
        if not unique_ids:
            raise V1InvariantError("material revision requires at least one source")
        sources = self.session.scalars(select(Source).where(Source.id.in_(unique_ids))).all()
        by_id = {row.id: row for row in sources}
        if set(by_id) != set(unique_ids):
            missing = sorted(set(unique_ids) - set(by_id))
            raise V1NotFoundError(f"source not found: {missing}")
        foreign = [row.id for row in sources if row.candidate_id != candidate_id]
        if foreign:
            raise V1InvariantError(f"sources belong to another candidate: {sorted(foreign)}")

        next_revision = (
            self.session.scalar(
                select(func.coalesce(func.max(MaterialRevision.revision), 0)).where(
                    MaterialRevision.candidate_id == candidate_id
                )
            )
            or 0
        ) + 1
        source_identity = [
            {"source_kind": by_id[source_id].source_kind, "content_hash": by_id[source_id].content_hash}
            for source_id in unique_ids
        ]
        from srw.kernel.hashing import canonical_json_bytes

        row = MaterialRevision(
            candidate_id=candidate_id,
            revision=next_revision,
            source_set_hash=content_hash(source_identity),
            provenance_json=canonical_json_bytes(provenance or {}).decode("utf-8"),
        )
        self.session.add(row)
        self.session.flush()
        for position, source_id in enumerate(unique_ids):
            self.session.add(
                MaterialSourceBinding(
                    material_revision_id=row.id,
                    source_id=source_id,
                    position=position,
                )
            )
        candidate.current_material_revision_id = row.id
        self.session.flush()
        return row

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentMaterialIdentity:
    candidate_id: str
    project_id: str
    material_revision_id: str


def get_current_material_identity(session: Session, candidate_id: str) -> CurrentMaterialIdentity:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise V1NotFoundError(f"candidate not found: {candidate_id}")
    if not candidate.current_material_revision_id:
        raise V1InvariantError("candidate has no published current material revision")
    material = session.get(MaterialRevision, candidate.current_material_revision_id)
    if material is None or material.candidate_id != candidate.id:
        raise V1InvariantError("current material pointer is invalid")
    return CurrentMaterialIdentity(
        candidate_id=candidate.id,
        project_id=candidate.project_id,
        material_revision_id=material.id,
    )

from srw.modules.candidate.models import Claim


def ensure_claims_belong_to_candidate(session: Session, candidate_id: str, claim_ids: list[str]) -> None:
    unique_ids = sorted(set(claim_ids))
    if not unique_ids:
        return
    rows = session.scalars(select(Claim).where(Claim.id.in_(unique_ids))).all()
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(unique_ids):
        missing = sorted(set(unique_ids) - set(by_id))
        raise V1NotFoundError(f"claim not found: {missing}")
    foreign = sorted(row.id for row in rows if row.candidate_id != candidate_id)
    if foreign:
        raise V1InvariantError(f"claims belong to another candidate: {foreign}")

@dataclass(frozen=True, slots=True)
class ClaimGrounding:
    claim_id: str
    source_id: str


def get_material_source_ids(session: Session, material_revision_id: str) -> set[str]:
    return set(session.scalars(select(MaterialSourceBinding.source_id).where(MaterialSourceBinding.material_revision_id == material_revision_id)).all())


def get_current_source_ids(session: Session, candidate_id: str) -> list[str]:
    identity = get_current_material_identity(session, candidate_id)
    return list(session.scalars(select(MaterialSourceBinding.source_id).where(MaterialSourceBinding.material_revision_id == identity.material_revision_id).order_by(MaterialSourceBinding.position)).all())


def get_claim_groundings(session: Session, claim_ids: list[str]) -> list[ClaimGrounding]:
    if not claim_ids: return []
    rows = session.scalars(select(Claim).where(Claim.id.in_(sorted(set(claim_ids))))).all()
    return [ClaimGrounding(row.id, row.source_id) for row in rows]
