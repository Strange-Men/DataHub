# P1/P2-M9.5 Maintenance Release Closure Report

## 1. Release Decision

P1/P2 Maintenance Hardening M9.1 through M9.4B is **PASS** for the authoritative local Docker release boundary. The independent No-answer holdout exceeds every release line without threshold tuning. This closure adds only release evidence, the independent challenge fixture, and holdout reporting; it adds no product feature and does not start P3/P4.

Render P2 Deployment Acceptance remains **BLOCKED** by the previously recorded persistent-storage requirement. Nothing here claims online Render persistence or production-scale acceptance.

## 2. Maintenance Completeness Matrix

| Stage | Capability | Status | Evidence |
|---|---|---:|---|
| M9.1 | run-scoped Eval corpus, namespace and manifest | PASS | scoped manifests and focused regression |
| M9.1 | cleanup safety and repeat-run isolation | PASS | logical archive only; current-run IDs; zero leakage |
| M9.2 | Bearer Token, centralized RBAC and `/api/auth/me` | PASS | 401/403 and role matrix regression |
| M9.2 | constant-time matching and Secret safety | PASS | duplicate-token guard and final secret audit |
| M9.3 | Chinese P1/P2 flows and five-role UX | PASS | frontend contracts and production build |
| M9.3 | Ready/Serving, Archive, Source Trace and no fake actions | PASS | P2 Acceptance and UI contracts |
| M9.4A | offline mock/provider and subprocess isolation | PASS | environment-isolation regression |
| M9.4A | PostgreSQL/pgvector, transactions, concurrency, idempotency | PASS | isolated PostgreSQL suite 5/5 |
| M9.4A | independent Docker project and bounded recovery | PASS | parallel healthy stacks; test resources removed |
| M9.4B | disabled/shadow/enforced answerability gate | PASS | focused regression and 26-sample calibration Eval |
| M9.4B | outage distinction, Agent abstention and leakage gates | PASS | stable contracts and runtime acceptance |
| Deployment | local Docker maintenance release | PASS | all release gates below |
| Deployment | Render P2 persistent production acceptance | BLOCKED | Persistent Disk remains unavailable/unverified |
| Roadmap | production-scale calibration, OIDC, cloud storage, P3/P4 | DEFERRED | outside M9.5 scope |

## 3. Risks Closed and Final Architecture

- M9.1 removed historical-corpus drift from exact-ID metrics through `run_id`, `datahub-eval:<run_id>` and ignored manifests. Cleanup archives only manifest-owned test knowledge and never deletes records.
- M9.2 added environment Bearer Tokens, five centralized roles and capability permissions. Disabled mode preserves trusted-local compatibility; token mode distinguishes stable 401 and 403. Health and API discovery remain public.
- M9.3 made the Chinese console a real backend-driven P1/P2 task flow using `/api/auth/me`, Ready/Serving separation, Archive confirmation and Source Trace without vectors or Secrets.
- M9.4A separated offline, PostgreSQL integration and Docker E2E tests. The test project uses test-named databases, ports, network and volumes and can run beside development.
- M9.4B added deterministic answerability without changing RRF, database schema, physical indexes, default P1-only Agent behavior or Unified opt-in.

## 4. No-answer Calibration and Holdout

The original run-scoped calibration set has 26 samples (11 answerable, 15 no-answer/failure). Answerable precision/recall, No-answer precision/recall/F1 and reason accuracy were 1.0; false-answer, false-rejection, archived leakage and old-version leakage were 0.

M9.5 adds a disjoint 48-sample holdout with 24 answerable and 24 no-answer cases. No query text is copied from the original set. Coverage includes synonyms, typos, long/short and multi-intent questions, keyword-only false friends, similar product/policy confusion, archived, superseded and Ready-not-Serving sources, conflicts, guessing/fabrication prompts, reliable single branches, two weak branches, and Provider/Database faults. The run-scoped results stay under ignored `.local-data/no-answer-eval/`.

| Metric | Shadow | Enforced | Release line |
|---|---:|---:|---:|
| answerable precision | 0.9583 | 0.9583 | observed |
| answerable recall | 0.9583 | 0.9583 | >= 0.95 |
| no-answer precision | 0.9583 | 0.9583 | >= 0.95 |
| no-answer recall / F1 | 0.9583 / 0.9583 | 0.9583 / 0.9583 | observed |
| false-answer rate | 0.0417 | 0.0417 | <= 0.05 |
| false-rejection rate | 0.0417 | 0.0417 | observed |
| reason accuracy | 0.9583 | 0.9583 | observed |
| archived / old-version leakage | 0 / 0 | 0 / 0 | 0 / 0 |

