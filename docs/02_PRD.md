# DataHub PRD

## 1. Background

CustomerOpsAgent needs reliable business knowledge to answer customer questions. Raw customer service chat records contain valuable information, but they are noisy, duplicated, private, and not directly safe for RAG retrieval.

DataHub solves this by creating a controlled knowledge production workflow:

```text
Phase 1 target flow:
raw text data
-> sanitized data
-> knowledge candidates
-> reviewed candidates
-> local RAG chunks / future production index
-> CustomerOpsAgent retrieval
-> Bad Case feedback
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

## 2B. Implementation Status Note

This PRD describes the Phase 1 target scope, not only the currently completed implementation.

### Phase 1 Target Scope

- Import customer service chat records.
- Clean, deduplicate, and desensitize records.
- Extract knowledge candidates.
- Support human review.
- Build RAG from approved knowledge.
- Provide CustomerOpsAgent retrieval.
- Receive Bad Cases and feed corrections back into the knowledge workflow.

### Currently Implemented Through P1-M12

- JSON customer service chat import.
- Local raw batch storage.
- Basic cleaning and PII masking.
- Sanitized batch generation.
- Rule-based mock knowledge candidate extraction.
- Human review for knowledge candidates.
- Local RAG chunk generation from approved candidates only.
- Local JSON plus keyword/mock RAG search for DataHub internal testing.
- Idempotent RAG build without duplicate chunks.
- RAG search query and top_k validation.
- `matched_terms` and source trace returned for local search debugging.
- CustomerOpsAgent restricted retrieval API over approved local `rag_chunked` results.
- Retrieval trace records for Bad Case linkage.
- CustomerOpsAgent Bad Case submission with `retrieval_id` validation.
- Bad Case queue listing, detail lookup, and manual status / review note updates.
- Human-triggered Bad Case conversion into new `pending_review` knowledge candidates.
- Bad Case source trace on generated candidates.
- P1 core-loop release freeze verification.
- Public dataset small-sample evaluation.
- CustomerOpsAgent legacy RAG export import.
- Legacy RAG items standardized into DataHub knowledge candidates.
- Trusted legacy import to approved candidates.
- Review-required legacy import to pending-review candidates.
- Legacy source trace through candidates, local RAG chunks, and CustomerOpsAgent retrieval results.
- Unified DataHub RAG release across approved `chat_logs`, `public_dataset`, `bad_case`, and `legacy_rag` sources.
- CustomerOpsAgent DataHub-only integration guide and locked retrieval contract.
- Chinese and English P1-M11 release README files.
- P1-M12 advanced machine cleaning and data quality scoring.
- Message-level `cleaning_issues`, `risk_flags`, `quality_score`, `quality_level`, and `suggested_action`.
- Enhanced duplicate, near-duplicate, low-quality, noise, and PII risk detection.
- Extraction skips sanitized messages marked `suggested_action: drop`.

### Pending In Phase 1

- CSV import.
- Manual text paste import.
- Manual cleaning workbench for reviewing and correcting sanitized data.
- Chinese knowledge review quality console and reviewer rules.
- Separate approved knowledge or knowledge asset version management.
- Approval of Bad Case-generated drafts through the normal M5 review workflow.
- RAG rebuild after approved Bad Case-generated drafts.
- Production retrieval/indexing beyond local mock RAG chunks.

### Phase 1 High-Quality DataHub Extension: P1-M12 To P1-M15

P1-M11 is the unified DataHub RAG release, not the final high-quality DataHub release.
The Phase 1 final high-quality data platform release is now planned as P1-M15.

- P1-M12: Advanced Machine Cleaning & Data Quality Scoring.
  - Enhance machine cleaning.
  - Add data quality scores.
  - Mark duplicates, low-quality content, possible noise, and privacy risk.
  - Provide issue tags and suggested actions for the later manual cleaning workbench.
- P1-M13: Chinese Admin Console & Manual Cleaning Workbench.
  - Make the frontend Chinese-first.
  - Add a Chinese dashboard and reserved P1/P2/P3/P4 module cards.
  - Support raw versus sanitized comparison, manual sanitized content correction, keep/drop/review decisions, and cleaning notes.
  - Add a cleaner operation guide.
- P1-M14: Knowledge Review Quality Console.
  - Improve the Chinese review workbench.
  - Support candidate editing, approve, reject, and needs_revision operations with clearer rules.
  - Show source trace, quality_score, and risk_flags.
  - Add reviewer rules for FAQ, standard answers, business rules, human handoff rules, and forbidden answer rules.
- P1-M15: High-quality DataHub P1 Final Release.
  - Validate the full high-quality loop:
    machine cleaning -> manual cleaning -> extraction -> human review -> unified RAG -> CustomerOpsAgent retrieval -> Bad Case feedback.
  - Publish the final P1 high-quality DataHub acceptance report.
  - Prepare the boundary for Phase 2 multimodal material ingestion.

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

In the full Phase 1 target, only approved knowledge can become retrieval-ready. Current M6/M6.5 builds local RAG chunks with mock retrieval; future production retrieval may add a real indexed state.

### 4.6 Serve CustomerOpsAgent

CustomerOpsAgent queries DataHub through retrieval APIs and receives approved knowledge snippets with source information.

### 4.7 Handle Bad Cases

CustomerOpsAgent submits Bad Cases with a `retrieval_id`. DataHub stores them for human handling. Current M8.5 allows a human to convert a Bad Case into a new `pending_review` candidate. The generated draft still requires M5 review and does not enter RAG automatically.

### 4.8 Migrate Legacy RAG Knowledge

CustomerOpsAgent legacy RAG knowledge can be exported into a standard JSON shape and imported by DataHub. DataHub converts legacy items into normal knowledge candidates with `source_type: legacy_rag`.

Current P1-M10 behavior:

- `trusted_import=true` creates `approved` candidates for already-live legacy RAG knowledge.
- `trusted_import=false` creates `pending_review` candidates for uncertain legacy knowledge.
- Both modes preserve `source_legacy_id`, `source_import_id`, `migration_mode`, and source notes.
- Only approved legacy candidates can enter local RAG chunks.
- P1-M10 does not modify CustomerOpsAgent or switch it to DataHub-only retrieval.

### 4.9 Unified DataHub RAG Release

P1-M11 confirms that DataHub can unify approved knowledge from multiple governed sources into one local RAG and CustomerOpsAgent retrieval shape.

Current P1-M11 source coverage:

- `chat_logs`
- `public_dataset`
- `bad_case`
- `legacy_rag`

CustomerOpsAgent's recommended P1-M11 integration mode is DataHub-only retrieval through:

```text
POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
```

The CustomerOpsAgent repository is not modified in this DataHub milestone.

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

Canonical state names:

```text
raw_imported
-> sanitized
-> pending_review
   -> approved -> rag_chunked -> indexed
   -> needs_revision -> pending_review / approved / rejected
   -> rejected
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

