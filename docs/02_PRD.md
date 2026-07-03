# DataHub PRD

## 1. Background

CustomerOpsAgent needs reliable business knowledge to answer customer questions. Raw customer service chat records contain valuable information, but they are noisy, duplicated, private, and not directly safe for RAG retrieval.

DataHub solves this by creating a controlled knowledge production workflow:

```text
raw text data -> sanitized data -> knowledge drafts -> reviewed knowledge -> RAG index -> CustomerOpsAgent retrieval -> Bad Case feedback
```

## 2. Product Positioning

DataHub is a lightweight data asset center for AI application projects.

Long-term positioning:

```text
DataHub | Multi-source data governance and RAG knowledge platform for Agent clusters
```

In phase one, DataHub is a text knowledge governance system for CustomerOpsAgent. It is responsible for data import, cleaning, desensitization, knowledge extraction, human review, RAG indexing, retrieval, and Bad Case feedback handling.

## 2A. Long-Term Product Vision

DataHub is not intended to remain only a customer service text RAG tool. Its final product direction is a governed data and knowledge center for multiple AI Agents.

Long-term flow:

```text
Multi-source business data
-> cleaning / desensitization / standardization
-> knowledge extraction / material understanding / human review
-> text + multimodal RAG knowledge base
-> data service APIs / MCP Tools
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent and other Agent consumers
```

Formal product phases:

- Phase 1: Text Customer Service Knowledge Loop.
- Phase 2: AI Material Center and Multimodal Knowledge.
- Phase 3: High-quality Dataset Export.
- Phase 4: MCP Tools and Agent Cluster Integration.

Current implementation scope:

- This PRD's buildable scope remains Phase 1 only.
- Phase 2, Phase 3, and Phase 4 are product roadmap phases.
- Roadmap phases should guide architecture boundaries but must not be implemented before the Phase 1 loop is accepted.

### Phase 1: Text Customer Service Knowledge Loop

```text
Real customer service chat records
-> cleaning / deduplication / desensitization
-> FAQ / standard answers / business rules / human-handoff rules / forbidden-answer rules
-> human review
-> text RAG knowledge base
-> CustomerOpsAgent text customer service
-> Bad Case feedback
```

### Phase 2: AI Material Center And Multimodal Knowledge

```text
Ops Agent / AI Material Center generated images, videos, and poster assets
-> material ingestion
-> OCR / Caption / tags / SKU binding
-> human review
-> multimodal knowledge base
-> CustomerOpsAgent image-text / multimodal customer service
```

### Phase 3: High-Quality Dataset Export

```text
Reviewed customer service knowledge, excellent human replies, Bad Case fixes, high-quality Q&A
-> sales onboarding materials
-> FAQ handbook / SOP / script handbook / typical cases / quiz questions
-> SFT dataset / Preference dataset
-> reduce AI flavor and improve brand voice, service style, and refusal rules
```

### Phase 4: MCP Tools And Agent Cluster Integration

```text
DataHub MCP Tools
-> search_customer_knowledge
-> search_multimodal_assets
-> submit_bad_case
-> export_training_dataset
-> export_finetune_dataset
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent unified access
```

## 3. Target Users

Primary users:

- Data maintainer: imports chat records, checks cleaning results, manages knowledge.
- Knowledge reviewer: reviews, edits, approves, rejects, and supplements knowledge.
- CustomerOpsAgent: retrieves approved knowledge and submits Bad Cases through APIs.

Non-phase-one users:

- Sales Agent.
- Operations Agent.
- MaterialAgent.
- Multimodal content operators.
- MCP consumers.

## 4. Core Scenarios

### 4.1 Import Chat Records

A data maintainer imports real customer service chat records into DataHub. The system stores the import batch and raw records.

### 4.2 Clean And Desensitize Data

The system cleans invalid content, detects duplicates, and desensitizes sensitive information. Only sanitized records can move into knowledge extraction.

### 4.3 Extract Knowledge Drafts

The system extracts draft knowledge from sanitized records:

- FAQ
- Standard answers
- Business rules
- Human-handoff rules
- Forbidden-answer rules

### 4.4 Review Knowledge

A human reviewer checks knowledge drafts, edits them, rejects invalid ones, or approves valid ones.

### 4.5 Build RAG Knowledge

Only approved knowledge is indexed into the RAG knowledge base.

