# DataHub Architecture

## 1. Architecture Goal

DataHub phase one uses a lightweight web application architecture:

- Frontend: React + TypeScript management backend.
- Backend: FastAPI + Python API service.
- Database, vector database, ORM, RAG framework, task queue, and deployment platform remain candidates until further evaluation.

The architecture must support the CustomerOpsAgent text knowledge loop without becoming an enterprise data platform.

The long-term architecture should also support DataHub's final positioning:

```text
DataHub | Multi-source data governance and RAG knowledge platform for Agent clusters
```

## 2. High-Level Flow

```text
React Admin UI
    |
    v
FastAPI API Service
    |
    +--> Import Module
    +--> Cleaning & Desensitization Module
    +--> Knowledge Extraction Module
    +--> Human Review Module
    +--> RAG Build Module
    +--> CustomerOpsAgent Interface Module
    +--> Bad Case Feedback Module
    +--> Legacy RAG Migration Module
    |
    v
Candidate Data Layer
    |
    +--> Relational database candidate
    +--> Vector store candidate
    +--> File or object storage candidate if needed later
```

## 2A. Target Architecture

Final target structure:

```text
Data Sources
  - Customer chat logs
  - Product docs
  - Bad cases
  - AI Material Center assets
  - Human corrections

DataHub Core
  - Ingestion
  - Cleaning & Sanitization
  - Knowledge Extraction
  - Material Understanding
  - Human Review
  - Knowledge Asset Store
  - RAG Builder
  - Dataset Export
  - MCP Tool Layer

Consumers
  - CustomerOpsAgent
  - SalesAgent
  - OpsAgent
  - MaterialAgent
  - Fine-tuning pipeline
```

Current implemented Phase 1 path:

```text
Customer chat logs
-> Ingestion
-> Cleaning & Sanitization
-> Knowledge Extraction
-> Human Review
-> Local RAG Builder
-> CustomerOpsAgent Restricted Retrieval
-> Bad Case Queue
-> Bad Case To Draft
-> P1 Core Loop Release Verification
CustomerOpsAgent legacy RAG export
-> Legacy RAG Migration
-> Knowledge Candidates
-> Local RAG Builder
-> CustomerOpsAgent Restricted Retrieval Test
Governed sources
  - chat_logs
  - public_dataset
  - approved bad_case drafts
  - trusted legacy_rag imports
-> Unified Local RAG Chunks
-> CustomerOpsAgent Restricted Retrieval
```

Current Phase 1 modules already started or implemented locally:

- Ingestion.
- Cleaning & Sanitization.
- Knowledge Extraction.
- Human Review.
- Local RAG Builder.
- CustomerOpsAgent Restricted Retrieval.
- Bad Case Queue.
- Bad Case To Draft.
- P1 Core Loop Release Verification.
- P1-M9.5 Public Dataset Evaluation.
- P1-M10 Legacy RAG Migration.
- P1-M11 Unified DataHub RAG Release.
- P1-M12 Advanced Machine Cleaning & Data Quality Scoring.

Planned Phase 1 high-quality data platform extensions:

- P1-M13 Chinese Admin Console & Manual Cleaning Workbench.
- P1-M14 Knowledge Review Quality Console.
- P1-M15 High-quality DataHub P1 Final Release.

P1-M11 is the unified local RAG release. It is not the final high-quality DataHub release.
P1-M15 is the planned final Phase 1 high-quality data platform checkpoint.

P1-M12 adds a quality layer inside the Cleaning & Sanitization Module:

```text
raw messages
-> deterministic machine cleaning
-> PII masking
-> duplicate / near-duplicate detection
-> low-quality and noise flags
-> quality_score / quality_level / suggested_action
-> sanitized messages for extraction and later manual cleaning
```

Future modules not implemented yet:

- CustomerOpsAgent production vector retrieval beyond the M7 local restricted retrieval API.
- Bad Case-generated draft approval and RAG rebuild beyond M8.5.
- Material Understanding.
- Knowledge Asset Store beyond local files.
- Dataset Export.
- MCP Tool Layer.
- SalesAgent, OpsAgent, and MaterialAgent integrations.

Phase 2 AI Material Center position:

```text
AI Material Center assets
-> Ingestion
-> Material Understanding
-> Human Review
-> Knowledge Asset Store
-> Multimodal RAG Builder
```

Phase 3 dataset export position:

```text
Approved knowledge / reviewed Bad Case fixes / high-quality Q&A
-> Dataset Export
-> sales training materials
-> SFT dataset
-> Preference dataset
```

