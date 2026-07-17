# P1/P2 Maintenance Hardening State

## 1. Recovery Contract

This is the recovery ledger for the additive P1/P2 maintenance line. After an interruption, read this file, `git status`, `git log -10`, and the current diff before continuing. Never reset, clean, rebase, force-push, move the sealed tags, or delete retained Docker volumes/runtime data.

## 2. Stable Baseline

| Item | Value |
|---|---|
| branch | `main` |
| maintenance-start HEAD | `dfbeb9f6d52c29c9bebb703b9e79cd490d1efb74` |
| maintenance-start origin/main | `dfbeb9f6d52c29c9bebb703b9e79cd490d1efb74` |
| P1 sealed tag | `p1-m24.3-real-embedding-online-release` |
| P2 sealed tag | `p2-m9-local-docker-release` |
| preflight | PASS: clean synchronized `main`; no unknown user changes |
| ignored runtime data | `.env` and `.local-data/` confirmed ignored |
| authority environment | local Docker Compose; Render P2 acceptance remains BLOCKED |

## 3. Guardrails

- Preserve P1 `rag_chunks`, `rag_embeddings`, the old CustomerOpsAgent endpoint and its P1-only default.
- Preserve P2 review/Snapshot/Knowledge Asset/index/serve/archive gates and physical index isolation.
- Add no destructive database migration, cloud storage, native multimodal retrieval, P3/P4 or default Unified cutover.
- Use exact staging; every stage gets focused tests, relevant regressions, a report, one or more small commits, and a normal `main` push.
- Runtime manifests and run IDs stay under ignored `.local-data/`; cleanup may affect only positively identified test-run data.

## 4. Implementation Plan

### A. Maintenance Planning

Status: **COMPLETE**. Audit documents 58/59/60 define the evidence, test backlog and additive optimization boundaries. This ledger is the implementation recovery point.

### B. M9.1 Eval Isolation and Release Safety

- Reuse existing `metadata_json`, trace IDs and runtime manifests to introduce one run scope across P1 Harness, P2 Acceptance/Eval, Unified Eval and Agent smoke.
- Filter exact-ID metrics to the current manifest/run; never change RRF to improve the metric and never delete business corpus by default.
- Add explicit, guarded cleanup only for records carrying the current test scope, if the existing public lifecycle makes this safe; otherwise retain data and rely on logical isolation.
- Add unit/script tests for scope propagation, manifest compatibility, repeat-run metrics and release invariants. Add a Docker/PostgreSQL release-safety subset where current infrastructure permits it without touching retained volumes.
- Expected files: existing acceptance/Eval/Harness scripts, sample manifest schema if required, focused backend tests, README usage notes, docs 08/09/61/62.
- Gate: three scoped repeated evaluations have stable denominators/current expected IDs, archived leakage 0, default Agent P1-only, secret scan clean, P1 Harness 10/10, P2 recall baseline retained.
- Commit: `[P1-P2-M9.1] test: isolate eval corpus and add release safety gates`.

### C. M9.2 Governance Authentication and RBAC

- Write the ADR first. Prefer environment-provided opaque Bearer tokens with explicit token-to-role mapping, constant-time comparison and no database passwords/users; document JWT/OIDC as future replacement.
- Centralize FastAPI dependencies and classify every route as public/read/service/governance. Use the smallest meaningful roles after the route inventory.
- Keep a clearly explicit disabled test/local compatibility mode; Docker maintenance acceptance uses token mode. Never change retrieval result schemas or Agent default strategy.
- Add frontend in-memory/session token handling and stable Chinese 401/403 behavior, without redesigning the console.
- Expected files: new auth module/tests/ADR, route dependency wiring, frontend API/auth state, `.env.example`, Compose runtime pass-through, README, docs 08/09/61/63.
- Gate: full permission matrix, 401/403 distinction, no token in logs/Git/URL, legacy contract tests, P1 Harness 10/10 and Docker auth smoke.
- Commit: `[P1-P2-M9.2] feat: add governance authentication and role controls`.

### D. M9.3 Frontend Governance Usability

- Correct stale P2 status/navigation and expose only real APIs.
- Complete the Chinese P2 sequence for Extraction, Review/Snapshot, publish, index, embed, explicit serve, retrieval validation, archive and trace; preserve P1 operational flow.
- Respect RBAC in controls, refresh state after mutation, confirm destructive operations, omit vectors/secrets, and keep P3/P4 visibly disabled.
- Expected files: existing frontend pages/API/types/styles plus lightweight tests if the current toolchain supports them, README and docs 08/09/61/65.
- Gate: production build, API contract/component checks, Docker browser/manual role checklist, no fake controls, P1/P2 backend regressions.
- Commit: `[P1-P2-M9.3] feat: complete chinese governance workflow`.

### E. M9.4 Reliability and No-answer Gate

- Add disposable PostgreSQL/pgvector integration tests for transactions, idempotency, concurrency and provider/storage/database/log failures; never use retained developer volumes as a test database.
- Build labeled answer/near-negative/unrelated/archive/unreviewed/query-shape samples and measure score distributions before selecting any threshold.
- Add a default-off, separately observable no-answer Shadow/active policy with profile/source-specific configuration and a stable non-error rejection contract. Do not add answer generation.
- Make only small, measured query-path fixes proven by latency/query-count evidence.
- Expected files: reliability fixtures/tests, no-answer policy/schemas/Eval samples/scripts, `.env.example`, README, docs 08/09/61/65.
- Gate: PostgreSQL/pgvector fault/concurrency suite, no rollback drift, zero archive/unreviewed leakage, calibrated Eval report, default behavior unchanged, full regressions.
- Commits: `[P1-P2-M9.4] test: harden postgres pgvector reliability`; if policy code is independently ready, `[P1-P2-M9.4] feat: add calibrated no-answer gate`.

