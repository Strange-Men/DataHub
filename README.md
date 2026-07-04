# DataHub

DataHub is a multi-source data governance and RAG knowledge platform for Agent clusters.

DataHub is not only a customer service RAG tool. The final product direction is a governed data asset center that can turn customer service records, product docs, Bad Cases, human corrections, and future AI Material Center assets into reviewed text and multimodal knowledge for CustomerOpsAgent, SalesAgent, OpsAgent, MaterialAgent, and future MCP tool consumers.

Phase one still focuses on the CustomerOpsAgent text knowledge loop. This repository is currently at P1-M10 Legacy RAG Migration: CustomerOpsAgent legacy RAG export samples can be imported into DataHub and normalized into the same candidate, local RAG chunk, and retrieval format.

## Current Scope

Implemented through P1-M10:

- React + TypeScript frontend skeleton.
- FastAPI + Python backend skeleton.
- Frontend base page.
- Backend `/health` endpoint.
- JSON customer service chat import.
- Raw batch metadata listing and lookup.
- Raw batch cleaning and PII masking.
- Sanitized batch lookup.
- Rule-based mock knowledge candidate extraction.
- Pending-review knowledge candidate lookup.
- Human review state transitions for knowledge candidates.
- Local JSON RAG chunk building from approved candidates only.
- Internal keyword/mock RAG search.
- Idempotent local RAG build with duplicate chunk prevention.
- Local RAG search query and `top_k` validation.
- Search debug output with `matched_terms` and source trace.
- CustomerOpsAgent restricted retrieval API over approved local RAG chunks.
- Retrieval trace lookup for later M8 Bad Case linkage.
- Local development auth placeholder for CustomerOpsAgent retrieval: `X-DataHub-Client: CustomerOpsAgent`.
- Unified safe error responses for CustomerOpsAgent retrieval APIs.
- CustomerOpsAgent retrieval contract document.
- CustomerOpsAgent Bad Case submission with `retrieval_id` validation.
- Bad Case queue listing, detail lookup, and manual status/note updates.
- Bad Case to pending-review knowledge candidate draft creation.
- P1 core loop release freeze report and full-chain verification test.
- P1-M9.5 public dataset small-sample evaluation with report and lightweight test.
- P1-M10 legacy RAG export import APIs.
- Trusted legacy import to approved candidates.
- Review-required legacy import to pending-review candidates.
- Idempotent legacy candidate generation using stable `source_name + legacy_id` ids.
- Legacy source trace through candidate, local RAG chunk, and CustomerOpsAgent retrieval results.
- Final vision and four-phase roadmap documentation.
- Documentation consistency fixes for phase status, API roadmap, canonical state names, and M6.5 boundaries.
- Environment example file.
- Development status and stage checklist documents.

Not implemented yet:

- Separate approved knowledge/version management.
- Automatic candidate or RAG chunk modification from Bad Cases.
- Automatic approval or RAG rebuild from Bad Case drafts.
- Multimodal material ingestion and understanding.
- Sales training dataset export.
- Fine-tuning dataset export.
- MCP tools and Agent cluster integration.

## Final Roadmap

```text
Phase 1: Text Customer Service Knowledge Loop
Phase 2: AI Material Center & Multimodal Knowledge
Phase 3: High-quality Dataset Export
Phase 4: MCP Tools & Agent Cluster Integration
```

Current code development remains Phase 1 only. Phase 2, Phase 3, and Phase 4 are formal roadmap phases, not completed features.

Detailed final vision:

```text
docs/10_FINAL_VISION_AND_ROADMAP.md
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Default local URL:

```text
http://localhost:5173
```

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:

```text
GET http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "datahub-api",
  "phase": "P1-M10"
}
```

## M2 JSON Import

Sample file:

```text
samples/customer_chat_sample.json
```

Raw batches are saved locally under:

```text
backend/storage/raw_batches/
```

The storage directory is ignored by Git and must not contain real committed customer records.

### API Verification

Start the backend, then run from the repository root:

```powershell
$payload = Get-Content .\samples\customer_chat_sample.json -Raw
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/sources/import-json `
  -Method Post `
  -ContentType 'application/json' `
  -Body $payload
```

List imported batches:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sources
```

Get one batch by id:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sources/{batch_id}
```

### Frontend Verification

Start both backend and frontend.

1. Open `http://localhost:5173`.
2. Paste the sample JSON from `samples/customer_chat_sample.json`.
3. Keep or edit the source name.
4. Click `Import raw JSON`.
5. Confirm the page shows `batch_id`, `message_count`, `conversation_count`, and `raw_imported`.