State naming rules:

- `pending_review` is the canonical candidate review state. Do not use `review_pending`.
- `approved` means a human approved the candidate. It does not mean the item has entered RAG.
- `rag_chunked` means a local RAG chunk has been generated from an approved candidate.
- `indexed` is reserved for future real vector store or production retrieval index status.
- Current M6/M6.5 reaches `rag_chunked`, not production `indexed`.
- `knowledge candidate` is the M4-M5 term.
- `approved candidate` is the M5 post-review term.
- If DataHub later introduces a formal `knowledge_item` or knowledge asset store, it must be planned separately and not mixed with candidate records.

Hard rules:

- Only sanitized records can be used for extraction.
- Only approved candidates or future approved knowledge items can be chunked or indexed.
- Only approved retrieval-ready knowledge can be retrieved by CustomerOpsAgent. At the current local stage, retrieval-ready may mean `rag_chunked`; future production retrieval may require `indexed`.
- Raw records must remain isolated from RAG and export flows.

## 8. Acceptance Summary

Phase one is acceptable when:

- Customer service chat records can be imported.
- Records can be cleaned, deduplicated, and desensitized.
- Knowledge drafts can be extracted from sanitized records.
- Humans can approve, edit, reject, and supplement knowledge.
- Only approved knowledge enters local RAG chunks or future production indexes.
- CustomerOpsAgent can retrieve approved knowledge by API.
- CustomerOpsAgent can submit Bad Cases.
- Bad Cases can be corrected and re-enter the knowledge workflow.
- Every approved knowledge item has traceable source records.
- Un-desensitized and unreviewed data cannot be retrieved or exported.

## 9. P1-M13 Product Update: Chinese Admin Console And Manual Cleaning

P1-M13 adds a Chinese DataHub admin console and a manual cleaning workbench.

Implemented behavior:

- The frontend is organized as a Chinese management console.
- P1 text customer service modules are visible as operational capabilities.
- P2 multimodal, P3 dataset reuse, and P4 MCP / Agent cluster modules are visible only as Roadmap / not connected entries.
- Cleaners can load a sanitized batch and inspect machine cleaning fields:
  - `pii_detected`
  - `pii_types`
  - `cleaning_issues`
  - `risk_flags`
  - `quality_score`
  - `quality_level`
  - `suggested_action`
- Cleaners can save manual cleaning decisions:
  - `keep`
  - `keep_edited`
  - `drop`
  - `needs_review`

Manual cleaning remains a Phase 1 text-data capability. It does not implement Phase 2 multimodal, Phase 3 dataset export, or Phase 4 MCP.

## 10. P1-M14 Product Update: Knowledge Review Quality Console

P1-M14 adds a Chinese knowledge review workbench for pending-review knowledge candidates.

Implemented behavior:

- Reviewers can load knowledge candidates.
- Reviewers can filter candidates locally by:
  - `review_status`
  - `source_type`
  - quality level derived from `quality_score`
  - `intent`
  - keyword
- Reviewers can inspect:
  - source trace
  - `quality_score`
  - `risk_level`
  - `cleaning_issues`
  - `risk_flags`
- Reviewers can edit:
  - `question`
  - `answer`
  - `intent`
  - `tags`
  - `risk_level`
  - `quality_score`
- Reviewers can approve, reject, or mark candidates as `needs_revision`.

Hard rule:

- Only `approved` candidates can enter local RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates cannot enter RAG.
- P1-M14 does not implement Phase 2, Phase 3, Phase 4, real vector search, embeddings, database, ORM, real LLM, or MCP.
