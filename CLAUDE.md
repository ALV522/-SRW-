# SRW mandatory agent onboarding

STOP: read AGENTS.md completely and follow every required document in its ordered list before editing this repository. Governance G1, product charter, release version policy, dual Windows/Web carrier design, synthetic-only CI and exact-artifact acceptance rules apply to all changes. Document the exact SHA, VERSION, Schema and tests before claiming completion. No blind "continue development" changes, no new business core/UI rewrite, and no invented PASS.

Temporary G1 rule: branch protection is not enabled. Read docs/NO_BRANCH_PROTECTION_PROTOCOL.md, create clean non-main task branch, run agent_preflight.py --issue <issue> --acknowledge-reading, use PR and full exact-SHA CI, NEVER direct-push main.
