# DataHub Project Scope

## 1. What DataHub Is

DataHub is a data asset center for AI application projects.

The final vision is broader than phase one:

```text
DataHub is a multi-source data governance and RAG knowledge platform for Agent clusters.
```

In the long term, DataHub should govern text data, multimodal assets, reviewed knowledge, dataset exports, and MCP-style tool access for multiple Agents. CustomerOpsAgent is the first phase-one consumer, not the only final consumer.

In the first phase, DataHub focuses on turning real customer service chat records into high-quality, reviewed, traceable knowledge that can be used by CustomerOpsAgent through retrieval APIs.

The first-phase value chain is:

```text
Customer service chat records
-> import into DataHub
-> clean, deduplicate, desensitize
-> extract FAQ / standard answers / business rules / human-handoff rules / forbidden-answer rules
-> human review, edit, and supplement
-> approved data enters RAG knowledge base
-> CustomerOpsAgent queries DataHub
-> CustomerOpsAgent sends Bad Cases back
-> DataHub fixes and re-enters the knowledge workflow
```

DataHub owns the knowledge lifecycle. CustomerOpsAgent consumes DataHub knowledge but does not maintain the knowledge base directly.

## 1A. Final Vision

DataHub is not only a customer service RAG tool. The target product is:

```text
DataHub | Multi-source data governance and RAG knowledge platform for Agent clusters
```

Final target flow:

```text
Multi-source business data
-> cleaning / desensitization / standardization
-> knowledge extraction / material understanding / human review
-> text + multimodal RAG knowledge base
-> data service APIs / MCP Tools
-> CustomerOpsAgent / SalesAgent / OpsAgent / MaterialAgent and other Agent consumers
```

The roadmap is formal:

- Phase 1: Text customer service knowledge loop for CustomerOpsAgent.
- Phase 2: AI Material Center and multimodal knowledge.
- Phase 3: High-quality dataset export for sales training and fine-tuning datasets.
- Phase 4: MCP Tools and Agent cluster integration.

This final vision guides architecture decisions, but it does not expand the current implementation scope.

## 2. What DataHub Is Not

DataHub is not:

- An enterprise big data platform.
- A data lakehouse.
- A Spark / Hive / Flink system.
- A BI platform.
- A general document management system.
- A full multimodal asset system in phase one.
- A fine-tuning platform in phase one.
- An MCP server in phase one.
- A project that directly implements sales agents or operations agents.

## 3. Phase-One Consumer

CustomerOpsAgent is the only core consumer in phase one.

CustomerOpsAgent is not the only final consumer. Later phases may serve SalesAgent, OpsAgent, MaterialAgent, a fine-tuning pipeline, and an MCP-based Agent cluster.

Rules:

- CustomerOpsAgent can query DataHub through APIs.
- CustomerOpsAgent can submit Bad Cases through APIs.
- CustomerOpsAgent cannot directly write DataHub knowledge records.
- CustomerOpsAgent cannot directly modify the DataHub database.
- CustomerOpsAgent cannot bypass review and push data into the RAG index.

CodePilot and EnterpriseAiDataAgent are not phase-one dependencies. They may be referenced later only if a concrete integration need appears.

## 4. Phase-One MVP Boundary

Phase one only implements the text customer service knowledge loop.

In scope:

- Import customer service chat records.
- Clean text records.
- Deduplicate repeated or near-repeated records.
- Desensitize sensitive information.
- Extract knowledge drafts:
  - FAQ
  - Standard answers
  - Business rules
  - Human-handoff rules
  - Forbidden-answer rules
- Human review:
  - Approve
  - Reject
  - Edit then approve
  - Supplement missing knowledge
- Build a RAG knowledge base only from approved knowledge.
- Provide retrieval APIs for CustomerOpsAgent.
- Receive Bad Cases from CustomerOpsAgent.
- Allow humans to convert Bad Cases into revised knowledge.
- Preserve traceability from knowledge back to source records and review actions.

## 5. Explicitly Out of Scope

Phase one does not implement:

- Full multimodal processing.
- Image OCR.
- Image caption generation.
- SKU binding.
- Video understanding.
- Sales Agent.
- Operations Agent.
- Real model fine-tuning.
- MCP packaging.
- Spark / Hive / Flink / lakehouse architecture.
- Complex BI dashboards.
- Complex multi-tenant permission systems.
- Automatic knowledge publishing without review.
- Direct database access from CustomerOpsAgent.

## 6. Future Product Roadmap

The architecture should leave extension points for formal later phases:

- Phase 2: AI Material Center assets, image/video/poster ingestion, OCR, Caption, tags, SKU binding, material review, and multimodal knowledge.
- Phase 3: Export reviewed knowledge, excellent replies, Bad Case fixes, and high-quality Q&A into sales onboarding materials, FAQ handbooks, SOP, script handbooks, typical cases, quiz questions, SFT datasets, and Preference datasets.
- Phase 4: Package DataHub as MCP Tools for CustomerOpsAgent, SalesAgent, OpsAgent, MaterialAgent, and future Agent cluster consumers.

These are roadmap directions only. They must not be implemented in phase one.
