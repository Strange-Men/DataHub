# P1-M9 Phase-One Release Freeze Report

## 1. Release Goal

P1-M9 freezes and verifies the current Phase 1 core loop. This milestone is a checkpoint for the DataHub text customer service knowledge workflow, not the final P1 unified RAG release.

Target tag:

```text
p1-m9-phase-one-release-freeze
```

Historical tags remain unchanged and must not be moved, deleted, or renamed.

## 2. Current Completed Chain

The P1 core chain completed through P1-M9 is:

```text
JSON customer service chat import
-> cleaning / sanitization
-> knowledge candidate extraction
-> human review
-> approved candidate to local RAG chunk
-> CustomerOpsAgent restricted retrieval
-> Bad Case submission
-> Bad Case to pending_review candidate
```

The chain remains local JSON plus keyword/mock retrieval. It does not use a real database, ORM, embedding model, vector database, or real LLM.

## 3. Verification Result

Automated verification run for this checkpoint:

```powershell
python -m py_compile backend\app\main.py backend\app\schemas.py backend\app\storage.py
python backend\tests\test_customerops_retrieval.py
python backend\tests\test_rag_quality.py
python backend\tests\test_bad_case_feedback.py
python backend\tests\test_phase_one_flow.py
```

Result:

```text
All commands passed.
```

Verified behaviors:

- Sample JSON can be imported as a raw batch.
- Raw batch can be cleaned and sanitized.
- Sanitized batch can produce knowledge candidates.
- Candidate can be human-approved.
- Only approved candidates can become local RAG chunks.
- CustomerOpsAgent retrieval returns approved local RAG chunks only.
- Retrieval creates a traceable `retrieval_id`.
- Bad Case submission binds to `retrieval_id`.
- Bad Case can be converted into a new `pending_review` candidate.
- Rejected and needs-revision candidates do not enter RAG.
- Bad Case-generated drafts do not auto-approve or alter RAG chunks.

## 4. Core API List

Implemented P1 APIs:

```text
GET  /health

POST /api/sources/import-json
GET  /api/sources
GET  /api/sources/{batch_id}

POST /api/cleaning/run/{batch_id}
GET  /api/cleaning/jobs/{job_id}
GET  /api/sanitized/{batch_id}

POST /api/extraction/run/{batch_id}
GET  /api/extraction/jobs/{job_id}
GET  /api/knowledge/candidates
GET  /api/knowledge/candidates/{candidate_id}
PATCH /api/knowledge/candidates/{candidate_id}

GET  /api/review/pending
POST /api/review/{candidate_id}/approve
POST /api/review/{candidate_id}/reject
POST /api/review/{candidate_id}/needs-revision

POST /api/rag/build
GET  /api/rag/chunks
GET  /api/rag/chunks/{chunk_id}
POST /api/rag/search

POST /api/customer-ops-agent/retrieve
GET  /api/customer-ops-agent/retrievals/{retrieval_id}
POST /api/customer-ops-agent/bad-cases

GET  /api/bad-cases
GET  /api/bad-cases/{bad_case_id}
PATCH /api/bad-cases/{bad_case_id}
POST /api/bad-cases/{bad_case_id}/create-draft
```

## 5. Data State Flow

Canonical P1 state flow:

```text
raw_imported
-> sanitized
-> pending_review
   -> approved -> rag_chunked
   -> needs_revision
   -> rejected
```

Bad Case loop:

```text
CustomerOpsAgent retrieval
-> retrieval_id
-> Bad Case open / triaged / resolved / ignored
-> create pending_review candidate
-> future M5 review
```

`indexed` is reserved for future production retrieval index work. Current P1-M9 stops at local `rag_chunked`.

## 6. Security Boundary Verification

Verified boundaries:

- Raw data is stored only under ignored local storage.
- Sanitized data is separate from raw data.
- Extraction reads sanitized batches, not raw batches.
- Unreviewed candidates cannot enter local RAG chunks.
- Rejected and needs-revision candidates cannot enter local RAG chunks.
- CustomerOpsAgent retrieval reads only local RAG chunks.
- Bad Cases do not copy raw batches or sanitized batches.
- Bad Case draft creation does not modify RAG chunks.
- `backend/storage/` remains Git ignored.