Phase 4 MCP tool layer position:

```text
Knowledge Asset Store + RAG Builder + Dataset Export
-> MCP Tool Layer
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent
```

These target modules are architecture reservations and roadmap commitments. They are not current implementation scope until their phase is explicitly started.

## 3. Frontend: React Management Backend

The frontend is a single-page management backend built with React + TypeScript.

Responsibilities:

- Import data through forms and upload controls.
- Show import batches and processing status.
- Show cleaning, deduplication, and desensitization results.
- Show extracted knowledge drafts.
- Support human review, editing, approval, rejection, and supplementation.
- Show approved knowledge and index status.
- Show Bad Case queue and manual handling status.
- Provide loading, empty, error, and success states for core operations.

Non-goals:

- No Next.js App Router.
- No SSR requirement.
- No marketing landing page.
- No complex BI dashboard in phase one.

## 4. Backend: FastAPI API Service

The backend is a FastAPI + Python API service.

Responsibilities:

- Expose stable APIs to the React frontend.
- Expose restricted retrieval and feedback APIs to CustomerOpsAgent.
- Validate all request payloads.
- Enforce data state transitions.
- Enforce safety rules:
  - Raw data cannot enter extraction, RAG, or export flows.
  - Unapproved knowledge cannot enter retrieval.
- Coordinate service modules.
- Store processing metadata and traceability links.
- Hide secrets and sensitive errors.

## 5. Candidate Data Layer

The final data storage choice is not fixed yet.

Candidate responsibilities:

- Store raw import batches.
- Store sanitized records separately from raw records.
- Store knowledge drafts and approved knowledge.
- Store review records and version history.
- Store Bad Cases and resolution records.
- Store RAG index metadata.

Candidate technologies are documented in `06_TECH_STACK_CANDIDATES.md`.

## 6. Module Responsibilities

### 6.1 Data Import Module

Responsibilities:

- Accept CSV, JSON, and manual text input.
- Create import batches.
- Normalize initial record structures.
- Store raw records in the raw data layer.
- Record source metadata.

Must not:

- Send raw records directly to RAG.
- Expose raw records to CustomerOpsAgent.

### 6.2 Cleaning & Desensitization Module

Responsibilities:

- Remove empty or invalid records.
- Normalize text format.
- Detect duplicates.
- Mask sensitive information.
- Produce sanitized records.
- Record cleaning and desensitization status.

Must enforce:

- Extraction can only use sanitized records.
- Raw and sanitized data must remain separated.

### 6.3 Knowledge Extraction Module

Responsibilities:

- Read sanitized records.
- Generate knowledge drafts.
- Classify drafts into supported types:
  - FAQ
  - Standard answer
  - Business rule
  - Human-handoff rule
  - Forbidden-answer rule
- Attach source references.
- Mark candidates as `pending_review`.

Candidate implementation:

- Start with a lightweight service interface.
- LLM provider and orchestration framework remain replaceable.

### 6.4 Human Review Module

Responsibilities:

- List pending knowledge drafts.
- Allow human edit, supplement, approve, or reject.
- Create version and review records.
- Move approved records into the eligible-for-indexing state.

Must enforce:

- No unreviewed knowledge can be indexed.
- Review metadata must be preserved.

### 6.5 RAG Build Module

Responsibilities:

- Read approved knowledge only.
- Chunk or format approved knowledge for indexing.
- Generate or update retrieval index entries.
- Store index status and errors.

Candidate implementation:

- Vector store and embedding provider remain candidates.
- Index rebuild strategy remains a design decision for later implementation.

### 6.6 CustomerOpsAgent Interface Module

Responsibilities:

- Provide retrieval APIs for CustomerOpsAgent.
- Return only approved retrieval-ready knowledge.
- In M7/M8, retrieval-ready means approved local `rag_chunked` records from `backend/storage/rag_chunks/`.
- Include source trace, retrieval id, and knowledge type metadata.
- Apply request validation and access boundaries.
- In M7.5, require `X-DataHub-Client: CustomerOpsAgent` as a local development auth placeholder.
- M7.5 auth placeholder is not a production token, API key, or `.env` secret.
- In M8, the same auth placeholder is reused for CustomerOpsAgent Bad Case submission.

Must enforce:

- CustomerOpsAgent cannot access raw records.
- CustomerOpsAgent cannot mutate approved knowledge directly.
- CustomerOpsAgent cannot bypass DataHub review.
- CustomerOpsAgent cannot read raw batches, sanitized batches, or knowledge candidates directly.

