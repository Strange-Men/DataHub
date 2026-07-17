# P1/P2-M9.2 Governance Authentication and RBAC Report

- Stage: P1/P2-M9.2
- Date: 2026-07-17
- Result: PASS
- ADR: `docs/63_ADR_GOVERNANCE_AUTH_RBAC.md`

## 1. Risk background and decision

The sealed P1/P2 lifecycle already prevents unreviewed, archived and stale content from serving, but its governance routes previously accepted anonymous callers. M9.2 adds a schema-free runtime trust boundary before wider exposure: opaque Bearer tokens supplied by environment variables and mapped to centralized roles and permissions.

The decision deliberately excludes a database user system, passwords, registration, JWT refresh, OAuth/OIDC and external identity providers. Health and operator API discovery remain public. `DATAHUB_AUTH_MODE=disabled` preserves trusted local/test compatibility; `token` enforces authentication and RBAC.

## 2. Configuration and token safety

Supported variables are:

- `DATAHUB_AUTH_MODE=disabled|token`
- `DATAHUB_ADMIN_TOKEN`
- `DATAHUB_CLEANER_TOKEN`
- `DATAHUB_REVIEWER_TOKEN`
- `DATAHUB_SERVICE_TOKEN`
- `DATAHUB_VIEWER_TOKEN`

Token mode fails configuration validation when every role Token is absent and rejects duplicate role Token values. A missing individual role is unavailable and produces only a role-name warning. The application never generates defaults. Matching uses `hmac.compare_digest` against every configured Token. Token values are not accepted in URLs, written to source/database/logs, returned in errors, or stored in frontend `localStorage`.

## 3. Roles and permission matrix

| Role | Allowed | Explicitly excluded |
|---|---|---|
| admin | every P1/P2 governance, retrieval, Agent and Bad Case permission | none inside M9.2 scope |
| cleaner | P1 import/clean/revise/read; P2 upload/extract/revise/read | review, publish, index, embed, serve, archive |
| reviewer | P1/P2 read and terminal review | import, clean, upload, embed, serve, archive |
| service | P1/P2/Unified retrieval, CustomerOpsAgent, Bad Case submit | human review and governance mutation |
| viewer | P1/P2 governance reads and P1/P2 retrieval | every write and Unified/Agent |

`Role`, `Permission`, `ROLE_PERMISSIONS`, `get_current_principal()` and `require_permission()` are centralized in `backend/app/auth.py`; routes do not define their own role strings.

The current P2 Review PATCH combines content revision with a required terminal decision. Cleaner can create the review workspace, while reviewer/admin owns the terminal PATCH. Splitting draft revision from decision is deferred rather than weakening review authority.

## 4. Protected API range

- P1 writes: legacy/source import, machine/manual cleaning, extraction, candidate revision, review decisions and RAG sync.
- P2 writes: Asset upload, Extraction, Review creation/decision, Snapshot publish, Knowledge Asset lifecycle, Index, Embed, Serve and Archive.
- Read governance routes: P1/P2 read permission.
- Retrieval and Agent: separate P1, P2, Unified, CustomerOpsAgent and Bad Case-submit permissions.
- Public: `/health`, `/api/health`, `/docs`, `/redoc`, `/openapi.json`.

The old `X-DataHub-Client` check remains an additional CustomerOpsAgent compatibility gate. No success response schema, retrieval mode, RRF behavior, Unified flag, fallback rule or Agent default was changed.

## 5. 401/403 contract

| Condition | HTTP | Stable code |
|---|---:|---|
| Bearer credentials absent | 401 | `AUTHENTICATION_REQUIRED` |
| Bearer Token invalid | 401 | `AUTHENTICATION_INVALID` |
| authenticated role lacks permission | 403 | `AUTHORIZATION_DENIED` |
| runtime auth configuration invalid | 503 | `AUTH_CONFIGURATION_INVALID` |

401 responses include `WWW-Authenticate: Bearer`. Error bodies contain no Token value. Focused tests prove missing/invalid credentials and role denials are distinct.

## 6. Frontend authentication foundation

The existing console layout and governance pages were retained. A small Chinese Token control was added to the current header:

- password-type “访问令牌” input;
- apply and clear actions;
- role resolution through `GET /api/auth/me`;
- page-refresh role revalidation through `GET /api/auth/me`; only the Token, never a role claim, is retained in `sessionStorage`;
- current role display;
- common API client Authorization Header injection;
- current-tab-only `sessionStorage`;
- Chinese 401 message: “身份验证失败，请检查访问令牌。”;
- Chinese 403 message: “当前角色没有执行此操作的权限。”.

