# Business session authorization (opt-in) - module contract

Status: **NOT IMPLEMENTED in the running Core.** `backend/srw/supervisor/session_policy.py`
is a pure decision module; no middleware, route, launcher or Host path calls it yet.
Track A owns the integration. Until then, the only protections on business writes are
the local boundary: loopback-only bind, unique `Host`, same-origin `Origin` /
`Sec-Fetch-Site`, duplicate-source-header rejection.

## What problem it solves - and what it does not

| Threat | Today | After enabling the gate |
|---|---|---|
| Cross-site page / DNS rebinding against `127.0.0.1` | Mitigated by the local boundary | Still mitigated; a valid token does not bypass the origin check |
| **Another process or user on the same machine** calling the API | **Not mitigated** - no credential at all | Mitigated: the caller must present the session token |
| Same-origin script / extension already inside the page | Not mitigated | **Still not mitigated.** A token cannot be hidden from same-origin script |

The gate is therefore "minimal authentication against local processes", not
"authenticated sessions" in the web sense, and must never be described as the latter.

## Contract

* `RECRUITMENT_SESSION_ENFORCE=1` enables the gate. Only the literal `1`; every other
  value and the absent variable leave it disabled. Default **off** so the Native WPF
  Host, which sends no `Origin` and no token today, keeps working unchanged.
* Credential: `X-SRW-Session` header, compared in constant time. It is **never**
  accepted from the query string: query strings end up in logs and history. Detection
  parses query **keys** after percent-decoding (two rounds, so `session%5ftoken` and
  `%255f` are seen through) and never inspects values, so `description=mysession=note`
  stays an ordinary filter. An undecodable key that still looks session-related
  (`session%zz=...`) is refused conservatively.
* Anonymous `GET`/`HEAD` allowlist (exact match): `/health/live`, `/health/ready`,
  `/api/v1/runtime/ready`, `/api/v1/runtime/capabilities`, plus the local static bundle
  `/v1` and `/v1/...`. `/api/v1/info`, `/api/v1/runtime/info` and
  `/api/v1/runtime/live` expose instance/release/session identifiers and are **not**
  anonymous.
* Every other path and every other method (including `OPTIONS`) requires the token.
* Cross-origin (`Origin` not in the configured set, or `Sec-Fetch-Site` equal to
  `cross-site` **or** `same-site`) is refused with `403` even when the token is valid:
  `same-site` is not `same-origin`, so another loopback port is still a different
  origin. A caller that sends no Fetch Metadata at all (the Native Host) is not
  rejected for the absence. If the gate is enabled without a configured origin set,
  browser-originated (`Origin`-bearing) requests are refused, while the Origin-less
  Host path still works.
* Enabling the gate with no token configured fails closed: non-anonymous requests get
  `401 session_token_not_configured` instead of falling open.
* Ambiguous paths are **refused, not normalised** (`400 ambiguous_path`): percent
  encoding, back slashes, duplicate slashes, `.`/`..` segments, `;`, `?`, `#`,
  control/non-ASCII characters, trailing dots or spaces, and over-long paths. A decoder
  that rewrites the path would give an attacker a second parser to disagree with.
* `SessionPolicy.rotated(new)` returns a policy that accepts the new token and rejects
  the old one; `revoked` tokens are rejected with `401 session_token_invalid`.
* Decisions carry only `allowed` / `status_code` / `reason`. The module imports nothing
  but `hmac`, `dataclasses`, `typing` and the pure `urllib.parse` decoder, so a rejected
  request cannot write, log or
  audit anything. **No audit event is produced by authorization failures.**

## Integration checklist (Track A)

1. Middleware placed after `LocalBoundaryMiddleware`, opt-in, applied to all methods.
2. `/api/v1/runtime/info` adds `businessSessionTokenRequired`, so a client can detect the
   requirement before its first failing call.
3. `401` responses carry `WWW-Authenticate: SRW-session` and a "reopen from the Host"
   hint for the SPA; the SPA must render that state rather than a blank page.
4. `RECRUITMENT_SESSION_ENFORCE=0` (or unset) is the 30-second rollback; it needs no data
   migration and changes no Schema.

## Tests

`convergence_tests/test_session_policy.py` - 37 green cases covering default-off
compatibility, the exact allowlist, token missing/invalid/rotated/revoked, query-key
rejection (including percent-encoded key names and the value-only false positive), the
origin boundary (`cross-site` and `same-site`, plus the Origin-less Host path), 22
ambiguous-path bypass attempts, and the absence of imports or filesystem writes.
Mutation checks were run while writing it: disabling path validation fails every bypass
subtest; rejecting only `cross-site` fails the same-site cases; falling back to a raw
substring scan of the query string fails both the encoded-key and the value-only cases.

The 7 API-level `200 -> 401/403` RED cases need the middleware and belong to a separate
test-only PR after Track A approves the integration.