### 6.7 Bad Case Feedback Module

Responsibilities:

- Receive Bad Cases from CustomerOpsAgent.
- Store the original query, agent answer, issue type, and expected correction if available.
- Link Bad Cases to retrieval traces when available.
- Allow humans to triage the Bad Case and record handling notes.
- M8 stores Bad Cases under `backend/storage/bad_cases/`.
- M8.5 lets humans convert a Bad Case into a new `pending_review` candidate under `backend/storage/knowledge_candidates/`.
- Later review stages may approve those drafts through the normal M5 workflow.

Must enforce:

- Bad Cases cannot directly update the RAG index.
- Bad Cases cannot directly update candidates or RAG chunks.
- M8.5 must create new drafts only; it must not directly update existing candidates.
- M8.5 must not automatically rebuild or re-index RAG.
- Bad Case fixes require review before indexing.

### 6.8 Legacy RAG Migration Module

Responsibilities:

- Accept CustomerOpsAgent legacy RAG exports in a stable JSON format.
- Convert legacy question-answer items into DataHub knowledge candidates.
- Preserve legacy source trace:
  - `source_type: legacy_rag`
  - `source_legacy_id`
  - `source_import_id`
  - `migration_mode`
  - `source_note`
- Support trusted migration for already-live legacy RAG knowledge.
- Support review-required migration for uncertain legacy knowledge.
- Prevent duplicate candidates for the same `source_name + legacy_id`.
- Save import metadata under `backend/storage/legacy_rag_imports/`.

Must enforce:

- CustomerOpsAgent repository is not read or modified.
- Trusted imports may create `approved` candidates, but they remain traceable as legacy migrations.
- Review-required imports must create only `pending_review` candidates.
- Legacy imports do not directly create RAG chunks; existing RAG build rules still apply.
- P1-M10 does not switch CustomerOpsAgent to DataHub-only retrieval.

### 6.9 Unified DataHub RAG Release Module

Responsibilities:

- Treat approved candidates from `chat_logs`, `public_dataset`, `bad_case`, and `legacy_rag` as one governed retrieval-ready source after local RAG build.
- Preserve source trace in candidates, chunks, and CustomerOpsAgent retrieval results.
- Keep CustomerOpsAgent retrieval read-only and restricted to `backend/storage/rag_chunks/`.
- Document the DataHub-only CustomerOpsAgent integration path.

Must enforce:

- CustomerOpsAgent repository is not modified by DataHub P1-M11.
- Pending, needs-revision, and rejected candidates remain outside RAG.
- Bad Case drafts require normal approval before entering RAG.
- P1-M11 does not introduce a vector database, embedding model, database, ORM, real LLM, MCP, or P2/P3/P4 implementation.

## 7. Data State Boundaries

Logical layers:

```text
raw data layer
sanitized data layer
knowledge draft layer
approved knowledge layer
rag index layer
bad case layer
```

Hard boundaries:

- Raw data layer is internal only.
- Sanitized data can be used for extraction.
- Draft knowledge can be reviewed but not retrieved by CustomerOpsAgent.
- Approved knowledge can be indexed.
- Indexed approved knowledge can be retrieved.

## 8. Extension Points

### 8.1 Multimodal Extension

Future modules may include:

- Image import.
- OCR.
- Caption generation.
- Tagging.
- SKU binding.
- Image review.
- Multimodal retrieval.

Phase one only reserves the module boundary. It does not implement these features.

### 8.2 Fine-Tuning Dataset Extension

Future exports may create supervised fine-tuning datasets from approved knowledge and reviewed Bad Cases.

Phase one does not implement real fine-tuning or fine-tuning export.

### 8.3 MCP Extension

Future versions may package DataHub retrieval and data operations as MCP tools for an agent cluster.

Phase one does not implement MCP.

### 8.4 Additional Agent Consumers

Future consumers may include:

- Sales Agent.
- Operations Agent.
- Multimodal CustomerOpsAgent.

Phase one only supports CustomerOpsAgent.

## 9. Architecture Constraints

- Keep module boundaries clear.
- Keep API contracts stable once implementation begins.
- Do not place business logic in React components.
- Do not place business logic directly in route handlers.
- Do not allow CustomerOpsAgent to access the database directly.
- Do not implement future extension modules before phase-one acceptance.
- Do not introduce big data infrastructure in phase one.
