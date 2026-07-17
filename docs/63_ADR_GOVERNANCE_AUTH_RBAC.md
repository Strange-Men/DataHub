# ADR 63: Governance Authentication and RBAC

- Status: Accepted for P1/P2-M9.2
- Date: 2026-07-17
- Scope: DataHub governance, retrieval and high-risk write APIs

## Context

The sealed P1/P2 lifecycle gates validate content state but do not establish caller identity. `X-DataHub-Client` is a compatibility marker for CustomerOpsAgent, not authentication. Before broader exposure, anonymous governance mutation, review, publish, index, embed, serve and archive operations need a small reversible trust boundary that does not add a user database or change retrieval contracts.

## Decision

DataHub uses runtime environment Bearer tokens with an explicit role mapping:

- `DATAHUB_AUTH_MODE=disabled|token`
- `DATAHUB_ADMIN_TOKEN`
- `DATAHUB_CLEANER_TOKEN`
- `DATAHUB_REVIEWER_TOKEN`
- `DATAHUB_SERVICE_TOKEN`
- `DATAHUB_VIEWER_TOKEN`

`disabled` is the compatibility default for tests and trusted local migration. It preserves historical request behavior. `token` requires at least one configured role token, rejects duplicate token values, never generates a default, and makes an omitted role unavailable. Startup logs may name unavailable roles but never token values.

Bearer tokens are accepted only through the `Authorization` header. Missing/malformed credentials and unknown tokens return HTTP 401 with stable codes. An authenticated role lacking a route permission returns HTTP 403 with `AUTHORIZATION_DENIED`. Token comparisons use `hmac.compare_digest` across all configured tokens.

Health endpoints remain public. `/docs`, `/redoc` and `/openapi.json` remain public for operator discovery; protected operations advertise the Bearer security scheme. This can be restricted by deployment infrastructure later without changing application authorization.

## Roles and permissions

| Role | Permissions |
|---|---|
| admin | every permission |
| cleaner | P1 import/clean/revise/read; P2 upload/extract/revise/read |
| reviewer | P1 read/review; P2 read/review |
| service | P1/P2/Unified retrieval, CustomerOpsAgent and Bad Case submission |
| viewer | P1/P2 read and P1/P2 retrieval; no mutation |

The centralized permissions are `p1.import`, `p1.clean`, `p1.revise`, `p1.review`, `p1.rag_sync`, `p1.read`, `p2.asset_upload`, `p2.extract`, `p2.revise`, `p2.review`, `p2.publish`, `p2.index`, `p2.embed`, `p2.serve`, `p2.archive`, `p2.read`, `retrieval.p1`, `retrieval.p2`, `retrieval.unified`, `agent.customerops` and `badcase.submit`.

P2 calibration: the current Review PATCH combines revised content with a required terminal decision. Cleaner may create the review workspace (`p2.revise`) but cannot call the terminal PATCH; only reviewer/admin (`p2.review`) can approve, reject or request revision. A future separate draft-revision operation, if product-approved, belongs to a later stage.

## Route policy

- Public: `/health`, `/api/health`, OpenAPI/docs.
- P1 governance reads: `p1.read`; import/clean/manual/extraction/candidate updates: the matching cleaner permission; review decisions: `p1.review`; RAG build: `p1.rag_sync`.
- P2 governance reads: `p2.read`; upload/extraction/review creation: cleaner permissions; terminal review: `p2.review`; publish/index/embed/serve/archive: their admin permissions.
- P1/P2 retrieval: the corresponding retrieval permission; Unified: `retrieval.unified`; old and v2 Agent routes: `agent.customerops`; Bad Case submission: `badcase.submit`.
- Bad Case queue reads use `p1.read`; queue mutation/draft uses `p1.revise`.

Existing `X-DataHub-Client` checks remain in addition to Bearer authorization for CustomerOpsAgent compatibility. Authentication does not change response success schemas, retrieval modes, Unified flags, fallback logic or the Agent P1-only default.

## Security and operations

- Tokens exist only in runtime environment variables and frontend `sessionStorage`.
- Tokens are not accepted in query parameters, persisted in the database, printed in logs, embedded in source/build args, or returned in errors.
- Docker Compose only passes through operator-supplied variables. Token mode with no configured tokens or duplicate values fails startup.
- The frontend adds `Authorization: Bearer ...` in the common API client, maps 401/403 to stable Chinese guidance, stores only the Token in `sessionStorage`, and resolves the displayed role from `/api/auth/me` after entry and page refresh. It never trusts a client-selected or cached role.

## Rejected alternatives

Database users, password login, JWT access/refresh tokens, OAuth/OIDC and external identity platforms are rejected for M9.2. They require identity lifecycle, rotation and migration design beyond this maintenance boundary.

## Consequences and rollback

The boundary is additive and schema-free. Trusted compatibility environments can explicitly set `DATAHUB_AUTH_MODE=disabled`; exposed Docker deployments should use `token`. Rollback is configuration-only and does not touch P1/P2 data, indexes or release tags.
