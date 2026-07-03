# DataHub Development Rules

## 1. Development Rhythm

- Build in small iterations.
- Each round must have one clear goal.
- Each round must define:
  - Allowed files or modules.
  - Forbidden files or modules.
  - Input and output expectations.
  - Acceptance criteria.
  - Test or verification method.
- Do not implement the entire project in one pass.
- Do not mix refactoring with new feature work unless explicitly planned.

## 2. Phase Discipline

This document defines permanent development guardrails. The current milestone is tracked in `docs/08_DEV_STATUS.md`.

Phase rules:

- Follow the current milestone stated in `docs/08_DEV_STATUS.md`.
- Do not start the next milestone until the current milestone is verified and checkpointed.
- Do not implement future roadmap phases before they are explicitly started.
- Documentation-only rounds must not modify business code.
- Code rounds must keep documentation aligned with implemented behavior.

## 3. Confirmed Technical Direction

Confirmed:

- Frontend: React + TypeScript.
- Backend: FastAPI + Python.

Not finalized yet:

- Database.
- Vector database.
- ORM.
- RAG orchestration framework.
- Background task system.
- Deployment platform.

These must remain candidate decisions until explicitly selected.

## 4. Scope Control Rules

Do not implement in phase one:

- Full multimodal support.
- Image OCR.
- Image caption generation.
- SKU binding.
- Video understanding.
- Sales Agent.
- Operations Agent.
- Real model fine-tuning.
- MCP.
- Spark / Hive / Flink / lakehouse architecture.
- Complex BI.
- Complex multi-tenant permissions.

Architecture may reserve extension points, but implementation must wait.

## 5. Data Layering Rules

The following logical layers must remain separated:

```text
raw data
sanitized data
knowledge drafts
approved knowledge
RAG index
Bad Cases
```

Rules:

- Raw data must not be used for extraction directly.
- Sanitized data may be used for extraction.
- Knowledge drafts may be reviewed but not retrieved by CustomerOpsAgent.
- Approved knowledge may be indexed.
- Only indexed approved knowledge may be retrieved by CustomerOpsAgent.
- Bad Cases may create or update drafts, but must not directly update the RAG index.

## 6. Safety Rules

- Un-desensitized data must never enter RAG.
- Unreviewed knowledge must never enter RAG.
- Raw records must never be returned to CustomerOpsAgent.
- Rejected knowledge must never be retrieved.
- Archived knowledge must not appear in future retrieval results.
- Logs must not print private data, API keys, or secrets.
- Error responses must not expose internal stack traces or private raw content.
- User input must be validated and length-limited.

## 7. CustomerOpsAgent Boundary

CustomerOpsAgent can:

- Query approved knowledge through the retrieval API.
- Submit Bad Cases through the feedback API.

CustomerOpsAgent cannot:

- Access the DataHub database directly.
- Modify knowledge directly.
- Approve knowledge.
- Index knowledge.
- Read raw imported data.
- Read unapproved drafts.
- Bypass DataHub review workflow.

## 8. Module Split Rules

Use clear module boundaries once implementation begins:

- API layer: request and response handling.
- Service layer: business workflow.
- Data layer: persistence and queries.
- Schema layer: request, response, and domain models.
- RAG layer: retrieval and indexing abstraction.
- Extraction layer: knowledge extraction abstraction.
- UI layer: React components and pages.
- Tests layer: behavior verification.

Do not place all core logic in one large file.

## 9. API Contract Rules

- API paths should remain stable after implementation starts.
- Field names should not be changed casually.
- Response shapes should not be changed without updating `04_API_CONTRACT.md`.
- Any API change must update related tests and documentation.
- CustomerOpsAgent-facing APIs require extra stability.

## 10. Git And Recovery Rules

- Initialize Git only when the project setup step begins.
- Commit after each accepted small feature.
- Tag after each accepted milestone.
- After each development stage, run the relevant verification, commit, tag, and push to the remote repository by default unless the user explicitly says not to.
- Create a branch before major refactoring.
- Do not continue multiple large changes without a clean checkpoint.
- Do not commit secrets, `.env` files, caches, temporary files, or generated private data.

## 11. Documentation Rules

Keep these documents current:

- `docs/00_PROJECT_SCOPE.md`
- `docs/01_IDEA_PRESSURE_TEST.md`
- `docs/02_PRD.md`
- `docs/03_ARCHITECTURE.md`
- `docs/04_API_CONTRACT.md`
- `docs/05_DEV_RULES.md`
- `docs/06_TECH_STACK_CANDIDATES.md`
- `docs/07_ACCEPTANCE_CRITERIA.md`

During implementation, maintain:

- `docs/08_DEV_STATUS.md`
- `docs/CHANGELOG.md`

## 12. Repository Content Rules

- Do not put private interview materials into the project repository.
- Do not put personal resume packaging material into the project repository.
- Do not commit real customer private data.
- Use sample or anonymized data for demos and tests.
- Keep project documentation focused on product, architecture, APIs, and development process.

## 13. Error Handling Rules

When errors occur:

1. Reproduce the error.
2. Preserve the relevant error message.
3. Classify the error.
4. Locate the smallest likely root cause.
5. Make the smallest related fix.
6. Run the relevant verification.
7. Document important behavior changes.

Do not respond to errors by rewriting unrelated architecture.
