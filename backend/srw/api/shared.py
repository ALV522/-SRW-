"""Shared Core helpers used by more than one route module.

``publish_current_revision`` used to be a closure inside
``install_full_workbench_routes``. Four call sites need it (candidate intake,
interview event creation, interview correction and an async job), so it cannot
live inside a single domain module without creating a cycle or duplicating the
revision policy. It is a pure function of the session plus identifiers: it reads
the candidate's current Source set, applies the supersede rule and publishes one
MaterialRevision.

Business meaning: a corrected structured interview replaces the superseded
Source inside the *current* evidence set; the old Source and MaterialRevision
remain immutable history. Do not re-implement this rule in a carrier or route
module (ADR-0002 §2.3).
"""
from __future__ import annotations

from sqlalchemy import select

from srw.modules.candidate.models import Candidate
from srw.modules.candidate.repository import MaterialRepository, get_current_source_ids
from srw.modules.protocol.models import ProtocolRevision


def publish_current_revision(session, candidate_id: str, new_source_id: str,
                             *, supersedes_source_id: str | None = None):
    candidate = session.get(Candidate, candidate_id)
    ids: list[str] = []
    if candidate and candidate.current_material_revision_id:
        try:
            ids = get_current_source_ids(session, candidate_id)
        except Exception:
            ids = []
    # A corrected structured interview is a replacement within the *current*
    # evidence set, not an additional live statement. The superseded Source and
    # previous MaterialRevision remain immutable historical records.
    if supersedes_source_id:
        ids = [source_id for source_id in ids if source_id != supersedes_source_id]
    if new_source_id not in ids:
        ids.append(new_source_id)
    provenance = {"action": "v1_intake", "source_id": new_source_id}
    if supersedes_source_id:
        provenance["supersedes_source_id"] = supersedes_source_id
    return MaterialRepository(session).publish_revision(candidate_id, ids, provenance)


def latest_draft(session, project_id: str):
    """Newest draft ProtocolRevision for a project, or None.

    Shared by template application, template creation from the current protocol
    and knowledge curation, so it cannot live inside one domain module.
    """
    return session.scalar(
        select(ProtocolRevision)
        .where(ProtocolRevision.project_id == project_id, ProtocolRevision.state == "draft")
        .order_by(ProtocolRevision.revision.desc())
        .limit(1)
    )