## M3 Cleaning And Sanitization

Sanitized batches are saved locally under:

```text
backend/storage/sanitized_batches/
```

Cleaning jobs are saved locally under:

```text
backend/storage/cleaning_jobs/
```

Both directories are ignored by Git through `backend/storage/`.

Supported masking:

- Email -> `[EMAIL]`
- Phone or mobile number -> `[PHONE]`
- Order id -> `[ORDER_ID]`
- Tracking id -> `[TRACKING_ID]`
- Obvious address text -> `[ADDRESS]`

Run cleaning by API:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/cleaning/run/{batch_id} `
  -Method Post
```

Get cleaning job status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/cleaning/jobs/{job_id}
```

Get sanitized batch:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/sanitized/{batch_id}
```

Frontend M3 verification:

1. Start both backend and frontend.
2. Import `samples/customer_chat_sample.json`.
3. In Raw batches, click `Run cleaning`.
4. Confirm summary counts are shown.
5. Confirm sanitized messages show `[EMAIL]`, `[PHONE]`, `[ORDER_ID]`, `[TRACKING_ID]`, and `[ADDRESS]` for the fake sample data.

M3 does not create knowledge drafts, approved knowledge, RAG indexes, embeddings, CustomerOpsAgent integrations, or Bad Case workflows.

## M4 Knowledge Candidate Extraction

Knowledge candidates are saved locally under:

```text
backend/storage/knowledge_candidates/
```

Extraction jobs are saved locally under:

```text
backend/storage/extraction_jobs/
```

Both directories are ignored by Git through `backend/storage/`.

Extraction method:

```text
rule_based_mock
```

The first version only extracts simple sanitized customer -> agent question-answer pairs. It does not call a real LLM.

Run extraction by API:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/extraction/run/{batch_id} `
  -Method Post
```

Get extraction job status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/extraction/jobs/{job_id}
```

List knowledge candidates:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/knowledge/candidates
```

Get one candidate:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/knowledge/candidates/{candidate_id}
```

Frontend M4 verification:

1. Start both backend and frontend.
2. Import `samples/customer_chat_sample.json`.
3. Run cleaning for the raw batch.
4. In Sanitized batches, click `Run extraction`.
5. Confirm extraction summary shows `candidate_count`.
6. Confirm candidates show question, answer, intent, tags, quality score, and `pending_review`.

M4 does not create approved knowledge, RAG indexes, embeddings, CustomerOpsAgent integrations, or Bad Case workflows.

## M5 Human Review

Review records are saved locally under:

```text
backend/storage/review_records/
```

Review updates existing knowledge candidates under:

```text
backend/storage/knowledge_candidates/
```

Both directories are ignored by Git through `backend/storage/`.

Supported review states:

- `pending_review`
- `needs_revision`
- `approved`
- `rejected`

Approved candidates are human-reviewed candidates only. They are not indexed, embedded, or available to CustomerOpsAgent.

List pending review candidates:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/review/pending
```

Edit a candidate:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/knowledge/candidates/{candidate_id} `
  -Method Patch `
  -ContentType 'application/json' `
  -Body '{"question":"Updated question?","answer":"Updated answer.","intent":"shipping","tags":["shipping"],"risk_level":"low","quality_score":0.82}'
```

Approve:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/review/{candidate_id}/approve `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"reviewer":"local_reviewer","review_note":"Approved."}'
```

Reject:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/review/{candidate_id}/reject `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"reviewer":"local_reviewer","review_note":"Rejected."}'
```

Needs revision:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/review/{candidate_id}/needs-revision `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"reviewer":"local_reviewer","review_note":"Needs a clearer answer."}'
```

Frontend M5 verification:

1. Start both backend and frontend.
2. Import sample JSON.
3. Run cleaning.
4. Run extraction.
5. Open the review queue.
6. Edit candidate fields.
7. Enter reviewer and review note.
8. Approve, reject, or mark needs revision.
9. Confirm status updates in the UI.

M5 does not create RAG chunks, embeddings, vector records, CustomerOpsAgent integrations, or Bad Case workflows.

## M6 / M6.5 Local RAG Builder And Quality Hardening

RAG chunks are saved locally under:

```text
backend/storage/rag_chunks/
```

This directory is ignored by Git through `backend/storage/`.

M6 uses:

```text
local_json_mock_retrieval
```

Rules:

- Only `approved` candidates can become RAG chunks.
- `pending_review`, `needs_revision`, and `rejected` candidates are skipped.
- Build is idempotent. Repeating build for the same unchanged approved candidate does not create duplicate chunks.
- Stable chunk ids are derived from candidate ids.
- RAG chunks preserve candidate and source traceability.
- Search uses local JSON plus simple keyword scoring.
- Search validates trimmed query text and `top_k`.
- Search results include `matched_terms` and source trace for debugging.
- Current RAG search is local mock retrieval for DataHub internal testing only.
- This is not CustomerOpsAgent integration.
- This is not production vector retrieval.
- This is not a real vector database, embedding model, database, ORM, or RAG framework.

Build local RAG chunks:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/rag/build `
  -Method Post
```

List local RAG chunks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/rag/chunks
```

Get one chunk:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/rag/chunks/{chunk_id}
```

Search local RAG chunks:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/rag/search `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Frontend M6 verification:

1. Start both backend and frontend.
2. Import sample JSON.
3. Run cleaning.
4. Run extraction.
5. Approve at least one candidate.
6. In Local RAG test, click `Build RAG chunks`.
7. Confirm build summary shows `built_count`, `updated_count`, `skipped_count`, `chunk_count`, and `status`.
8. Confirm RAG chunks list shows approved chunks only.
9. Enter a query and click `Search RAG`.
10. Confirm results show score, matched terms, chunk text, chunk id, candidate id, source conversation id, and tags.

M6.5 does not create CustomerOpsAgent APIs, Bad Case workflows, embeddings, vector records, database/ORM integrations, real LLM calls, multimodal workflows, MCP, sales training export, or fine-tuning.

Lightweight RAG quality verification:

```powershell
python backend\tests\test_rag_quality.py
```

The test covers approved-only chunking, repeated build idempotency, safe search validation, source trace, and the absence of Bad Case routes.

## M7 / M7.5 CustomerOpsAgent Restricted Retrieval

Retrieval traces are saved locally under:

```text
backend/storage/retrieval_logs/
```

This directory is ignored by Git through `backend/storage/`.

M7 uses:

```text
customerops_local_mock_retrieval
```

Rules:

- CustomerOpsAgent retrieval reads only from `backend/storage/rag_chunks/`.
- Only approved local RAG chunks can be returned.
- CustomerOpsAgent retrieval requires `X-DataHub-Client: CustomerOpsAgent`.
- The header is a local development auth placeholder, not production authentication.
- No API key or real token is introduced.
- Raw batches, sanitized batches, and knowledge candidates are not read directly by the CustomerOpsAgent endpoint.
- Each retrieval creates a `retrieval_id` for later M8 Bad Case linkage.
- Retrieval traces store metadata only: query, top_k, filters, result count, result chunk ids, optional conversation/session ids, created time, and retrieval mode.
- This does not modify the CustomerOpsAgent repository.
- M7/M7.5 did not implement Bad Case; M8 adds a separate Bad Case queue below.
- This is still local JSON plus keyword/mock retrieval, not a real vector database, embedding model, database, ORM, or production RAG index.

Retrieve for CustomerOpsAgent:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Read retrieval trace:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrievals/{retrieval_id} `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"}
```

CustomerOpsAgent retrieval contract:

```text
docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md
```

Frontend M7 verification:

1. Start both backend and frontend.
2. Import sample JSON.
3. Run cleaning.
4. Run extraction.
5. Approve at least one candidate.
6. Build RAG chunks.
7. In CustomerOpsAgent Retrieval Test, enter a query and top_k.
8. Click `Test CustomerOps Retrieval`.
9. Confirm `retrieval_id`, score, matched terms, answer, chunk id, candidate id, and source conversation id are shown.

Lightweight M7 verification:

```powershell
python backend\tests\test_customerops_retrieval.py
```

The test covers the full M2-M7.5 path, auth placeholder errors, approved-only retrieval, retrieval trace lookup, and safe query/top_k errors.

## M8 Bad Case Feedback

Bad Cases are saved locally under:

```text
backend/storage/bad_cases/
```

This directory is ignored by Git through `backend/storage/`.

Rules:

- Bad Case submission requires `X-DataHub-Client: CustomerOpsAgent`.
- `retrieval_id` must reference an existing retrieval trace in `backend/storage/retrieval_logs/`.
- Bad Case records store `linked_chunk_ids` and `retrieval_result_count` from the retrieval trace.
- Bad Case records do not copy raw data or sanitized batches.
- M8 does not automatically generate knowledge candidates.
- M8 does not modify existing candidates.
- M8 does not modify RAG chunks.
- M8 does not rebuild or re-index RAG.
- M8 still uses local JSON storage and does not introduce a database, ORM, vector store, embedding model, or real LLM.

Submit a Bad Case:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/bad-cases `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{
    "retrieval_id":"retrieval_xxx",
    "user_query":"Where is my order?",
    "agent_answer":"Your package should arrive soon.",
    "issue_type":"wrong_answer",
    "expected_answer":"The answer should mention tracking status or escalation.",
    "severity":"medium"
  }'
