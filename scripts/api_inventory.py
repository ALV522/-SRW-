"""Generate the frozen API inventory for the API-first modular Core (R1).

The inventory is the safety net that lets backend routes move between modules
without changing what clients already depend on. It records, for every route
the real application registers:

* HTTP method and path template (exact string, used verbatim for the freeze);
* the module that owns the handler, taken from the live endpoint object rather
  than from text matching, so it cannot drift from reality;
* a business domain bucket derived from the path;
* whether the route mutates state;
* static signals for concurrency, audit and human-actor handling.

The last three are *static source signals*, not proof of behaviour. They are
labelled ``basis: "endpoint-source-scan"`` for exactly that reason: this file
maps the surface, it does not certify the invariants behind it.

Run ``python scripts/api_inventory.py`` to print the inventory, or
``--write`` to refresh ``verification/api_contract/inventory.json`` and
``docs/API_INVENTORY.md``. ``convergence_tests/test_api_contract.py`` builds a
real application and fails when the committed inventory and the live route
table disagree.
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "backend"), str(ROOT / "convergence_tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

INVENTORY_PATH = ROOT / "verification" / "api_contract" / "inventory.json"
MUTATIONS_PATH = ROOT / "verification" / "api_contract" / "mutations.json"
DOC_PATH = ROOT / "docs" / "API_INVENTORY.md"
FRONTEND_DIR = ROOT / "frontend" / "dist"

MUTATING_METHODS = ("POST", "PATCH", "PUT", "DELETE")
IGNORED_METHODS = ("HEAD", "OPTIONS")

# Resource keyword -> business domain. The last matching path segment wins, so
# /api/v1/projects/{id}/candidates is classified as candidates, not projects.
DOMAIN_KEYWORDS = {
    "system": {"runtime", "health", "info", "settings", "system", "diagnostics", "backups"},
    "candidates": {"candidates", "candidate", "identity-reviews", "ranked-shortlists"},
    "evidence": {"sources", "source", "evidence", "claims", "claim", "judgments", "judgment"},
    "decisions": {"decisions", "decision", "assessment", "assessments", "reevaluations",
                  "calibration", "decision-actions"},
    "interviews": {"events", "event", "interviews", "interview", "scorecards", "scorecard"},
    "offers": {"offers", "offer"},
    "knowledge": {"knowledge"},
    "providers": {"providers", "provider", "ai-runs", "jobs", "job"},
    "operations": {"work", "workbench", "tasks", "task", "operations", "feedback", "dashboard", "queue",
                   "contacts", "templates", "template"},
    "projects": {"projects", "project", "protocol", "protocol-revisions", "import-package",
                 "handoff", "brief"},
}

CONCURRENCY_MARKERS = ("if_match", "if-match", "expected_revision", "expected_version",
                       "revision_id", "revision=", "base_revision")
AUDIT_MARKERS = ("record_audit", "AuditEvent", "audit_log", "_audit(")
HUMAN_MARKERS = ("actor", "human", "operator", "confirmed_by")


def build_app():
    """Construct the real application on a disposable synthetic workspace."""
    from knowledge_fixture import create_minimal_knowledge_tree
    from srw.api.app import create_v1_app

    root = Path(tempfile.mkdtemp(prefix="srw-api-inventory-"))
    url = f"sqlite+pysqlite:///{(root / 'inventory.db').as_posix()}"
    return create_v1_app(
        url,
        data_dir=root / "data",
        knowledge_dir=create_minimal_knowledge_tree(root / "knowledge" / "active"),
        frontend_dist=FRONTEND_DIR,
    )


def domain_for(path: str) -> str:
    segments = [seg for seg in path.strip("/").split("/")
                if seg and not seg.startswith("{") and seg not in ("api", "v1")]
    for segment in reversed(segments):
        if segment.startswith("knowledge"):
            return "knowledge"
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if segment in keywords:
                return domain
    return "static" if not path.startswith("/api/") else "other"


def endpoint_signals(endpoint) -> dict:
    try:
        source = inspect.getsource(endpoint)
    except (OSError, TypeError):
        source = ""
    return {
        "concurrency": any(marker in source for marker in CONCURRENCY_MARKERS),
        "audit": any(marker in source for marker in AUDIT_MARKERS),
        "human_actor": any(marker in source for marker in HUMAN_MARKERS),
        "basis": "endpoint-source-scan",
    }


def collect_routes(app) -> list[dict]:
    rows = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        endpoint = getattr(route, "endpoint", None)
        owner = getattr(endpoint, "__module__", "") or ""
        for method in sorted(m for m in methods if m not in IGNORED_METHODS):
            rows.append({
                "method": method,
                "path": route.path,
                "owner": owner,
                "domain": domain_for(route.path),
                "mutation": method in MUTATING_METHODS,
                "signals": endpoint_signals(endpoint) if method in MUTATING_METHODS else None,
            })
    rows.sort(key=lambda row: (row["path"], row["method"]))
    return rows


def template_to_regex(template: str) -> re.Pattern:
    """Convert a Starlette path template into a matcher for client literals."""
    out, index = [], 0
    for match in re.finditer(r"\{[^}]+\}", template):
        out.append(re.escape(template[index:match.start()]))
        out.append(r"[^/]+")
        index = match.end()
    out.append(re.escape(template[index:]))
    return re.compile("^" + "".join(out) + "$")


FRONTEND_CALL = re.compile(r"/api/v1/[A-Za-z0-9_\-/{}.$()]*")


def normalise_client_literal(literal: str) -> str:
    literal = re.sub(r"\$\{[^}]+\}", "{param}", literal)
    return literal.rstrip(".,;)]}'\"")


def collect_frontend_calls(rows: list[dict]) -> list[dict]:
    matchers = {}
    for row in rows:
        matchers.setdefault(row["path"], template_to_regex(row["path"]))
    seen: dict[str, dict] = {}
    for path in sorted(FRONTEND_DIR.glob("*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for literal in FRONTEND_CALL.findall(text):
            literal = normalise_client_literal(literal)
            if literal in seen:
                seen[literal]["files"].add(path.name)
                continue
            matched = next((tpl for tpl, rx in matchers.items() if rx.match(literal)), None)
            seen[literal] = {"literal": literal, "matched_path": matched, "files": {path.name}}
    return [
        {"literal": item["literal"], "matched_path": item["matched_path"],
         "files": sorted(item["files"])}
        for item in sorted(seen.values(), key=lambda item: item["literal"])
    ]


def build_inventory() -> dict:
    app = build_app()
    rows = collect_routes(app)
    calls = collect_frontend_calls(rows)
    by_domain: dict[str, int] = {}
    for row in rows:
        by_domain[row["domain"]] = by_domain.get(row["domain"], 0) + 1
    return {
        "schema": "srw.api-inventory.v1",
        "generated_by": "scripts/api_inventory.py",
        "source": "live Starlette route table built from srw.api.app.create_v1_app",
        "route_count": len(rows),
        "mutation_count": sum(1 for row in rows if row["mutation"]),
        "domains": dict(sorted(by_domain.items())),
        "routes": rows,
        "frontend_calls": calls,
    }


def render_doc(inventory: dict) -> str:
    lines = [
        "# SRW API 库存（R1 冻结基线）",
        "",
        "> 由 `python scripts/api_inventory.py --write` 生成，请勿手工编辑。",
        "> 本文件是 ADR-0002 / Issue #63 的 R1 产物：先冻结现有对外表面，再允许搬代码。",
        "> 它记录的是**路由与签名信号**，不是业务不变量已经验证的证明。",
        "",
        "## 规模",
        "",
        f"- 路由条目：**{inventory['route_count']}**",
        f"- 写操作（POST/PATCH/PUT/DELETE）：**{inventory['mutation_count']}**",
        f"- 前端硬编码 `/api/v1` 字面量：**{len(inventory['frontend_calls'])}**",
        "",
        "## 按业务域",
        "",
        "| 域 | 路由数 |",
        "|---|---|",
    ]
    for domain, count in inventory["domains"].items():
        lines.append(f"| {domain} | {count} |")
    unmatched = [c for c in inventory["frontend_calls"] if c["matched_path"] is None]
    lines += [
        "",
        "## 前端字面量与路由对账",
        "",
        f"- 已解析到路由模板：{len(inventory['frontend_calls']) - len(unmatched)}",
        f"- 未解析：{len(unmatched)}",
    ]
    for call in unmatched[:40]:
        lines.append(f"  - `{call['literal']}`（{', '.join(call['files'])}）")
    lines += [
        "",
        "## 路由清单",
        "",
        "| 方法 | 路径 | 域 | 归属模块 | 并发信号 | 审计信号 | 人工信号 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in inventory["routes"]:
        signals = row["signals"] or {}
        mark = lambda key: "—" if row["signals"] is None else ("yes" if signals.get(key) else "·")
        lines.append(
            f"| {row['method']} | `{row['path']}` | {row['domain']} | `{row['owner']}` | "
            f"{mark('concurrency')} | {mark('audit')} | {mark('human_actor')} |"
        )
    lines += [
        "",
        "## 边界说明",
        "",
        "- 归属模块取自运行中端点对象的 `__module__`，不是文本匹配，因此不会与真实注册表漂移。",
        "- 并发/审计/人工三列是**端点源码静态标记**（`if_match`、`record_audit`、`actor` 等），"
        "标记为 `·` 不代表该能力不存在，只代表处理器自身没有出现该标记；也可能由下游 service 实现。",
        "- 路径冻结以 `verification/api_contract/inventory.json` 为准；`test_api_contract.py` 会在路由增删时失败。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the SRW API inventory")
    parser.add_argument("--write", action="store_true", help="write inventory.json and docs/API_INVENTORY.md")
    args = parser.parse_args()

    inventory = build_inventory()
    if args.write:
        INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        INVENTORY_PATH.write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        DOC_PATH.write_text(render_doc(inventory), encoding="utf-8")
        print(f"wrote {INVENTORY_PATH.relative_to(ROOT)} ({inventory['route_count']} routes)")
        print(f"wrote {DOC_PATH.relative_to(ROOT)}")
        return 0
    print(json.dumps({k: inventory[k] for k in ("route_count", "mutation_count", "domains")},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