### 4.6 Serve CustomerOpsAgent

CustomerOpsAgent queries DataHub through retrieval APIs and receives approved knowledge snippets with source information.

### 4.7 Handle Bad Cases

CustomerOpsAgent submits Bad Cases. DataHub stores them for human correction. Corrected Bad Cases can become new or updated knowledge after review.

## 5. Phase-One Functional Requirements

### 5.1 Data Import

- Support importing customer service chat records.
- Initial supported input types:
  - CSV
  - JSON
  - Manual text paste
- Store import batch metadata.
- Store source identity for traceability.
- Reject unsupported or malformed inputs with clear errors.

### 5.2 Cleaning And Deduplication

- Remove empty records.
- Normalize basic text format.
- Detect exact duplicates.
- Mark near-duplicates for later review or merge.
- Preserve source linkage after cleaning.

### 5.3 Desensitization

- Detect and mask common sensitive information:
  - Phone numbers
  - Emails
  - Names when detectable
  - Addresses when detectable
  - Order numbers or business identifiers when configured
- Keep raw and sanitized data in separate layers.
- Prevent raw data from entering extraction, RAG, or export flows.

### 5.4 Knowledge Extraction

- Generate knowledge drafts from sanitized records.
- Assign one of the supported knowledge types.
- Attach source records to each draft.
- Mark generated drafts as pending review.

### 5.5 Human Review

- Reviewers can edit draft title, question, answer, tags, and source notes.
- Reviewers can approve knowledge.
- Reviewers can reject knowledge.
- Reviewers can supplement missing knowledge manually.
- Approved knowledge receives version metadata.

### 5.6 RAG Knowledge Base

- Only approved knowledge can be indexed.
- The index must preserve knowledge id, version, type, tags, and source references.
- Rejected, pending, raw, or sanitized-only records must not be retrieved.

### 5.7 CustomerOpsAgent Retrieval

- CustomerOpsAgent can query DataHub through an API.
- DataHub returns top matching approved knowledge.
- Responses include source and version metadata.

### 5.8 Bad Case Feedback

- CustomerOpsAgent can submit Bad Cases.
- Bad Cases include the original user query, agent answer, issue type, expected correction if available, and context references.
- Bad Cases enter a human processing queue.
- Bad Case fixes must pass the normal review flow before entering RAG.

## 6. Non-Functional Requirements

### 6.1 Security

- API keys must only exist in backend environment variables.
- Private data must not be logged.
- Raw data must not be retrievable through CustomerOpsAgent APIs.
- User input must be length-limited and validated.
- Error messages must not expose private data or secrets.

### 6.2 Performance

- Basic management operations should respond quickly for small and medium local datasets.
- Long-running cleaning, extraction, or indexing jobs should be trackable.
- Repeated processing should be avoided when records have not changed.

### 6.3 Cost

- LLM calls must be controllable.
- Mock mode should be supported in development.
- Batch processing should be preferred over per-row uncontrolled calls.

### 6.4 Usability

- Key flows should expose loading, empty, success, and error states.
- Reviewers should see source context before approving knowledge.
- The product should behave as a focused management backend, not a marketing website.

## 7. Data State Flow

Core state flow:

```text
raw_imported
-> cleaned
-> sanitized
-> extraction_pending
-> draft_extracted
-> review_pending
-> approved
-> indexed
```

Alternative states:

```text
rejected
needs_revision
duplicate
failed_cleaning
failed_desensitization
failed_extraction
failed_indexing
archived
```

Hard rules:

- Only sanitized records can be used for extraction.
- Only approved knowledge can be indexed.
- Only indexed approved knowledge can be retrieved by CustomerOpsAgent.
- Raw records must remain isolated from RAG and export flows.

## 8. Acceptance Summary

Phase one is acceptable when:

- Customer service chat records can be imported.
- Records can be cleaned, deduplicated, and desensitized.
- Knowledge drafts can be extracted from sanitized records.
- Humans can approve, edit, reject, and supplement knowledge.
- Only approved knowledge enters the RAG index.
- CustomerOpsAgent can retrieve approved knowledge by API.
- CustomerOpsAgent can submit Bad Cases.
- Bad Cases can be corrected and re-enter the knowledge workflow.
- Every approved knowledge item has traceable source records.
- Un-desensitized and unreviewed data cannot be retrieved or exported.
