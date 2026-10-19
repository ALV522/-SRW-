# E5 — Per-carrier attach and pinned Core identity (synthetic-only)

## Engineering question

E4 showed that one independently-owned Core can serve two UI carriers.
But **loopback-only HTTP is not user authentication**: another local process
may be able to reach an exposed port. Worse, reconnecting to the same port
without verifying Core identity risks attaching to the wrong instance.

E5 adds an isolated protocol experiment while keeping the real C11
production API, migrations, Windows Host and main branch untouched.

## What has been built

- `e5_attach.py`: a protected E3 HTTP carrier whose GET/PATCH endpoints
  require a browser attach capability and a live matching Core identity.
- `e5_owner.py`: an independent owner that starts one E4 disposable Core,
  replaces E4 open carriers with protected E5 carriers, and manages their
  detach/re-attach lifecycle.
- `run_e5_demo.py`: an E5 Windows/Python smoke procedure that checks
  unprivileged access denial, two-carrier business state, capability refresh
  and independent process ownership.
- `browser_acceptance/test_e5_real_backend.py`: actual Chromium security
  and business tests including unauthorized requests and identity invalidation.
- `START_E5.cmd`: source-demo Windows entry (no EXE).

## Local attach exchange

1. The temporary Core supervisor creates a separate 256-bit random
   capability for each browser-facing carrier.
2. A specific browser opens the guarded bootstrap URL.
3. On a valid capability and matching live Core identity, the server issues
   an HttpOnly, SameSite=Strict cookie and HTTP 303 redirect to `/`.
4. UI code receives **no capability in its DOM, JavaScript state or API JSON**.
5. Other requests require the matching cookie and must pass same-origin,
   Host and core-identity checks.
6. The owner invalidates the prior capability when a carrier detaches;
   its reattachment creates a new server and token.

The cookie name is distinct per carrier because browser cookies are scoped by
**hostname, not port**. Two `127.0.0.1` carrier ports cannot safely rely on
different values of the same cookie name.

Core identity is pinned to:
`product`, `instanceId`, `sessionId`, `dataScopeId`, `version`,
`schemaVersion`. Every request rechecks the live Core. If it is dead or its
identity changes, the proxy returns HTTP 503 rather than silently continuing.

All writes continue to use only the E3 synthetic Action Plan route with its
SQLite revision CAS. No production candidate or Windows data root is opened.

## Known limits (not product authentication)

- This is a **localhost synthetic experiment**, not a login system.
- HTTP loopback lacks TLS and provides no separate multi-user or process
  identity proof.
- The initial capability is necessarily delivered via a URL; browser plugins,
  local process inspection or OS-level compromise are out of scope.
- No persistent browser session revocation service, role-based access policy,
  remote authentication or Windows native secret store exists.
- A production service must authenticate the local attach initiator, use
  appropriately scoped short-lived credentials, prevent CSRF, and bind all
  business actor identity to the transaction/audit trail.
- A local port is not a security boundary against other software already
  running with the user's account privileges.

E5 is a technical proof for an attach protocol, not a license to expose the
Core over a LAN or internet.

## Verification criteria

A successful E5 CI run must show:

1. Unattached browser/API requests get 403.
2. Wrong-carrier capability cannot attach to another carrier.
3. Successful attach leads to the correct HTML/UI via 303, with Strict
   HttpOnly cookie and no visible token in JavaScript.
4. Two independently attached browser contexts read/write the same real
   temporary Core Action Plan state.
5. Detach/reattach invalidates the previous cookie and preserves Core state.
6. Forced identity mismatch or Core death fails closed with 503.
7. Existing E1–E4 behavior is unchanged.
8. Windows launcher and full source ZIP are accepted via separate CI.

Never report E5 as accepted until a concrete successful run of all these tests
is available.

## Future real Web + EXE requirements

Move from E5 capabilities to a formal `Core Supervisor -> Carrier` protocol,
with verified OS/user process identity, session lifespan, protected
credential exchange, version/schema handshake and authenticated business
mutation actors. The Native WPF/WebView2 Host remains a separate unaccepted
deliverable. See `DUAL_CARRIER_PRODUCT_CONTRACT.md`.
