# Business session authorization (opt-in) - module contract

Status: **implemented as an opt-in M3A slice for the Local Web carrier, OFF by default.**
With `RECRUITMENT_SESSION_ENFORCE` unset/blank/`0` the application behaves exactly as
before and installs no gateway. With `=1`, `backend/srw/runtime/business_session_gateway.py`
runs as the outermost middleware and every business route needs a paired session. The
Windows Host / external-Browser carrier (M3B) is **not** wired yet: a WPF process that
forces `=1` without pairing fails closed rather than silently falling back to OFF.
Any other non-empty value (`true`, `yes`, `01`, `2`) refuses startup **before** the
workspace directory or SQLite file is created.

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
  parses query **keys**, decodes them up to five rounds (`%5f`, `%255f`,
  `%252573ession`), refuses any key that still cannot be decoded, and never inspects
  values, so `description=mysession=note` stays an ordinary filter. Refusing
  undecodable keys is the decisive rule: a name cannot hide behind another encoding
  layer.
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
rejection (percent-encoded names up to four layers deep, plus the value-only false
positive), the origin boundary (`cross-site` and `same-site`, plus the Origin-less Host
path), 22 ambiguous-path bypass attempts, and the absence of imports or filesystem
writes. Mutation checks were run while writing it: disabling path validation fails every
bypass subtest; rejecting only `cross-site` fails the same-site cases; restoring the
substring scan fails the encoded-key and value-only cases; removing the
"undecodable key is refused" rule fails the three deep-encoding cases and the three
malformed-key cases.

`convergence_tests/test_session_gate_http.py` - the migrated API-level cases (#148
N1-N7) plus the M3A credential model: anonymous 401 on `info` / `runtime/info` /
`projects` / `workbench` / backup listing with unchanged row counts, unknown and
foreign-instance cookies, cross-site `Origin`, missing/wrong/duplicate `X-SRW-CSRF`,
credentials in the query string (plain and percent-encoded), duplicate raw `Cookie`
headers through ASGI, pairing code single-use and never echoed, logout revocation,
TTL expiry through a fake clock, a previous Core instance's cookie, and the Host
lifecycle route still answering only its own secret (202) while a business cookie
gets 403.

## M3A credential model (Local Web)

| Credential | Where it lives | Lifetime | What it can do |
|---|---|---|---|
| pairing code | interactive console only (`scripts/start_local_web.py`) | 60 s, single use, 5 attempts | exchange for one session |
| business session cookie | `srw_business_session`, `HttpOnly`, `SameSite=Strict`, `Path=/` | registry TTL | read/write business routes |
| CSRF token | `srw_csrf`, readable by same-origin JS, echoed in `X-SRW-CSRF` | same as the session | unlocks **mutating** methods only; never authorises alone |

The session token is never returned in JSON, never placed in a URL and never logged.
`POST /api/v1/runtime/shutdown` stays on its own lifecycle secret: a business cookie
cannot stop the Core.
