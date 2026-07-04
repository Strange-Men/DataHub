# P1-M9.5 Public Dataset Evaluation Report

## 1. Evaluation Goal

P1-M9.5 validates whether DataHub's Phase 1 core loop can process a small public customer-support style dataset sample.

Target flow:

```text
public customer support dataset sample
-> DataHub M2 import JSON
-> M3 cleaning / sanitization
-> M4 knowledge candidate extraction
-> M5 controlled approval
-> M6/M6.5 local RAG chunk build
-> M7/M7.5 CustomerOpsAgent restricted retrieval
-> M8 Bad Case feedback
-> M8.5 Bad Case to pending_review draft
```

This stage is an evaluation stage. It does not implement P1-M10 legacy RAG migration, P1-M11 unified RAG release, or any P2/P3/P4 capability.

## 2. Dataset Selection

Selected dataset:

```text
Bitext customer support dataset
```

Selection reason:

- It is closer to customer support than generic product reviews.
- It has customer-style instructions and assistant-style responses.
- It includes intent/category fields that are useful for later QA and retrieval quality analysis.
- It is more suitable for Phase 1 text customer service evaluation than multimodal or structured order datasets.

## 3. Dataset Source

Source URL:

```text
https://github.com/bitext/customer-support-llm-chatbot-training-dataset
```

Source data file:

```text
data/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv
```

Download / access method:

- The original CSV was downloaded to a local temporary directory for evaluation.
- The original CSV was not committed to the repository.
- The submitted repository contains only a 50-conversation converted sample and conversion/evaluation scripts.

License note:

- The upstream repository includes `LICENSE.txt` using Community Data License Agreement - Sharing - Version 1.0.
- This report records only a brief license note; future broader dataset usage should re-check the current upstream license and usage restrictions before any production or commercial reuse.

Fields used:

- `instruction` -> customer message content.
- `response` -> agent message content.
- `intent` / `category` -> referenced in evaluation notes; not stored directly in the DataHub import JSON because the current M2 schema accepts conversations and messages only.

## 4. Sampling Strategy

Sampling configuration:

```text
sample size: 50 QA rows
converted conversations: 50
converted messages: 100
source_name: public_dataset_eval_bitext_sample
```

The sample was generated with:

```powershell
python scripts\prepare_public_dataset_sample.py `
  --input D:\temp\bitext.csv `
  --output samples\public_dataset_eval_sample.json `
  --limit 50 `
  --source-name public_dataset_eval_bitext_sample
```

Submitted sample:

```text
samples/public_dataset_eval_sample.json
```

The full public dataset is not committed.

## 5. Data Conversion Format

Each CSV row was converted into a two-message DataHub conversation:

```json
{
  "conversation_id": "public_eval_conv_001",
  "messages": [
    {
      "message_id": "public_eval_msg_001_customer",
      "role": "customer",
      "content": "question about cancelling order {{Order Number}}",
      "timestamp": "2026-07-03T10:02:00"
    },
    {
      "message_id": "public_eval_msg_001_agent",
      "role": "agent",
      "content": "I've understood you have a question regarding canceling order {{Order Number}}...",
      "timestamp": "2026-07-03T10:03:00"
    }
  ]
}
```

Conversion rules:

- `role` is limited to `customer` and `agent`.
- Every row creates one customer -> agent pair.
- The sample contains public template placeholders rather than real private customer identifiers.
- The sample is intentionally small and safe to commit.

## 6. DataHub Pipeline Result

Evaluation command:

```powershell
python scripts\run_public_dataset_eval.py --sample samples\public_dataset_eval_sample.json --approve-count 10 --query "cancel order"
```

Result summary:

```text
import: passed
cleaning: passed
extraction: passed
controlled approval: passed
RAG build: passed
CustomerOpsAgent retrieval: passed
Bad Case submit: passed
Bad Case to draft: passed
```

Recorded metrics:

```text
raw_conversation_count: 50
raw_message_count: 100
sanitized_message_count: 100
dropped_message_count: 0
candidate_count: 50
approved_count: 10
rag_chunk_count: 10
retrieval_test_count: 1
retrieval_hit_count: 5
bad_case_count: 1
bad_case_to_draft_count: 1
```

## 7. Cleaning / Sanitization Result

Cleaning result:

```text
raw_message_count: 100
sanitized_message_count: 100
dropped_message_count: 0
```

Observation:

- The selected sample uses public template placeholders such as `{{Order Number}}`.
- No real private customer records were introduced.
- The current PII masking rules remain available for email, phone, order id, tracking id, and obvious address patterns.