```

List Bad Cases:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/bad-cases
```

View one Bad Case:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/bad-cases/{bad_case_id}
```

Update status and handling note:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/bad-cases/{bad_case_id} `
  -Method Patch `
  -ContentType 'application/json' `
  -Body '{"status":"triaged","review_note":"Confirmed retrieval miss.","resolution_type":"retrieval_tuning"}'
```

Frontend M8 verification:

1. Start both backend and frontend.
2. Complete M2-M6.5 until at least one approved RAG chunk exists.
3. Run CustomerOpsAgent Retrieval Test and copy or reuse the shown `retrieval_id`.
4. In Bad Case Feedback, submit a Bad Case with that `retrieval_id`.
5. Confirm the Bad Case queue shows the submitted record.
6. Select it, update `status` and `review_note`, and confirm the record updates.

Lightweight M8 verification:

```powershell
python backend\tests\test_bad_case_feedback.py
```

The test covers CustomerOpsAgent Bad Case auth, invalid `retrieval_id`, validation errors, successful queue insertion, list/detail/PATCH APIs, retrieval trace linkage, and the boundary that Bad Case management does not create candidates or modify RAG chunks.

## M8.5 Bad Case Resolution To Draft

Bad Case draft candidates are saved under the normal candidate layer:

```text
backend/storage/knowledge_candidates/
```

Rules:

- `POST /api/bad-cases/{bad_case_id}/create-draft` creates a new `pending_review` candidate.
- The generated candidate uses `extraction_method: bad_case_resolution`.
- The generated candidate keeps `source_type: bad_case`, `source_bad_case_id`, `source_retrieval_id`, and `source_chunk_ids`.
- `ignored` Bad Cases cannot create drafts.
- The Bad Case is updated with `status: resolved` and `linked_candidate_id`.
- The new candidate is not approved automatically.
- The new candidate does not enter RAG automatically.
- Existing candidates and RAG chunks are not modified.
- RAG is not rebuilt or re-indexed automatically.

Create a pending-review draft from a Bad Case:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/bad-cases/{bad_case_id}/create-draft `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{
    "question":"Where is my order?",
    "answer":"Please provide your order number or tracking number. If tracking is unavailable, we will escalate this to a human agent.",
    "intent":"order_status",
    "tags":["order","tracking","handoff"],
    "risk_level":"medium",
    "quality_score":0.7,
    "knowledge_type":"faq",
    "reviewer":"local_reviewer",
    "review_note":"Created from Bad Case after human correction."
  }'
```

Then review candidates:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/knowledge/candidates
```

Lightweight M8.5 verification:

```powershell
python backend\tests\test_bad_case_feedback.py
```

The test covers missing and ignored Bad Cases, invalid draft payloads, pending-review candidate creation, source trace preservation, Bad Case `linked_candidate_id` updates, and the boundary that draft creation does not auto-approve, modify RAG chunks, or auto-rebuild RAG.

## P1-M9 Phase-One Release Freeze

P1-M9 freezes and verifies the current Phase 1 core loop:

```text
JSON chat import
-> cleaning / sanitization
-> knowledge candidate extraction
-> human review
-> local RAG chunk build
-> CustomerOpsAgent restricted retrieval
-> Bad Case feedback
-> Bad Case to pending_review draft
```

Release report:

```text
docs/13_P1_RELEASE_FREEZE_REPORT.md
```

Run the P1 core flow verification:

```powershell
python backend\tests\test_phase_one_flow.py
```

P1-M9 is not the final P1 unified RAG release. Remaining P1 milestones are:

- `P1-M9.5 Public Dataset Evaluation`
- `P1-M10 Legacy RAG Migration`
- `P1-M11 Unified RAG Release`

Starting from P1-M9, new Git tags use phase-prefixed names. Historical tags remain unchanged.

## P1-M9.5 Public Dataset Evaluation

P1-M9.5 validates the same P1 core loop with a small public customer-support dataset sample.

