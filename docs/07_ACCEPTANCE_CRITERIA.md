# DataHub Acceptance Criteria

This document defines milestone-level acceptance criteria. Each milestone should be accepted before moving to the next one.

## M0 Documentation Baseline

Goal:

- Solidify phase-one scope, architecture direction, API draft, development rules, technical candidates, and milestone acceptance criteria.

Acceptance criteria:

- `docs/00_PROJECT_SCOPE.md` exists and defines what DataHub is and is not.
- `docs/01_IDEA_PRESSURE_TEST.md` exists and explains why the project is worth building and why scope must be narrowed.
- `docs/02_PRD.md` exists and defines phase-one product requirements.
- `docs/03_ARCHITECTURE.md` exists and uses React + TypeScript and FastAPI + Python as the main architecture direction.
- `docs/04_API_CONTRACT.md` exists and defines first-phase API drafts.
- `docs/05_DEV_RULES.md` exists and defines development guardrails.
- `docs/06_TECH_STACK_CANDIDATES.md` exists and keeps non-confirmed technology choices as candidates.
- `docs/07_ACCEPTANCE_CRITERIA.md` exists and defines milestone acceptance.
- No business feature code is implemented.
- No dependencies are installed.
- No RAG implementation is started.

## M1 Project Initialization

Goal:

- Initialize a minimal project structure without implementing business workflows.

Acceptance criteria:

- React + TypeScript frontend scaffold exists.
- FastAPI + Python backend scaffold exists.
- Basic project commands are documented.
- Environment variable example file exists without real secrets.
- Git ignore rules prevent committing secrets, caches, and local data.
- Basic health check endpoint may exist if needed for setup verification.
- No data import, extraction, RAG, Bad Case, or CustomerOpsAgent business logic is implemented yet.

## M2 Data Import

Goal:

- Import customer service chat records into DataHub.

Acceptance criteria:

- CSV, JSON, or manual input is supported according to the selected MVP order.
- Import batch metadata is stored.
- Raw records are stored in the raw data layer.
- Invalid input returns safe structured errors.
- Duplicate import detection or warning exists at a basic level.
- Raw data is not exposed to CustomerOpsAgent APIs.
- Tests or manual verification cover successful import and invalid input.

## M3 Cleaning And Desensitization

Goal:

- Convert raw records into cleaned and sanitized records.

Acceptance criteria:

- Empty or invalid records are filtered or marked.
- Exact duplicates are detected.
- Sensitive information is masked for supported patterns.
- Sanitized records are stored separately from raw records.
- Cleaning job status can be checked.
- Extraction cannot start unless data is sanitized.
- Logs and errors do not expose raw private data.

## M4 Knowledge Extraction

Goal:

- Generate reviewable knowledge drafts from sanitized records.

Acceptance criteria:

- Extraction only reads sanitized records.
- Drafts can be created for:
  - FAQ
  - Standard answer
  - Business rule
  - Human-handoff rule
  - Forbidden-answer rule
- Each draft includes source references.
- Drafts are created in `review_pending` or equivalent state.
- Drafts are not searchable by CustomerOpsAgent.
- Mock mode or controlled LLM mode is available before real uncontrolled LLM usage.

## M5 Human Review

Goal:

- Allow humans to control which knowledge becomes approved.

Acceptance criteria:

- Reviewers can list pending drafts.
- Reviewers can edit draft content.
- Reviewers can approve drafts.
- Reviewers can reject drafts.
- Reviewers can mark drafts as needing revision.
- Manual knowledge supplements can be created as drafts.
- Approved knowledge includes reviewer, timestamp, version, and source references.
- Rejected and pending knowledge cannot enter RAG.

## M6 RAG Build

Goal:

- Build a retrievable index from approved knowledge only.

Acceptance criteria:

- Indexing job accepts approved knowledge only.
- Pending, rejected, raw, cleaned, or sanitized-only records are rejected by indexing.
- Indexed entries preserve knowledge id, type, version, tags, and source metadata.
- Retrieval returns only indexed approved knowledge.
- Retrieval results include traceable source information.
- Indexing failures are visible and safe.

