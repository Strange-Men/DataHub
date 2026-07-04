# DataHub Final Vision And Roadmap

## 1. Final Positioning

DataHub is not only a customer service RAG tool.

Final positioning:

```text
DataHub | Multi-source data governance and RAG knowledge platform for Agent clusters
```

The target product direction is a governed data asset center that can turn customer service records, product documents, Bad Cases, human corrections, and future AI Material Center assets into reviewed text and multimodal knowledge for multiple Agent consumers.

The long-term flow is:

```text
Multi-source business data
-> cleaning / desensitization / standardization
-> knowledge extraction / material understanding / human review
-> text + multimodal RAG knowledge base
-> data service APIs / MCP Tools
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent and other Agent consumers
```

Phase 1 serves CustomerOpsAgent first because the text customer service knowledge loop is the smallest useful closed loop. CustomerOpsAgent is the first core consumer, not the only final consumer.

## 2. Four-Phase Roadmap

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

Phase 1 proves the governed knowledge lifecycle:

- Raw data is separated from sanitized data.
- Sanitized data becomes knowledge candidates.
- Humans approve or reject candidates.
- Only approved knowledge can enter RAG.
- CustomerOpsAgent retrieves controlled knowledge after M7.
- Bad Cases return to DataHub for correction after M8.

Current status:

- Implemented through P1-M12 advanced machine cleaning and data quality scoring.
- P1-M11 is the unified DataHub RAG release, not the final high-quality DataHub release.
- P1-M15 is the planned final Phase 1 high-quality data platform release.
- Current retrieval is CustomerOpsAgent restricted local mock retrieval over approved local RAG chunks.
- Bad Case feedback and Bad Case to `pending_review` draft creation are implemented.
- Public dataset evaluation and legacy RAG migration are implemented in P1.
- Phase 2, Phase 3, and Phase 4 remain roadmap only.

Phase 1 high-quality extension route:

- P1-M12: Advanced Machine Cleaning & Data Quality Scoring.
  - Detect exact duplicates and near duplicates.
  - Detect low-quality text, possible noise, weak questions, and weak answers.
  - Improve PII masking.
  - Add quality score, quality level, risk flags, and suggested action for each sanitized message.
- P1-M13: Chinese Admin Console & Manual Cleaning Workbench.
  - Full Chinese admin experience.
  - P1/P2/P3/P4 module entry reservation.
  - Raw versus sanitized comparison.
  - Manual sanitized content correction, keep/drop/review decisions, and cleaning notes.
- P1-M14: Knowledge Review Quality Console.
  - Chinese candidate review workbench.
  - Candidate editing, approve, reject, and needs_revision.
  - Source trace, quality_score, cleaning_issues, and risk_flags.
  - Reviewer standards for FAQ, standard answer, business rule, human handoff rule, and forbidden answer rule.
- P1-M15: High-quality DataHub P1 Final Release.
  - Validate machine cleaning -> manual cleaning -> extraction -> human review -> unified RAG -> CustomerOpsAgent retrieval -> Bad Case feedback.
  - Publish the final P1 high-quality DataHub acceptance report.

### Phase 2: AI Material Center And Multimodal Knowledge

```text
Ops Agent / AI Material Center generated images, videos, and poster assets
-> material ingestion
-> OCR / Caption / tags / SKU binding
-> human review
-> multimodal knowledge base
-> CustomerOpsAgent image-text / multimodal customer service
```

Phase 2 extends DataHub from text knowledge governance into multimodal asset governance. The goal is not just to store images or videos, but to turn reviewed materials into retrievable business knowledge with traceable source metadata.

Expected capabilities:

- AI Material Center asset ingestion.
- Image and poster OCR.
- Caption generation or caption correction.
- Asset tags and business labels.
- SKU or product binding.
- Human review for material understanding.
- Multimodal retrieval preparation for CustomerOpsAgent.

Current status:

- Roadmap only.
- Not implemented.

### Phase 3: High-Quality Dataset Export

```text
Reviewed customer service knowledge, excellent human replies, Bad Case fixes, high-quality Q&A
-> sales onboarding materials
-> FAQ handbook / SOP / script handbook / typical cases / quiz questions
-> SFT dataset / Preference dataset
-> reduce AI flavor and improve brand voice, service style, and refusal rules
```

