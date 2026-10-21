from __future__ import annotations

import sqlite3
from pathlib import Path


def _db(path: Path, statements: list[str], rows: list[tuple[str, tuple]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        for sql in statements:
            con.execute(sql)
        for sql, params in rows or []:
            con.execute(sql, params)
        con.commit()
    finally:
        con.close()


def create_minimal_knowledge_tree(root: str | Path) -> Path:
    """Create a tiny source-controlled test Knowledge surface.

    The real five active databases remain release artifacts. CI builds only the
    schemas/rows needed by recovery tests, so Git does not need production DBs.
    """
    root = Path(root)

    _db(
        root / "taxonomy" / "knowledge.db",
        [
            "CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)",
            "CREATE TABLE canonical_role(role_id TEXT PRIMARY KEY, title TEXT, status TEXT)",
            "CREATE TABLE specialization(specialization_id TEXT PRIMARY KEY, title TEXT, status TEXT)",
            "CREATE TABLE title_alias(alias_id TEXT PRIMARY KEY, title TEXT, normalized_title TEXT, language TEXT, alias_type TEXT, ambiguity INTEGER, source_id TEXT, status TEXT)",
            "CREATE TABLE title_mapping(mapping_id TEXT PRIMARY KEY, alias_id TEXT, target_type TEXT, target_id TEXT, mapping_type TEXT, seniority_hint TEXT, management_scope_hint TEXT, confidence REAL, rationale TEXT, status TEXT, valid_from TEXT, valid_to TEXT, version TEXT)",
            "CREATE TABLE alias_fts(alias_id TEXT PRIMARY KEY, title TEXT)",
        ],
        [
            ("INSERT INTO schema_meta VALUES (?,?)", ("schema", "test-taxonomy")),
            ("INSERT INTO canonical_role VALUES (?,?,?)", ("ROLE-001", "Software Engineer", "active")),
            ("INSERT INTO alias_fts VALUES (?,?)", ("ALIAS-001", "Software Engineer")),
        ],
    )

    _db(
        root / "job_info" / "knowledge.db",
        [
            "CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)",
            "CREATE TABLE profile(profile_id TEXT PRIMARY KEY, title TEXT)",
            "CREATE TABLE profile_item(item_id TEXT PRIMARY KEY, profile_id TEXT, item_text TEXT)",
        ],
        [("INSERT INTO schema_meta VALUES (?,?)", ("schema", "test-job-info"))],
    )

    _db(
        root / "competency" / "knowledge.db",
        [
            "CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)",
            "CREATE TABLE competency(competency_id TEXT PRIMARY KEY, name_zh TEXT, name_en TEXT, definition TEXT, status TEXT)",
            "CREATE TABLE competency_alias(alias_id TEXT PRIMARY KEY, competency_id TEXT, alias TEXT, language TEXT, alias_type TEXT, source_id TEXT, status TEXT)",
            "CREATE TABLE competency_facet(facet_id TEXT PRIMARY KEY, competency_id TEXT, facet_text TEXT)",
            "CREATE TABLE job_competency_requirement(requirement_id TEXT PRIMARY KEY, competency_id TEXT)",
            "CREATE TABLE evidence_policy(policy_id TEXT PRIMARY KEY, competency_id TEXT)",
            "CREATE TABLE competency_fts(competency_id TEXT PRIMARY KEY, name_zh TEXT, name_en TEXT, definition TEXT, facet_text TEXT)",
        ],
        [
            ("INSERT INTO schema_meta VALUES (?,?)", ("schema", "test-competency")),
            ("INSERT INTO competency VALUES (?,?,?,?,?)", ("COMP-001", "数据分析", "Data Analysis", "Analyse structured evidence", "active")),
            ("INSERT INTO competency VALUES (?,?,?,?,?)", ("COMP-002", "项目管理", "Project Management", "Coordinate project delivery", "active")),
            ("INSERT INTO competency_fts VALUES (?,?,?,?,?)", ("COMP-001", "数据分析", "Data Analysis", "Analyse structured evidence", "结构化证据分析与归纳")),
        ],
    )

    _db(
        root / "market_reference" / "knowledge.db",
        [
            "CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)",
            "CREATE TABLE source_record(source_id TEXT PRIMARY KEY, title TEXT)",
            "CREATE TABLE wage_benchmark(id TEXT PRIMARY KEY, period TEXT, geography TEXT, industry TEXT, occupation_group TEXT, annual_wage_cny REAL, metric_scope TEXT, note TEXT)",
            "CREATE TABLE local_supply_demand(id TEXT PRIMARY KEY, geography TEXT, occupation_group TEXT)",
            "CREATE TABLE role_market_mapping(id TEXT PRIMARY KEY, role_id TEXT)",
            "CREATE TABLE beijing_skill_shortage(job_title TEXT, occupation_description TEXT, salary_median_10k REAL, shortage_level TEXT, regions TEXT, guardrail TEXT)",
        ],
        [("INSERT INTO schema_meta VALUES (?,?)", ("schema", "test-market"))],
    )

    _db(
        root / "reference" / "knowledge.db",
        [
            "CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)",
            "CREATE TABLE source_registry(source_id TEXT PRIMARY KEY, title TEXT)",
            "CREATE TABLE reference_entity(entity_id TEXT PRIMARY KEY, title TEXT)",
            "CREATE TABLE reference_job_profile(profile_id TEXT PRIMARY KEY, title TEXT)",
            "CREATE TABLE quality_metric(metric_id TEXT PRIMARY KEY, value REAL)",
        ],
        [("INSERT INTO schema_meta VALUES (?,?)", ("schema", "test-reference"))],
    )
    return root