### F. M9.5 Maintenance Release Closure

- Run clone-style Docker config/build/up/health/persistence; full P1/P2/Unified/Agent/auth/frontend/no-answer chains; compileall, full backend tests, frontend build, secret and diff audits.
- Add docs 66 and close README/status/checklist/ledger without adding a major feature.
- Commit the closure report, push `main`, then create the annotated tag only if every forced gate passes.
- Final tag: `p2-m9.5-maintenance-hardening` with the authorized message.
- Render Deployment Acceptance remains BLOCKED and is not a local-release gate.

## 5. Hard Stops

Stop only for a branch/remote divergence or unknown user change; need for history rewrite or destructive migration; any requirement to break the sealed P1/P2 contracts/tags; persistent archive or unreviewed leakage; unrecoverable P1 Harness failure; volume deletion risk; a committed secret; or scope expansion into P3/P4.

## 6. Stage Ledger

| Stage | Status | Commit | Push | Tests / runtime evidence | Next action |
|---|---|---|---|---|---|
| Planning | COMPLETE | included in the M9.1 phase commit | pushed with M9.1 | audit/plans 58/59/60 retained | no separate planning commit required |
| M9.1 | COMPLETE | `[P1-P2-M9.1] test: isolate eval corpus and add release safety gates` (this phase commit; see Git log for hash) | normal `main` push verified in final handoff | focused 37; clean-export 387; compile/build PASS; P1 10/10; three P2/Unified scoped Evals stable; Agent/cleanup/secret gates PASS | stop; M9.2 has not started |
| M9.2 | COMPLETE | `[P1-P2-M9.2] feat: add governance authentication and role controls` (this phase commit; see Git log for hash) | normal `main` push at phase closure | focused 24; clean-export 411; compile/build PASS; Docker auth smoke; P1 10/10; P2 Acceptance PASS | stop; M9.3 has not started |
| M9.3 | COMPLETE | `[P1-P2-M9.3] feat: complete chinese governance workflow` (this phase commit; see Git log for hash) | normal `main` push at phase closure | focused/contract 99; frontend build PASS; Docker five-role browser checklist PASS | stop; M9.4 has not started |
| M9.4 | PENDING | PENDING | PENDING | PENDING | enter only after M9.3 push |
| M9.5 | PENDING | PENDING | PENDING | PENDING | enter only after M9.4 push |

## 7. Current Risks and Next Action

- Auth must not silently make current local/Docker clients unusable; the ADR and route matrix precede enforcement.
- Eval isolation must not become production ranking logic or broad data deletion.
- Real PostgreSQL tests require a disposable database/schema strategy; retained Compose data is evidence, not a destructive test fixture.
- No-answer thresholds require measured labeled data and remain disabled until calibrated.

M9.1 closure: run-scoped Eval isolation and release-safety gates are complete. Runtime manifests remain ignored, all test Knowledge Assets were logically archived with zero record deletion, non-test P2 state and P1 index counts were unchanged, and all four opt-in flags were restored false. The phase report is `docs/62_M9_1_EVAL_ISOLATION_AND_RELEASE_SAFETY_REPORT.md`.

Historical M9.1 boundary: M9.2 was authorized to start with the authentication ADR and route/role inventory. The completed M9.2 state is recorded below.

M9.2 closure: centralized environment Bearer Token authentication and RBAC protect P1/P2 governance, retrieval and Agent APIs without a schema change. Disabled mode remains compatible; token mode has stable 401/403 behavior, constant-time matching and duplicate/no-Token safety validation. Docker auth smoke, P1 Harness 10/10, P2 Acceptance, 411-test clean export, compileall and frontend build passed. Runtime Tokens were removed and Compose was restored to disabled. The ADR is `docs/63_ADR_GOVERNANCE_AUTH_RBAC.md`; the report is `docs/64_M9_2_GOVERNANCE_AUTH_RBAC_REPORT.md`.

Historical entry: M9.3 Frontend Governance Usability was authorized after the M9.2 push. Its completed state is recorded below.

M9.2.1 interruption audit: the backend route inventory, centralized role matrix, Auth core, Docker configuration and Agent/Unified compatibility were complete. One frontend trust issue was confirmed and corrected: editable browser state can no longer supply the displayed role. Only the Token is retained in `sessionStorage`, and `/api/auth/me` revalidates the allow-listed role after page refresh and Token apply. The M9.2/Agent/Unified audit suite passed 38 tests and the frontend build passed. At that audit boundary M9.3 had not started.

M9.3 closure: the Chinese frontend is now task-flow oriented, exposes only real P1/P2 and retrieval APIs, centralizes five-role UX from `/api/auth/me`, distinguishes P2 ready/serving, confirms retrieval-visibility changes, and displays the full Source Trace without vectors or Secrets. P3/P4 remain explicitly disabled. Focused/contract regressions passed 99 tests, the production build passed, and retained-volume Docker browser checks covered all five roles, 401, Token clear/reload, serving/archived states, Agent P1-only and Unified opt-in. Docker was restored to disabled with zero role Tokens. Report: `docs/65_M9_3_FRONTEND_GOVERNANCE_USABILITY_REPORT.md`.

Next authorized entry: M9.4 Reliability and No-answer Gate. M9.4 has not started.
