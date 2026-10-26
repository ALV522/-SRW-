"""Read-only, bounded GitHub PR snapshot collector (#135).

This tool reads GitHub, writes a sanitized local JSON report only, and NEVER
changes source, labels, rulesets, or PR state. No token/review text is emitted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from scripts.check_pr_merge_readiness import assess

REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
VERDICT = re.compile(r"(?im)^\s*(?:verdict|结论)\s*[:：]\s*(ACCEPT|NEEDS_CHANGES|BLOCK)\s*$")


class GitHubReader:
    def __init__(self, token: str):
        if not token:
            raise ValueError("GITHUB_TOKEN is needed for read-only GitHub API")
        self.token = token

    def request(self, path: str, body: dict | None = None):
        if not path.startswith("/"):
            raise ValueError("only GitHub root-relative API paths are accepted")
        url = ("https://api.github.com/graphql" if path == "/graphql"
               else "https://api.github.com" + path)
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SRW-readonly-merge-review",
            "Content-Type": "application/json",
        }
        try:
            request = urllib.request.Request(
                url, data=raw, method="POST" if raw else "GET", headers=headers
            )
            with urllib.request.urlopen(request, timeout=20) as result:
                return json.load(result)
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            # Do not log exception details: request metadata might contain token.
            raise RuntimeError("read-only GitHub API collection failed") from None


def _sha(data: dict, *path: str) -> str:
    for key in path:
        if not isinstance(data, dict):
            raise ValueError("incomplete SHA response")
        data = data.get(key)
    if not isinstance(data, str) or not re.fullmatch(r"[0-9a-f]{40}", data):
        raise ValueError("missing or invalid GitHub SHA")
    return data


def _pages(client, url: str, collection: str | None = None) -> list[dict]:
    rows = []
    for page in range(1, 12):
        response = client.request(url + ("&" if "?" in url else "?")
                                  + f"per_page=100&page={page}")
        chunk = response.get(collection) if collection and isinstance(response, dict) else response
        if not isinstance(chunk, list) or not all(isinstance(x, dict) for x in chunk):
            raise RuntimeError("malformed check-run or review pagination")
        rows.extend(chunk)
        if len(chunk) < 100:
            if (collection and isinstance(response.get("total_count"), int)
                    and len(rows) != response["total_count"]):
                raise RuntimeError("incomplete check-run pagination")
            return rows
    raise RuntimeError("GitHub pagination exceeds bounded collection")


def _unresolved_threads(client, owner: str, repo: str, number: int) -> int:
    query = (
        "query($owner:String!,$repo:String!,$number:Int!,$cursor:String){"
        "repository(owner:$owner,name:$repo){pullRequest(number:$number){"
        "reviewThreads(first:100,after:$cursor){nodes{isResolved}"
        "pageInfo{hasNextPage endCursor}}}}}"
    )
    cursor = None
    count = 0
    for _ in range(15):
        value = client.request("/graphql", {"query": query, "variables": {
            "owner": owner, "repo": repo, "number": number, "cursor": cursor,
        }})
        if not isinstance(value, dict) or value.get("errors"):
            raise RuntimeError("cannot verify unresolved GitHub review threads")
        try:
            batch = value["data"]["repository"]["pullRequest"]["reviewThreads"]
            nodes, page = batch["nodes"], batch["pageInfo"]
            if not isinstance(nodes, list) or not isinstance(page["hasNextPage"], bool):
                raise TypeError()
            for node in nodes:
                if not isinstance(node, dict) or not isinstance(node.get("isResolved"), bool):
                    raise TypeError()
                count += int(not node["isResolved"])
            if not page["hasNextPage"]:
                return count
            cursor = page["endCursor"]
            if not isinstance(cursor, str) or not cursor:
                raise TypeError()
        except (KeyError, TypeError) as exc:
            raise RuntimeError("GitHub review-thread state is incomplete") from exc
    raise RuntimeError("too many review threads to audit safely")


def _verdict(review: dict) -> str:
    if review.get("state") == "CHANGES_REQUESTED":
        return "BLOCK"
    if review.get("state") == "APPROVED":
        return "ACCEPT"
    body = review.get("body")
    if isinstance(body, str):
        match = VERDICT.search(body)
        if match:
            return match.group(1).upper()
    return "UNKNOWN"


def collect(client, repository: str, number: int) -> dict:
    if not REPO.fullmatch(repository) or not 1 <= number <= 1000000:
        raise ValueError("invalid repository or PR number")
    owner, repo = repository.split("/", 1)
    if owner in {".", ".."} or repo in {".", ".."}:
        raise ValueError("unsafe GitHub repository path segment")
    prefix = f"/repos/{owner}/{repo}"
    first_main = _sha(client.request(prefix + "/branches/main"), "commit", "sha")
    first_pr = client.request(prefix + f"/pulls/{number}")
    head = _sha(first_pr, "head", "sha")
    base = _sha(first_pr, "base", "sha")
    base_ref = first_pr.get("base", {}).get("ref")
    author = first_pr.get("user", {}).get("login")
    if base_ref != "main" or not isinstance(author, str) or not author:
        raise RuntimeError("target branch or author identity is unavailable")
    checks = _pages(client, prefix + f"/commits/{head}/check-runs", "check_runs")
    reviews = _pages(client, prefix + f"/pulls/{number}/reviews")
    unresolved = _unresolved_threads(client, owner, repo, number)
    later_main = _sha(client.request(prefix + "/branches/main"), "commit", "sha")
    later_pr = client.request(prefix + f"/pulls/{number}")
    if (first_main != later_main or head != _sha(later_pr, "head", "sha")
            or base != _sha(later_pr, "base", "sha")):
        raise RuntimeError("main or PR SHA moved while collecting snapshot")
    return {
        "main_sha": later_main,
        "pr": {"head_sha": head, "base_sha": base, "base_ref": base_ref,
               "draft": later_pr.get("draft"), "author_account": author},
        "checks": [{"name": x.get("name"), "head_sha": x.get("head_sha"),
                    "status": x.get("status"), "conclusion": x.get("conclusion")}
                   for x in checks],
        "reviews": [{"head_sha": x.get("commit_id"),
                     "verdict": _verdict(x),
                     "reviewer_account": (x.get("user") or {}).get("login")}
                    for x in reviews],
        "unresolved_review_threads": unresolved,
        "preflight": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="ALV522/-SRW-")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        state = collect(GitHubReader(os.environ.get("GITHUB_TOKEN", "")),
                        args.repo, args.pr)
        args.output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        status = assess(state)
    except (ValueError, RuntimeError, OSError):
        print('{"collection":"BLOCKED","merge_authorized":false}', file=sys.stderr)
        return 2
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
