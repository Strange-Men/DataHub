# P1-M15 High-quality DataHub Release Report

## 1. P1 Final Goal

P1-M15 is the final Phase 1 high-quality DataHub release.

The goal is to prove that DataHub is not only a local RAG demo. It is a governed data platform that can clean, review, trace, and reuse customer-service knowledge before it is served to CustomerOpsAgent.

Release tag:

```text
p1-m15-high-quality-datahub-release
```

## 2. Final Complete Loop

The verified P1 loop is:

```text
data import
-> advanced machine cleaning
-> manual cleaning
-> knowledge extraction
-> knowledge review
-> local RAG build
-> CustomerOpsAgent restricted retrieval
-> Bad Case feedback
-> Bad Case to pending-review draft
```

Hard boundaries remain:

- Raw data stays read-only.
- Manual cleaning updates sanitized data only.
- Knowledge extraction creates `pending_review` candidates.
- Only `approved` candidates enter local RAG chunks.
- Bad Case drafts do not automatically enter RAG.

## 3. Machine Cleaning Summary

P1 machine cleaning supports:

- PII masking for email, phone, order id, tracking id, address, name-like text, ZIP/postal code, and payment-sensitive strings.
- Exact duplicate and near-duplicate detection.
- Low-quality text labels such as too short, too long, repeated chars, symbol noise, and possible garbled text.
- Noise labels for possible ads, off-topic chatter, weak questions, and weak answers.
- Message-level `quality_score`, `quality_level`, `suggested_action`, `cleaning_issues`, and `risk_flags`.

The cleaning summary includes duplicate counts, low-quality counts, noise counts, review/drop recommendations, and average quality score.

## 4. Manual Cleaning Summary

The Chinese admin console includes a manual cleaning workbench.

Cleaners can:

- Load sanitized batches by `batch_id`.
- Inspect PII, quality, issue, and risk fields.
- Edit sanitized content.
- Choose `keep`, `keep_edited`, `drop`, or `needs_review`.
- Save cleaner and cleaning note fields.

Manual cleaning records are saved under:

```text
backend/storage/manual_cleaning_records/
```

This directory is ignored by Git.

## 5. Knowledge Review Summary

The Chinese knowledge review console supports:

- Loading knowledge candidates.
- Local filtering by review status, source type, quality level, intent, and keyword.
- Editing question, answer, intent, tags, risk level, and quality score.
- Approve, reject, and needs-revision decisions.
- Reviewer and review note capture.
- Source trace, cleaning issues, and risk flags display.

Review records are saved under:

```text
backend/storage/review_records/
```

Only `approved` candidates can enter local RAG.

## 6. Unified RAG Summary

DataHub builds local RAG chunks from approved candidates only.

Supported governed sources in P1:

- `chat_logs`
- `public_dataset`
- `bad_case`
- `legacy_rag`

RAG build remains idempotent. Repeated builds do not create duplicate chunks for unchanged candidates.

Current retrieval is local keyword/mock retrieval. It does not use a real vector database or embeddings.

## 7. CustomerOpsAgent Access

CustomerOpsAgent uses the restricted retrieval API:

```text
POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
```

Required local development header:

```text
X-DataHub-Client: CustomerOpsAgent
```

The retrieval API reads only from local RAG chunks and returns score, matched terms, chunk id, candidate id, source type, and source trace.

## 8. Bad Case Feedback

CustomerOpsAgent can submit Bad Cases with a `retrieval_id`.

Bad Cases are saved under:

```text
backend/storage/bad_cases/
```

Humans can convert a Bad Case into a new `pending_review` draft. That draft:

- Preserves `source_bad_case_id`.
- Preserves `source_retrieval_id`.
- Preserves linked chunk ids.
- Does not auto-approve.
- Does not auto-build RAG.

## 9. Public Dataset Evaluation Result

P1 public dataset evaluation used a safe converted customer-support sample.

Verified metrics:

- public dataset sample: 50 conversations / 100 messages
- candidate_count: 50
- approved_count: 10
- rag_chunk_count: 10
- retrieval_hit_count: 5
- bad_case_to_draft_count: 1

The evaluation proves the pipeline can process external customer-support-style data. It does not prove production retrieval quality.

## 10. Legacy RAG Migration Result

CustomerOpsAgent legacy RAG export can be imported into DataHub using a standard JSON shape.

Verified behavior:

- `trusted_import=true` creates approved legacy candidates.
- `trusted_import=false` creates pending-review legacy candidates.
- Duplicate import is idempotent by `source_name + legacy_id`.
- Trusted legacy candidates can enter local RAG.
- Review-required legacy candidates stay outside RAG until approved.

The CustomerOpsAgent repository is not modified by this release.

## 11. Chinese Admin Console

The frontend is a Chinese admin console with:

- P1/P2/P3/P4 capability map.
- Data import and machine cleaning controls.
- Manual cleaning workbench.
- Knowledge review workbench.
- RAG build access from the review console.

P2, P3, and P4 remain Roadmap / not connected. They are visible as product direction only.

## 12. Dark Product Style

P1-M15 upgrades the frontend to a unified dark product style for an AgentOps / data governance management console.

Design choices:

- Deep navy-black surfaces.
- Thin bordered cards.
- Cyan-blue primary actions.
- Green for connected capabilities.
- Purple / muted treatment for roadmap modules.
- Yellow for review warnings and red for risk or rejection.

The style is restrained and dashboard-oriented. No large UI framework, complex animation, or technology stack change is introduced.

## 13. Verified Metrics

Verified repository metrics:

- public dataset sample: 50 conversations / 100 messages
- candidate_count: 50
- approved_count: 10
- rag_chunk_count: 10
- retrieval_hit_count: 5
- bad_case_to_draft_count: 1
- advanced cleaning tests passed
- manual cleaning tests passed
- review quality console tests passed
- unified RAG tests passed
- high-quality DataHub final release test passed

## 14. Current Limitations

Current limitations:

- Local JSON storage only.
- Local keyword/mock retrieval only.
- No real vector database.
- No embedding model.
- No database or ORM.
- No real LLM.
- No production authentication.
- No P2/P3/P4 implementation.

These are intentional Phase 1 boundaries.

## 15. P2 Multimodal Preparation

P1 leaves clear boundaries for Phase 2:

```text
AI Material Center assets
-> material ingestion
-> OCR / Caption / tags / SKU binding
-> human review
-> multimodal knowledge base
```

Phase 2 should start only after a separate scope confirmation.

## 16. Final Release Tag

Final P1 high-quality DataHub release tag:

```text
p1-m15-high-quality-datahub-release
```

Historical tags are kept as-is and are not moved, deleted, or renamed.

## 17. P1-M15.5 UX Cleanup Addendum

P1-M15.5 keeps the P1 high-quality release intact and improves operator usability.

Frontend cleanup:

- The first screen focuses on the product purpose and backend connection status.
- The P1 workflow is presented as Step 1 to Step 5:
  - import
  - machine cleaning
  - manual cleaning
  - knowledge review
  - RAG / Agent
- P1 entry buttons scroll to the real operational workflow.
- P2, P3, and P4 are shown only as Roadmap / not connected.
- Internal technical details are moved into a lower-priority advanced information area.

Boundary review:

- `docs/22_PROJECT_REVIEW_AND_BOUNDARY.md` records current capabilities, demo-friendly flows, technical limits, and capabilities that should not be claimed.
- This addendum does not change the P1 final release tag.
- This addendum does not implement P2/P3/P4, real vector databases, embeddings, database, ORM, real LLM, MCP, or CustomerOpsAgent repository changes.
