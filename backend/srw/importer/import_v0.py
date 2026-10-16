from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import Connection, inspect, text
from sqlalchemy.orm import Session

from srw.importer.reconcile import reconcile_project_protocol
from srw.importer.report import ImportReport, ImportWarning
from srw.importer.source_db import open_legacy_readonly
from srw.importer.verify import verify_v1_import
from srw.kernel.hashing import canonical_json_bytes
from srw.modules.candidate.models import Candidate, CandidateContact, Source
from srw.modules.candidate.repository import MaterialRepository
from srw.modules.protocol.models import Project, ProtocolRevision
from srw.runtime.db.schema import create_v1_schema
from srw.runtime.db.session import create_v1_engine


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count(conn: Connection, table: str) -> int:
    if table not in inspect(conn).get_table_names():
        return 0
    return int(conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())


def _rows(conn: Connection, table: str, where: str = "", params: dict | None = None) -> list[dict]:
    if table not in inspect(conn).get_table_names():
        return []
    sql = f'SELECT * FROM "{table}"'
    if where:
        sql += f" WHERE {where}"
    return [dict(row) for row in conn.execute(text(sql), params or {}).mappings().all()]


def _source_text(row: dict) -> str:
    corrected = str(row.get("human_corrected_text") or "").strip()
    return corrected if corrected else str(row.get("parsed_text") or "")


def import_v0_to_v1(source_path: str | Path, destination_path: str | Path) -> ImportReport:
    source = Path(source_path).resolve()
    destination = Path(destination_path).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    temp = destination.with_name(destination.name + ".tmp")
    for candidate in (temp, Path(str(temp) + "-wal"), Path(str(temp) + "-shm")):
        if candidate.exists():
            candidate.unlink()

    report = ImportReport()
    report.source_sha256_before = _file_sha256(source)
    legacy_engine = open_legacy_readonly(source)
    v1_engine = create_v1_engine(f"sqlite:///{temp}")
    create_v1_schema(v1_engine)

    try:
        with legacy_engine.connect() as legacy, Session(v1_engine) as dest:
            report.source_counts = {
                table: _count(legacy, table)
                for table in (
                    "recruitment_projects",
                    "recruitment_context_versions",
                    "job_criteria_versions",
                    "requirement_criteria",
                    "assessment_plan_versions",
                    "candidates",
                    "candidate_contacts",
                    "candidate_documents",
                    "candidate_resume_versions",
                )
            }
            report.mapped_counts = {
                "project": 0,
                "protocol_revision": 0,
                "candidate": 0,
                "candidate_contact": 0,
                "source": 0,
                "material_revision": 0,
            }

            projects = _rows(legacy, "recruitment_projects")
            for legacy_project in projects:
                snapshot = reconcile_project_protocol(legacy, legacy_project["id"])
                project = Project(
                    id=legacy_project["id"],
                    title=legacy_project.get("title") or "",
                    status=legacy_project.get("status") or "active",
                )
                dest.add(project)
                dest.flush()
                protocol = ProtocolRevision(
                    project_id=project.id,
                    revision=1,
                    state="published",
                    payload_json=canonical_json_bytes(snapshot.payload).decode("utf-8"),
                    provenance_json=canonical_json_bytes(snapshot.provenance).decode("utf-8"),
                    content_hash=snapshot.content_hash,
                )
                dest.add(protocol)
                dest.flush()
                project.current_protocol_revision_id = protocol.id
                report.mapped_counts["project"] += 1
                report.mapped_counts["protocol_revision"] += 1

                for legacy_candidate in _rows(legacy, "candidates", "project_id=:project_id", {"project_id": project.id}):
                    candidate = Candidate(
                        id=legacy_candidate["id"],
                        project_id=project.id,
                        display_name=legacy_candidate.get("display_name") or "",
                        archived=bool(legacy_candidate.get("archived_at")),
                    )
                    dest.add(candidate)
                    dest.flush()
                    report.mapped_counts["candidate"] += 1

                    contacts = _rows(legacy, "candidate_contacts", "candidate_id=:candidate_id", {"candidate_id": candidate.id})
                    if contacts:
                        contact = contacts[0]
                        dest.add(
                            CandidateContact(
                                id=contact["id"],
                                candidate_id=candidate.id,
                                display_name=contact.get("display_name") or candidate.display_name,
                                phone=contact.get("phone") or "",
                                email=contact.get("email") or "",
                                confirmed_fields_json=contact.get("confirmed_fields_json") or "[]",
                                user_confirmed=bool(contact.get("user_confirmed")),
                                provenance_json=canonical_json_bytes({"legacy_contact_id": contact["id"]}).decode("utf-8"),
                            )
                        )
                        report.mapped_counts["candidate_contact"] += 1

                    source_by_document: dict[str, str] = {}
                    documents = _rows(legacy, "candidate_documents", "candidate_id=:candidate_id", {"candidate_id": candidate.id})
                    for document in documents:
                        source_row = Source(
                            id=document["id"],
                            candidate_id=candidate.id,
                            source_kind="resume_document",
                            content_hash=document.get("sha256") or hashlib.sha256(_source_text(document).encode("utf-8")).hexdigest(),
                            blob_hash=document.get("sha256") or None,
                            media_type=document.get("media_type") or "application/octet-stream",
                            text_content=_source_text(document),
                            metadata_json=canonical_json_bytes(
                                {
                                    "legacy_document_id": document["id"],
                                    "original_filename": document.get("original_filename") or "",
                                    "file_size": document.get("file_size") or 0,
                                    "storage_path": document.get("storage_path") or "",
                                    "parser_status": document.get("parser_status") or "",
                                }
                            ).decode("utf-8"),
                        )
                        dest.add(source_row)
                        source_by_document[document["id"]] = source_row.id
                        report.mapped_counts["source"] += 1
                    dest.flush()

                    current_resumes = [
                        row
                        for row in _rows(
                            legacy,
                            "candidate_resume_versions",
                            "candidate_id=:candidate_id",
                            {"candidate_id": candidate.id},
                        )
                        if bool(row.get("is_current"))
                    ]
                    if len(current_resumes) != 1:
                        raise RuntimeError(
                            f"candidate {candidate.id} must have exactly one current resume for phase-one import; found {len(current_resumes)}"
                        )
                    resume = current_resumes[0]
                    source_id = source_by_document.get(resume.get("document_id"))
                    if source_id is None:
                        raise RuntimeError(
                            f"candidate {candidate.id} current resume document is missing: {resume.get('document_id')}"
                        )
                    MaterialRepository(dest).publish_revision(
                        candidate.id,
                        [source_id],
                        provenance={"legacy_resume_version_id": resume["id"]},
                    )
                    report.mapped_counts["material_revision"] += 1

            dest.commit()

        errors = verify_v1_import(v1_engine)
        report.errors.extend(errors)
        report.status = "passed" if not errors else "failed"
        with v1_engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception as exc:
        report.status = "failed"
        report.errors.append(str(exc))
        raise
    finally:
        legacy_engine.dispose()
        v1_engine.dispose()
        report.source_sha256_after = _file_sha256(source)

    if report.source_sha256_after != report.source_sha256_before:
        report.status = "failed"
        report.errors.append("source database changed during import")
        raise RuntimeError("legacy source database mutated during import")
    if report.status != "passed":
        raise RuntimeError("v1 import verification failed: " + "; ".join(report.errors))

    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp, destination)
    for sidecar in (Path(str(temp) + "-wal"), Path(str(temp) + "-shm")):
        if sidecar.exists():
            sidecar.unlink()
    return report