Shadow and enforced intentionally share deterministic decision metrics; only enforced mode suppresses unreliable Agent evidence and emits the safe abstention text.

Release thresholds remain P1 `0.45`, P2 `0.55`, Unified normalized ratio `1.0`, minimum evidence `1`, and ambiguous-query minimum length `4`. Within +/-0.05, P1 had 3 samples and 1 error, P2 had 5 and 1 error, Unified had 12 and 0 errors. These are isolated boundary errors, not a systematic distribution failure. The holdout was not used for tuning; no threshold changed.

## 5. Final Release Gates

| Gate | Result |
|---|---|
| M9.1-M9.4B focused matrix | 95 passed, 2 warnings, 3.23 s |
| PostgreSQL 16 / pgvector integration | 5 passed, 3.93 s |
| P1 Pipeline Harness | 10/10 PASS in isolated enforced test backend |
| P2 Local Acceptance | PASS; Ready 0, Serve hit, Archive 0 |
| P2 replacement | old version not retrieved; physical vector retained |
| CustomerOpsAgent smoke | legacy/default P1; disabled explicit opt-in safely fell back to P1 |
| Unified smoke | stable 503 `unified_retrieval_disabled`; no implicit enablement |
| Auth/RBAC | PASS in focused and full regression |
| clean-export backend | 465 collected; 460 passed, 5 explicit PG skips, 44 warnings, 85.15 s |
| frontend contracts | 8 passed in focused/full regression; no npm test script exists |
| frontend production build | PASS, 54 modules, 1.18 s |
| archived / old-version leakage | 0 / 0 |
| independent test resources | removed; no residual test containers or volumes |
| development stack/data | three services healthy; development volumes not deleted |
| secret and diff audit | PASS at Git closure |

Development and `datahub-m95-test` were simultaneously healthy on independent ports (`8000/5433` and `18000/55432`). Only test-project containers, network and volumes were removed.

## 6. Known Limits and Deferred Work

- The holdout is a compact engineering set, not production traffic. Broader multilingual/domain calibration, drift monitoring and alerts remain deferred.
- OIDC, identity lifecycle, automated Token rotation and an external secret manager remain deferred.
- Native multimodal providers, cloud object storage, high-scale ANN/load acceptance and P3/P4 remain deferred.
- Render P2 persistent deployment remains blocked and was not tested online.

## 7. Rollback and Release Identity

Rollback is Git-based: deploy the prior pushed commit or protected `p2-m9-local-docker-release`, restore documented environment switches, and restart without deleting PostgreSQL or asset volumes. M9.5 adds no schema migration.

Closure commit title: `[P1-P2-M9.5] release: close maintenance hardening`.

Annotated tag: `p2-m9.5-maintenance-hardening`, message `P1/P2 maintenance hardening release`. The exact commit and tag object are verified after commit because a commit cannot embed its own hash.

## 8. Final Boundary

P1/P2 Maintenance Hardening is closed for local Docker. P3/P4 have not started; later work requires separate authorization and must preserve the release gates and historical tags.

## 9. Post-release Validation Patch

The independent final validation retained this report and `p2-m9.5-maintenance-hardening` as immutable release evidence. It confirmed no functional, security, data-integrity or test-isolation defect, but reproduced two P2 Source Trace query-amplification defects. A bounded bulk lineage load reduced Knowledge Asset page queries from 82 to 2; bulk retrieval governance loading plus a fresh lifecycle race gate reduced P2 retrieval from 220 to 8 SQL statements while retaining one Query Embedding call.

Affected regressions, isolated PostgreSQL/pgvector, P1 Harness, P2 Acceptance, Unified/Agent smoke, frontend build and a final clean-export (`463 passed, 5 skipped`) passed. A separate 24-sample exploratory No-answer boundary audit was not used for tuning and retained zero archived/old-version leakage. The patch is documented in `docs/69_P1_P2_FINAL_POST_RELEASE_VALIDATION_AND_FREEZE_DECISION.md`; it receives a new patch tag and does not move this release tag. Render P2 persistence remains BLOCKED and P3/P4 remain unstarted.