## M7 CustomerOpsAgent Integration

Goal:

- Allow CustomerOpsAgent to retrieve approved knowledge through DataHub APIs.

Acceptance criteria:

- CustomerOpsAgent retrieval API exists.
- Request validation is enforced.
- Query length limit is enforced.
- API returns topK approved indexed knowledge results.
- API returns retrieval id for later Bad Case linkage.
- API never returns raw records, unapproved drafts, rejected knowledge, or archived knowledge.
- CustomerOpsAgent has no direct database access.

## M8 Bad Case Feedback

Goal:

- Close the improvement loop from CustomerOpsAgent back to DataHub.

Acceptance criteria:

- CustomerOpsAgent can submit Bad Cases.
- Bad Cases store user query, agent answer, issue type, expected answer if available, retrieval id if available, and metadata.
- Bad Cases enter an open or pending state.
- Human reviewers can resolve Bad Cases.
- Resolution can create a new knowledge draft or update an existing knowledge draft.
- Bad Case fixes must pass human review before indexing.
- Bad Cases cannot directly update approved knowledge or the RAG index.

## M9 Phase-One Release Freeze

Goal:

- Stabilize the phase-one text knowledge loop.

Acceptance criteria:

- Full flow works end to end:

```text
import
-> clean and desensitize
-> extract drafts
-> human review
-> index approved knowledge
-> CustomerOpsAgent retrieval
-> Bad Case feedback
-> human correction
-> review and re-index
```

- Security rules are verified.
- Raw and unapproved data cannot be retrieved.
- Source traceability exists for approved knowledge.
- Documentation reflects the implemented behavior.
- Known limitations are recorded.
- Git tag or release marker is created if the repository is initialized.
- Future extensions are documented but not implemented:
  - Multimodal.
  - MCP.
  - Fine-tuning export.
  - Sales Agent.
  - Operations Agent.

## Future Phase Acceptance Outline

These outlines describe the long-term product roadmap. They are not permission to start implementation before Phase 1 is accepted.

### Phase 2 Multimodal Material Integration

Goal:

- Extend DataHub from text customer service knowledge into AI Material Center and multimodal asset governance.

Acceptance outline:

- AI Material Center assets can be imported as governed data sources.
- Image, poster, and later video assets have metadata records.
- OCR, Caption, tags, and SKU binding can be generated or edited.
- Human reviewers can approve or reject material understanding results.
- Approved multimodal assets can enter a multimodal knowledge store.
- Multimodal retrieval results preserve asset source, review, and SKU traceability.
- CustomerOpsAgent can later use approved multimodal knowledge for image-text customer service.
- Raw or unreviewed assets cannot be retrieved by Agent consumers.

### Phase 3 Sales Training And Fine-Tuning Dataset Export

Goal:

- Export reviewed high-quality knowledge into human training materials and model improvement datasets.

Acceptance outline:

- Approved FAQ, SOP, scripts, typical cases, excellent replies, and Bad Case fixes can be selected for export.
- Sales onboarding outputs can include FAQ handbooks, SOP, script handbooks, typical cases, and quiz questions.
- Fine-tuning exports can produce SFT and Preference-style datasets.
- Exported records preserve source and review traceability.
- Private data remains desensitized before export.
- Exported datasets are clearly labeled as generated artifacts, not production model training runs.

### Phase 4 MCP And Agent Cluster Integration

Goal:

- Package DataHub capabilities as stable tools for multiple Agents.

Acceptance outline:

- MCP Tools expose governed capabilities such as:
  - `search_customer_knowledge`
  - `search_multimodal_assets`
  - `submit_bad_case`
  - `export_training_dataset`
  - `export_finetune_dataset`
- CustomerOpsAgent, SalesAgent, OpsAgent, and MaterialAgent can call the appropriate tools.
- Tool permissions prevent Agents from bypassing review.
- Tool responses return only approved, indexed, and authorized data.
- Bad Case submission enters a governed review workflow.
- Tool contracts are documented and versioned.
