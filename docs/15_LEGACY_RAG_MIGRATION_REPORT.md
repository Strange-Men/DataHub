# P1-M10 Legacy RAG Migration Report

## 1. M10 Goal

P1-M10 migrates CustomerOpsAgent legacy RAG knowledge assets into DataHub through a standard legacy export JSON format.

The goal is to prove that old CustomerOpsAgent RAG knowledge can become normal DataHub knowledge candidates, local RAG chunks, and CustomerOpsAgent retrieval results without keeping two unmanaged RAG systems forever.

Current P1-M10 flow:

```text
CustomerOpsAgent legacy RAG export
-> DataHub legacy RAG import
-> DataHub knowledge candidates
-> optional trusted approval
-> local RAG build
-> CustomerOpsAgent restricted retrieval test
```

P1-M10 does not modify the CustomerOpsAgent repository and does not switch CustomerOpsAgent to DataHub-only retrieval. That belongs to P1-M11.

## 2. Why Migrate CustomerOpsAgent Legacy RAG

CustomerOpsAgent may already have useful RAG knowledge. Leaving that knowledge outside DataHub creates two problems:

- Knowledge governance is split across CustomerOpsAgent and DataHub.
- Future Bad Case and review flows cannot consistently trace and improve old knowledge.

M10 moves legacy knowledge into DataHub's governed structure:

- Same candidate model.
- Same approved / pending review states.
- Same local RAG chunk format.
- Same CustomerOpsAgent retrieval result shape.
- Same source trace discipline.

## 3. Legacy Export Format

Sample file:

```text
samples/legacy_rag_export_sample.json
```

Expected shape:

```json
{
  "source_name": "customerops_legacy_rag_sample",
  "source_type": "legacy_rag",
  "trusted_import": true,
  "exported_at": "2026-07-03T10:00:00+00:00",
  "items": [
    {
      "legacy_id": "legacy_shipping_001",
      "question": "How long does shipping take to Germany?",
      "answer": "Shipping to Germany usually takes 7-12 business days after dispatch.",
      "intent": "shipping",
      "tags": ["shipping", "delivery"],
      "risk_level": "low",
      "quality_score": 0.85,
      "source_note": "Migrated from CustomerOpsAgent legacy RAG."
    }
  ]
}
```

The sample uses fake knowledge only. No CustomerOpsAgent private RAG data or real business knowledge is committed.

## 4. trusted_import / review_required Modes

### trusted_import

When `trusted_import=true`, DataHub treats the legacy item as already-live knowledge from CustomerOpsAgent:

```text
legacy item -> approved candidate
```

Generated candidate fields:

```text
source_type: legacy_rag
migration_mode: trusted_import
review_status: approved
extraction_method: legacy_rag_migration
```

This is a migration shortcut, not a general bypass of review. The candidate remains traceable and can be sampled, reviewed, downgraded, or replaced later.

### review_required

When `trusted_import=false`, DataHub treats the legacy item as uncertain quality:

```text
legacy item -> pending_review candidate
```

Generated candidate fields:

```text
source_type: legacy_rag
migration_mode: review_required
review_status: pending_review
extraction_method: legacy_rag_migration
```

Review-required legacy candidates cannot enter local RAG chunks until the normal M5 review approves them.

## 5. Deduplication And Idempotency Strategy

M10 uses stable candidate ids derived from:

```text
source_name + legacy_id
```

The generated id shape is:

```text
kc_legacy_{sha1_prefix}
```

Rules:

- If the candidate does not exist, DataHub creates it.
- If the candidate already exists and content is unchanged, DataHub skips it.
- If the candidate already exists and content changed, DataHub updates the same candidate.
- DataHub never creates duplicate candidates for the same `source_name + legacy_id`.

Import metadata records each run separately under:

```text
backend/storage/legacy_rag_imports/
```

## 6. Source Trace Fields

Legacy candidates preserve:

```text
source_type: legacy_rag
source_legacy_id
source_import_id
source_batch_id: null
source_conversation_id: null
source_message_ids: []
migration_mode
source_note
```

These fields flow into RAG chunks and CustomerOpsAgent retrieval results.

## 7. RAG Build Verification

P1-M10 does not add a new RAG build API.

Existing API:

```text
POST /api/rag/build
```

Verified:

- Trusted legacy candidates with `review_status: approved` can become local RAG chunks.
- Review-required legacy candidates with `review_status: pending_review` are skipped by RAG build.
- RAG build remains local JSON plus keyword/mock retrieval.

## 8. Retrieval Verification

Existing API:

```text
POST /api/customer-ops-agent/retrieve
```

Verified:

- CustomerOpsAgent retrieval can return approved legacy chunks.
- Results include `source_type: legacy_rag`.
- Results include `source_legacy_id`.
- Results include `source_import_id`.
- Results include normal retrieval fields such as score, matched terms, candidate id, and chunk id.

## 9. CustomerOpsAgent Repository Boundary

P1-M10 does not:

- Read the CustomerOpsAgent repository.
- Modify the CustomerOpsAgent repository.
- Delete CustomerOpsAgent's old RAG.
- Switch CustomerOpsAgent to DataHub-only retrieval.
- Implement P1-M11.

The real CustomerOpsAgent cutover is intentionally left for P1-M11.

## 10. Verification Result

Required verification:

```powershell
python -m py_compile backend\app\main.py backend\app\schemas.py backend\app\storage.py
python backend\tests\test_customerops_retrieval.py
python backend\tests\test_rag_quality.py
python backend\tests\test_bad_case_feedback.py
python backend\tests\test_phase_one_flow.py
python backend\tests\test_public_dataset_eval_flow.py
python backend\tests\test_legacy_rag_migration.py
```

Expected result:

```text
All commands pass.
```

## 11. P1-M10 Non-Goals

At the time of P1-M10, this milestone did not implement:

- P1-M11 unified DataHub RAG release.
- Production vector retrieval.
- Embedding model.
- Real vector database.
- Database or ORM.
- Real LLM.
- Multimodal workflows.
- Sales training export.
- Fine-tuning export.
- MCP.
- P2/P3/P4 features.

## 12. P1-M11 Unified DataHub RAG Release Addendum

P1-M11 has now been completed after this migration checkpoint.

P1-M11 confirms:

```text
CustomerOpsAgent legacy RAG export
+ DataHub chat log candidates
+ public dataset candidates
+ approved Bad Case drafts
-> unified DataHub local RAG chunks
-> CustomerOpsAgent restricted retrieval API
```

Submitted release artifacts:

```text
docs/16_P1_UNIFIED_RAG_RELEASE_REPORT.md
docs/17_CUSTOMEROPS_DATAHUB_ONLY_INTEGRATION_GUIDE.md
backend/tests/test_unified_rag_release.py
README.md
README.en.md
```

The P1-M11 release still does not modify the CustomerOpsAgent repository. It documents and validates the DataHub-only retrieval contract from the DataHub side.

P1-M11 still does not introduce:

- real vector database,
- embedding model,
- database or ORM,
- real LLM,
- MCP,
- P2/P3/P4 features.