Dataset:

```text
Bitext customer support dataset
```

Source:

```text
https://github.com/bitext/customer-support-llm-chatbot-training-dataset
```

Submitted sample:

```text
samples/public_dataset_eval_sample.json
```

The committed sample contains 50 converted customer -> agent conversations and 100 messages. The full public CSV is not committed.

Conversion script:

```powershell
python scripts\prepare_public_dataset_sample.py --help
```

Example conversion command, assuming the public CSV is kept outside the repo:

```powershell
python scripts\prepare_public_dataset_sample.py `
  --input D:\temp\bitext.csv `
  --output samples\public_dataset_eval_sample.json `
  --limit 50
```

Evaluation runner:

```powershell
python scripts\run_public_dataset_eval.py --help
python scripts\run_public_dataset_eval.py --sample samples\public_dataset_eval_sample.json --approve-count 10 --query "cancel order"
```

Automated evaluation test:

```powershell
python backend\tests\test_public_dataset_eval_flow.py
```

Evaluation report:

```text
docs/14_PUBLIC_DATASET_EVAL_REPORT.md
```

P1-M9.5 remains local JSON plus keyword/mock retrieval. It does not migrate CustomerOpsAgent legacy RAG, switch CustomerOpsAgent to a unified RAG, add embeddings, add a vector database, add a database/ORM, or implement Phase 2/3/4.

## P1-M10 Legacy RAG Migration

P1-M10 imports a CustomerOpsAgent legacy RAG export shape into DataHub without reading or modifying the CustomerOpsAgent repository.

Sample file:

```text
samples/legacy_rag_export_sample.json
```

Legacy imports are saved locally under:

```text
backend/storage/legacy_rag_imports/
```

Generated candidates are saved under the existing candidate layer:

```text
backend/storage/knowledge_candidates/
```

Rules:

- `trusted_import=true` creates `approved` candidates with `migration_mode: trusted_import`.
- `trusted_import=false` creates `pending_review` candidates with `migration_mode: review_required`.
- All migrated candidates use `source_type: legacy_rag`.
- All migrated candidates use `extraction_method: legacy_rag_migration`.
- Stable candidate ids are derived from `source_name + legacy_id`.
- Re-importing the same legacy item does not create duplicate candidates.
- Trusted legacy candidates can enter the existing local RAG build.
- Review-required legacy candidates cannot enter RAG until normal review approval.
- CustomerOpsAgent retrieval can return approved legacy chunks with `source_type`, `source_legacy_id`, and `source_import_id`.
- P1-M10 does not switch CustomerOpsAgent to DataHub-only RAG. That is P1-M11.

Import sample legacy RAG export:

```powershell
$payload = Get-Content .\samples\legacy_rag_export_sample.json -Raw

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/legacy-rag/import `
  -Method Post `
  -ContentType 'application/json' `
  -Body $payload
```

List legacy imports:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/legacy-rag/imports
```

Get import detail:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/legacy-rag/imports/{import_id}
```

Then build and retrieve using existing APIs:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/rag/build `
  -Method Post

Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/customer-ops-agent/retrieve `
  -Method Post `
  -Headers @{"X-DataHub-Client"="CustomerOpsAgent"} `
  -ContentType 'application/json' `
  -Body '{"query":"shipping Germany","top_k":5}'
```

Migration report:

```text
docs/15_LEGACY_RAG_MIGRATION_REPORT.md
```

Automated verification:

```powershell
python backend\tests\test_legacy_rag_migration.py
```

P1-M10 still uses local JSON plus keyword/mock retrieval. It does not modify the CustomerOpsAgent repository, does not switch CustomerOpsAgent to DataHub-only retrieval, does not add embeddings, does not add a vector database, does not add a database/ORM, and does not implement Phase 2/3/4.

## Development Rules

Before each development round, read:

- `docs/00_PROJECT_SCOPE.md`
- `docs/01_IDEA_PRESSURE_TEST.md`
- `docs/02_PRD.md`
- `docs/03_ARCHITECTURE.md`
- `docs/04_API_CONTRACT.md`
- `docs/05_DEV_RULES.md`
- `docs/06_TECH_STACK_CANDIDATES.md`
- `docs/07_ACCEPTANCE_CRITERIA.md`
- `docs/08_DEV_STATUS.md`
- `docs/09_STAGE_CHECKLIST.md`
- `docs/10_FINAL_VISION_AND_ROADMAP.md`
- `docs/11_CUSTOMEROPS_RETRIEVAL_CONTRACT.md`
