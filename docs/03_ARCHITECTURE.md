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
```

Current Phase 1 modules already started or implemented locally:

- Ingestion.
- Cleaning & Sanitization.
- Knowledge Extraction.
- Human Review.
- Local RAG Builder.

Future modules not implemented yet:

- CustomerOpsAgent production retrieval interface.
- Bad Case feedback.
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
- Show Bad Case queue and correction workflow.
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
- Return only approved and indexed knowledge.
- Include source, version, and knowledge type metadata.
- Apply request validation and access boundaries.

Must enforce:

- CustomerOpsAgent cannot access raw records.
- CustomerOpsAgent cannot mutate approved knowledge directly.
- CustomerOpsAgent cannot bypass DataHub review.

### 6.7 Bad Case Feedback Module

Responsibilities:

- Receive Bad Cases from CustomerOpsAgent.
- Store the original query, agent answer, issue type, and expected correction if available.
- Link Bad Cases to retrieval traces when available.
- Allow human correction.
- Send corrected content back into the normal knowledge workflow.

Must enforce:

- Bad Cases cannot directly update the RAG index.
- Bad Case fixes require review before indexing.

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