Full per-role governance workflow presentation remains M9.3 work and was not started.

## 7. Docker and script compatibility

Compose passes only operator-supplied runtime variables. Existing volumes were retained and only changed backend/frontend images were rebuilt. The P1 Harness and P2 Acceptance clients accept `--auth-token-env`, which reads an environment variable name rather than putting the Token value in process arguments.

Docker evidence:

- disabled mode: public Health 200; a governed read without Token retained historical 200 behavior;
- token mode: public Health 200; missing Token 401; cleaner Archive attempt 403;
- reviewer approved a Harness-created pending candidate: 200;
- service P1 Retrieval: 200;
- admin completed the P1 high-risk chain through the Harness;
- P1 Harness: 10/10 PASS, `customerops_vector_retrieval`, fallback false;
- P2 Acceptance: PASS under `p2-local-20260717-232033-cd82097b` using PostgreSQL/pgvector and SiliconFlow Qwen3/1536;
- P2 Ready/Serve/Archive: pre-Serve 0, served hit, post-Archive 0, embedding physically retained;
- old P2 version retrieved: false;
- final Compose state restored to `DATAHUB_AUTH_MODE=disabled`, zero configured role Tokens, PostgreSQL/backend/frontend healthy.

P2 cleanup archived only the current run-scoped Eval Knowledge Assets and deleted no database records or volumes.

## 8. Test evidence

- M9.2 Auth/RBAC focused suite: 24 passed, 2 existing FastAPI startup warnings.
- Related route/Harness/P2/Unified/Agent regression: 122 passed, 26 existing warnings.
- Authoritative ignored clean export: 411 passed, 44 existing warnings, 127.08 seconds.
- Python `compileall backend/app scripts`: PASS.
- Frontend `tsc && vite build`: PASS, 50 modules transformed.
- Docker auth smoke, P1 Harness and P2 Acceptance: PASS.
- Git diff check and secret/ignored-artifact scan: PASS.

The full suite initially exposed order-dependent database access in the newly added representative RBAC test. The test was corrected to stub only authorized business calls; production behavior was not changed. The final clean export is `m92-clean-export-20260717-231229` under ignored `.local-data/`.

## 9. Compatibility proof

- Auth disabled preserves historical callers.
- CustomerOpsAgent remains P1-only by default; Docker Harness reported `customerops_vector_retrieval` with no fallback.
- Unified remains explicit opt-in and all existing opt-in/default/fallback tests passed.
- P1 and P2 indexes remain physically separate.
- P2 archived and superseded versions remained zero-recall during Acceptance.
- No database model, schema, repository business logic, retrieval ranking, RRF or Agent strategy was changed.

## 10. Known limitations and M9.3 entry

Opaque environment Tokens are an operator boundary, not a complete identity lifecycle: there is no per-user audit identity, expiry, rotation protocol, JWT/OIDC federation or centralized secret manager integration. OpenAPI/docs remain public by ADR decision. Frontend role-aware button visibility and the complete Chinese governance workflow are intentionally deferred.

M9.3 may build role-aware usability on the central role/permission contract after this M9.2 commit is pushed. M9.3 has not started in this phase.

## 11. M9.2.1 interruption audit

The post-interruption audit found no missing backend route protection, permission-matrix error, 401/403 drift, Token disclosure, Docker configuration drift or Agent/Unified compatibility change. It did confirm one frontend trust issue: the initial M9.2 UI cached and displayed a role value from editable `sessionStorage` until a Token was manually reapplied. Backend RBAC remained authoritative, but the label could be forged locally.

The minimal M9.2.1 correction removes client role persistence. On initial load, a retained Token is revalidated through `/api/auth/me`; the UI accepts only one of the five server-returned roles and clears an invalid/unverifiable session. Focused/static coverage now rejects local role caching and requires refresh-time server validation. No governance workflow, database, retrieval, RRF, Agent default or Unified opt-in behavior changed.

Audit verification passed 38 M9.2, CustomerOpsAgent and Unified tests with two existing FastAPI startup deprecation warnings. The frontend TypeScript/Vite production build passed with 50 modules transformed. The required clean export completed with 410 passed and one unrelated timeout: the existing rebuild CLI test called the live real-provider Docker backend on `127.0.0.1:8000` and exceeded its fixed 30-second subprocess limit. With that backend temporarily stopped, the exact failed test passed in 2.42 seconds; the backend was then restored healthy. No unrelated rebuild, provider or retrieval code was changed, and the pushed M9.2 baseline remains 411/411.