## 8. Candidate Extraction Result

Extraction method:

```text
rule_based_mock
```

Candidate result:

```text
candidate_count: 50
```

Observation:

- The dataset's instruction/response shape maps cleanly into DataHub's current customer -> agent pair extraction.
- The extraction output is still a candidate layer only.
- All extracted candidates require review before they can enter local RAG chunks.

## 9. Human Review / Controlled Approval Result

Controlled approval:

```text
approved_count: 10
```

Review method:

- The evaluation approved 10 candidates through the existing M5 review API.
- This was controlled local approval for evaluation, not automatic production approval.

Boundary:

- Non-approved candidates remained outside RAG.
- Rejected and needs-revision candidates were verified by automated tests to stay out of RAG.

## 10. RAG Build Result

RAG build method:

```text
local_json_mock_retrieval
```

Result:

```text
rag_chunk_count: 10
build_status: completed
```

Boundary:

- Only approved candidates were converted into local RAG chunks.
- The build remained local JSON plus mock retrieval.
- No vector database, embedding model, database, ORM, real LLM, or production RAG index was introduced.

## 11. Retrieval Test Cases

CustomerOpsAgent retrieval test query:

```text
cancel order
```

Result:

```text
retrieval_test_count: 1
retrieval_hit_count: 5
retrieval_mode: customerops_local_mock_retrieval
```

Observation:

- Retrieval returned approved local `rag_chunked` results with scores, matched terms, and source trace.
- The result demonstrates that external customer-support style records can enter the controlled DataHub retrieval path after review and local RAG build.
- The result does not prove production-grade semantic retrieval quality.

## 12. Bad Case Feedback Test

Bad Case test:

```text
bad_case_count: 1
```

Result:

- A CustomerOpsAgent-style Bad Case was submitted with the generated `retrieval_id`.
- The Bad Case was bound to retrieval trace metadata.
- The Bad Case entered DataHub's Bad Case queue.

Boundary:

- Bad Case submission did not modify existing candidates.
- Bad Case submission did not modify RAG chunks.
- Bad Case submission did not trigger automatic RAG rebuild or re-index.

## 13. Bad Case To Draft Test

Bad Case to draft result:

```text
bad_case_to_draft_count: 1
draft_review_status: pending_review
```

Result:

- The Bad Case was converted into a new `pending_review` candidate.
- The generated candidate preserved Bad Case source trace:
  - `source_bad_case_id`
  - `source_retrieval_id`
  - `source_chunk_ids`

Boundary:

- The generated candidate was not auto-approved.
- The generated candidate did not enter RAG automatically.
- Existing RAG chunks were not modified.

## 14. Quality Observations

- The public dataset is not the user's real customer chat history.
- Because this selected dataset is customer-support QA style, it is suitable for testing customer intent, FAQ candidate extraction, RAG retrieval, and Bad Case feedback.
- The dataset is cleaner and more templated than real messy chat logs, so it does not fully stress duplicate handling, noisy multi-turn conversations, or real private-data masking.
- Current extraction remains `rule_based_mock`.
- Current retrieval remains local keyword/mock retrieval.
- The evaluation proves pipeline usability and boundary enforcement on external public-style data.
- The evaluation does not prove production semantic retrieval quality.
- Production quality still requires later CustomerOpsAgent legacy RAG migration, unified RAG switching, real evaluation queries, and a stronger retrieval stack decision.

## 15. Current Limitations

- The evaluation sample is only 50 QA rows.
- Only JSON import was tested.
- CSV import into DataHub is still not implemented as a product API; CSV conversion is handled by an offline helper script.
- The current data shape is two-turn QA, not full multi-turn customer conversations.
- No real vector database is used.
- No embedding model is used.
- No database or ORM is used.
- No real LLM extraction is used.
- No CustomerOpsAgent repository changes were made.
- No P1-M10 legacy RAG migration was started.
- No P1-M11 unified RAG release was started.
- No P2/P3/P4 features were implemented.

## 16. Next Step: P1-M10 Legacy RAG Migration

Recommended next milestone:

```text
P1-M10 Legacy RAG Migration
```

P1-M10 should focus on identifying the existing CustomerOpsAgent RAG knowledge source and migrating it into DataHub's governed flow without bypassing:

- sanitization boundaries
- human review boundaries
- approved-only RAG chunking
- CustomerOpsAgent read-only retrieval boundaries
- Bad Case feedback traceability

P1-M10 must still avoid P2/P3/P4 implementation unless explicitly started.