## 7. CustomerOpsAgent Retrieval Boundary

Current CustomerOpsAgent retrieval is:

```text
CustomerOpsAgent
-> POST /api/customer-ops-agent/retrieve
-> approved local rag_chunked results only
```

Rules:

- Requires `X-DataHub-Client: CustomerOpsAgent`.
- Uses local JSON plus keyword/mock retrieval.
- Returns `retrieval_id`, score, matched terms, and source trace.
- Does not return raw batches.
- Does not return sanitized batches directly.
- Does not return knowledge candidates directly.
- Does not modify DataHub knowledge.
- Does not modify the CustomerOpsAgent repository.

## 8. Bad Case Feedback Boundary

Current Bad Case flow:

```text
CustomerOpsAgent
-> POST /api/customer-ops-agent/bad-cases
-> DataHub Bad Case queue
-> POST /api/bad-cases/{bad_case_id}/create-draft
-> pending_review candidate
```

Rules:

- Bad Case submission requires `retrieval_id`.
- Bad Case stores `linked_chunk_ids` and `retrieval_result_count`.
- Bad Case status can be `open`, `triaged`, `resolved`, or `ignored`.
- `ignored` Bad Cases cannot create drafts.
- Draft creation creates a new `kc_badcase_*` candidate.
- Draft creation does not auto-approve.
- Draft creation does not modify existing candidates.
- Draft creation does not modify RAG chunks.
- Draft creation does not rebuild or re-index RAG.

## 9. P1 Work Still Remaining

P1-M9 is a core-loop freeze. P1 final unified RAG release is still later.

Remaining P1 milestones:

- P1-M9.5 Public Dataset Evaluation.
- P1-M10 CustomerOpsAgent legacy RAG migration into DataHub.
- P1-M11 CustomerOpsAgent unified RAG release.

## 10. P2 / P3 / P4 Status

Not implemented:

- P2 AI Material Center and multimodal knowledge.
- P3 sales training dataset export.
- P3 fine-tuning dataset export.
- P4 MCP tool layer.
- P4 Agent cluster integration.

These remain formal roadmap phases only.

## 11. Known Limitations

- Only JSON import is implemented.
- CSV and manual text paste import are not implemented.
- Storage is local JSON files under `backend/storage/`.
- No database or ORM is connected.
- No vector database is connected.
- No embedding model is connected.
- No real LLM extraction is connected.
- Retrieval is keyword/mock scoring, not production vector retrieval.
- No production authentication is implemented.
- CustomerOpsAgent repository is not modified yet.
- Bad Case-generated drafts still require manual review and RAG rebuild after approval.
- No public dataset evaluation has been run yet.

## 12. Next Route

Recommended next milestone:

```text
P1-M9.5 Public Dataset Evaluation
```

Later P1 milestones:

```text
P1-M10 Legacy RAG Migration
P1-M11 Unified RAG Release
```

Do not start P2/P3/P4 implementation until explicitly requested.

## 13. P1-M9.5 Public Dataset Evaluation Addendum

P1-M9.5 has now been completed as the next validation checkpoint after the P1-M9 core-loop freeze.

Evaluation dataset:

```text
Bitext customer support dataset
```

Source:

```text
https://github.com/bitext/customer-support-llm-chatbot-training-dataset
```

Committed evaluation sample:

```text
samples/public_dataset_eval_sample.json
```

Submitted helper artifacts:

```text
scripts/prepare_public_dataset_sample.py
scripts/run_public_dataset_eval.py
backend/tests/test_public_dataset_eval_flow.py
docs/14_PUBLIC_DATASET_EVAL_REPORT.md
```

P1-M9.5 validates that the P1 core loop can process a small external customer-support style dataset sample:

```text
public customer support sample
-> DataHub import JSON
-> cleaning / sanitization
-> candidate extraction
-> controlled approval
-> local RAG chunks
-> CustomerOpsAgent restricted retrieval
-> Bad Case feedback
-> Bad Case to pending_review draft
```

The full public dataset is not committed. P1-M9.5 does not migrate CustomerOpsAgent legacy RAG, does not switch unified RAG, does not introduce embeddings or a vector database, and does not implement P2/P3/P4.