Phase 3 turns reviewed knowledge assets into training and improvement datasets.

Expected outputs:

- Sales onboarding FAQ handbooks.
- SOP documents.
- Customer service script handbooks.
- Typical case libraries.
- Quiz and assessment questions.
- Supervised fine-tuning dataset exports.
- Preference dataset exports.

Current status:

- Roadmap only.
- Not implemented.
- DataHub may export datasets later, but DataHub itself does not need to train models.

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

Phase 4 packages DataHub capabilities as stable tools for the Agent cluster.

Potential tool layer:

- `search_customer_knowledge`
- `search_multimodal_assets`
- `submit_bad_case`
- `export_training_dataset`
- `export_finetune_dataset`

Expected consumers:

- CustomerOpsAgent
- SalesAgent
- OpsAgent
- MaterialAgent
- Future fine-tuning pipeline

Current status:

- Roadmap only.
- Not implemented.

## 3. Current Development Boundary

Current code development still only implements Phase 1.

Phase 2, Phase 3, and Phase 4 are formal product roadmap phases, but they must not be implemented early.

## 2A. Frontend Product Principles For P1-M13 And Later

- The frontend should become Chinese-first.
- The frontend should reserve entries and cards for the P1/P2/P3/P4 final product structure.
- Backend capabilities are still connected stage by stage.
- Unimplemented modules must be clearly marked as Roadmap / Not Connected.
- The frontend must not falsely show P2/P3/P4 features as completed.
- Before future frontend development, read and follow:

```text
C:\Users\16432\Desktop\AI_workflow\前端工作流.md
```

Current forbidden work remains:

- No full multimodal implementation.
- No image OCR, Caption, or SKU binding implementation.
- No video understanding.
- No sales training export implementation.
- No fine-tuning dataset export implementation.
- No MCP implementation.
- No SalesAgent, OpsAgent, or MaterialAgent integration.
- No enterprise big data platform expansion.

The roadmap should guide architecture decisions without breaking the small-step development discipline.

## 4. Target Architecture

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

Current implementation covers only the early Phase 1 path:

```text
Customer chat logs
-> Ingestion
-> Cleaning & Sanitization
-> Knowledge Extraction
-> Human Review
-> Local RAG Builder
-> CustomerOpsAgent Restricted Retrieval
-> Bad Case Feedback
-> Bad Case To Pending Review Draft
-> Public Dataset Evaluation
-> Legacy RAG Migration
-> Unified Local RAG Release
```

Future modules are real roadmap modules, not current implementation commitments.

## 5. Resume-Ready Project Positioning

Resume-safe positioning:

```text
DataHub | Multi-source data governance and RAG knowledge platform for Agent clusters

Designed and implemented a DataHub data asset center for cross-border e-commerce AI applications. The system supports cleaning, desensitization, knowledge extraction, and human review from customer service chat records, builds traceable local RAG chunks, and prepares governed knowledge for CustomerOpsAgent. The architecture reserves extension paths for AI Material Center integration, multimodal knowledge bases, sales training dataset export, fine-tuning dataset export, and MCP-based Agent cluster access, forming an AI data loop across data governance, knowledge production, Agent consumption, and feedback iteration.
```

Important wording rules:

- Current completed work should be described as Phase 1 text customer service knowledge governance through P1-M12 advanced data cleaning. P1-M11 remains the unified DataHub RAG release milestone, and P1-M15 is the planned high-quality DataHub P1 final release.
- CustomerOpsAgent restricted retrieval is implemented locally from M7 onward.
- Bad Case feedback is implemented from M8 onward.
- Bad Case to pending-review draft creation is implemented from M8.5 onward.
- Phase 2, Phase 3, and Phase 4 should be described as architecture reservations or roadmap extensions unless they are actually implemented later.

## 6. P1-M13 Update

P1-M13 adds the Chinese admin console and manual cleaning workbench needed for high-quality text data governance.

The final vision remains unchanged:

- DataHub is not just a customer service RAG demo.
- DataHub is the multi-source data governance and RAG knowledge platform for an Agent cluster.
- Current code continues to stay in Phase 1.
- P2/P3/P4 are formal roadmap capabilities and must not be implemented until explicitly started.

P1-M13 strengthens the path from machine-cleaned data to human-verified data by letting cleaners edit sanitized content and save cleaning decisions before knowledge extraction.
