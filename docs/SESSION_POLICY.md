# Business session authorization (opt-in) — production M3A contract

Status: **Local Web M3A implemented, OFF by default; WPF opt-in M3B attach source pending CI/real Windows validation; external Browser shared-Core lifecycle NOT RUN.**
This page describes production behavior at the 2026-11-06 C11 baseline, not a
hypothetical single-header policy. The business gateway is installed by
`backend/srw/api/app.py` when the **validated** opt-in flag is ON; it is
`backend/srw/runtime/business_session_gateway.py`, not a reuse of the
Host lifecycle `X-SRW-Session` secret.

## Actual authentication boundary

| Threat | With enforcement OFF (default) | M3A ON |
| --- | --- | --- |
| Cross-site page / loopback DNS rebinding | LocalBoundaryMiddleware filters origin/Host | LocalBoundaryMiddleware remains authoritative; business session adds checks |
| Another local process calling protected Core business APIs | No business session credential | Requires valid paired business Cookie; cannot self-pair by visiting the static shell |
| Same-origin malicious script / extension | Not protected by origin checks alone | Still dangerous: HttpOnly prevents direct extraction of the business Cookie by ordinary JS, **not authenticated same-origin actions** |

This is opt-in local access protection, **not** an OS identity system,
enterprise login or evidence that every Native/Browser carrier is securely
attached to one Core.

## Effective production contract

* `RECRUITMENT_SESSION_ENFORCE` follows the **three-way parser** in
  `SessionPolicy.from_environ`: unset / blank / trimmed `0` → OFF;
  trimmed `1` → ON; **all other non-empty values** (`true`, `yes`,
  `01`, `2`) and non-string values raise a fixed `ValueError`
  without echoing the supplied value. `app.py` checks this before creating
  the data directory or opening SQLite. Invalid ON cannot silently become OFF.
* OFF leaves the legacy local WPF/API behavior unchanged, with no business
  gateway installed. This compatibility mode is **not** an authenticated
  business-session deployment.
* ON Local Web requires explicit human pairing: `scripts/start_local_web.py`
  prints a random one-use, 60-second code only to a trusted interactive
  terminal. The same-origin POST
  `/api/v1/runtime/business-attach` consumes it (bounded attempts/body)
  and issues a revocable `SessionRegistry` session in
  `srw_business_session` (HttpOnly, SameSite=Strict, Path=/).
  The separate `srw_csrf` is readable for the browser to echo as
  `X-SRW-CSRF` on mutating operations. A static GET never mints a session.
* Protected reads require an authorized live **Cookie** with read scope;
  mutating operations also require write scope, valid CSRF and same-origin
  `Origin`. Query-carried credentials, raw duplicate or ambiguous Cookie
  headers, repeated CSRF headers, foreign/expired/revoked sessions or
  cross-origin writes are refused **before** business/SQLite/audit effects.
  Exact anonymous static/liveness/attach paths are specified in
  `BusinessSessionGateway.ANONYMOUS_EXACT` and `ANONYMOUS_PREFIXES`.
  Sensitive `/api/v1/info`, `/api/v1/runtime/info`, project, backup
  and workbench routes are not anonymous under ON.
* **Host lifecycle is separate from business authorization**:
  `RECRUITMENT_SESSION_TOKEN` and `X-SRW-Session` currently belong to
  `POST /api/v1/runtime/shutdown` and the existing
  `desktop/SRW.Desktop/Runtime/RuntimeApiClient.cs`.
  They must not be copied into business Cookie/JS/URL/logs. A valid
  business Cookie alone cannot shut down the Core.
* `SessionPolicy.evaluate` remains a pure, legacy *single-token model*
  with separate tests; its header-based decision contract is **not the
  current production M3A business auth mechanism**. The top-level legacy
  docstrings in `session_policy.py` include pre-M3A terminology; the
  implemented `from_environ` parser and `BusinessSessionGateway` are
  authoritative until that source-level documentation is corrected.
* **M3B remains incomplete**: opt-in WPF Host may request a separate business
  Cookie via the lifecycle-authenticated `POST /api/v1/runtime/host-business-attach`
  (only desktop/windows, only ON), authenticated with a one-use HMAC proof
  over a fresh nonce rather than transmitting the Host lifecycle secret.
  Host injects those Cookies into WebView2
  before navigation; the lifecycle token is never copied to the renderer.
  `GET /api/v1/runtime/ready` is anonymously readable under ON solely to let
  the native Host wait for readiness before attaching; it returns no candidate
  data or session secret. The Host control client sends the business Cookie
  only for its protected identity GET, not for shutdown. These are **source
  contracts pending exact-HEAD CI and real Windows WPF acceptance**, not a
  claim that WPF and an external Browser now share an independently owned Core.
  WPF and an external Browser are not yet two
  independently attached/revocable clients of a persistent shared Core;
  Host shutdown lifetime, lease ownership and same-machine T1–T10 require
  separate real Windows tests. Source/Chromium CI alone is never WPF proof.

## Rollback and acceptance

Explicit `RECRUITMENT_SESSION_ENFORCE=0` is the supported M3A no-Schema-change
rollback. Malformed configuration must refuse startup, not silently roll back.
Regression proof lives in the `convergence_tests/test_session_gate_http.py`
and policy/registry tests plus real Chromium; all denied attempts must leave
project/candidate/audit state unchanged. #43 remains OPEN until real WPF +
Browser concurrently operate on the **same authoritative Core**.

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
| pairing code | trusted interactive console only (`scripts/start_local_web.py`); a redirected stdout refuses to start | 60 s, single use, 5 attempts | exchange for one session |
| business session cookie | `srw_business_session`, `HttpOnly`, `SameSite=Strict`, `Path=/` | registry TTL | read/write business routes |
| CSRF token | `srw_csrf`, readable by same-origin JS, echoed in `X-SRW-CSRF` | same as the session | unlocks **mutating** methods only; never authorises alone |

The session token is never returned in JSON, never placed in a URL and never logged.
`POST /api/v1/runtime/shutdown` stays on its own lifecycle secret: a business cookie
cannot stop the Core.

Two delivery rules are enforced in code rather than in prose:

* **The pairing code has exactly one channel.** `scripts/start_local_web.py` writes it
  only when `sys.stdout.isatty()` is true. With `RECRUITMENT_SESSION_ENFORCE=1` and a
  redirected stdout (pipe, file, service manager, CI) the launcher refuses *before* it
  creates a workspace, a lock or a database: exit code `3`, one explanation on stderr,
  and no code is minted at all. A log collector therefore never receives a live
  credential, and a non-interactive run cannot end up as a Core nobody can attach to.
* **A pairing body is untrusted JSON, not text.** Non-ASCII strings, lone surrogate
  escapes (`"\ud800"`), non-string values, extra keys and bodies over 512 bytes are
  `401`/`413` refusals. They never raise `UnicodeEncodeError`, never echo the presented
  text and never touch pairing or session state, so a malformed attempt does not consume
  the live code either. The same rule covers `X-SRW-CSRF`: a non-ASCII header value is
  a `403`, because `hmac.compare_digest` raises on it instead of comparing.
