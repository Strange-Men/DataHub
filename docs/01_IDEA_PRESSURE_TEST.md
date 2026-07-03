# DataHub Idea Pressure Test

## 1. Compressed Idea

DataHub is a lightweight data asset center for AI applications. In phase one, it turns real customer service chat records into reviewed, traceable, RAG-ready knowledge for CustomerOpsAgent.

The project aims to prove that real business data can be transformed into reliable AI knowledge through a controlled workflow:

```text
raw records -> sanitized records -> extracted drafts -> reviewed knowledge -> RAG index -> CustomerOpsAgent -> Bad Case feedback
```

## 2. Why This Is Worth Building

DataHub is worth building because CustomerOpsAgent cannot rely on scattered prompts, manually pasted FAQs, or unreviewed chat logs for stable production behavior.

The real pain points are:

- Customer service knowledge changes over time.
- Raw chat logs contain noise, duplicates, and private information.
- AI answers need traceable sources.
- Bad Cases need a place to return and become improved knowledge.
- CustomerOpsAgent should execute conversations, not maintain knowledge governance.

Compared with a simple RAG demo, DataHub has stronger project value because it includes:

- Data cleaning.
- Desensitization.
- Human review.
- Knowledge status control.
- Source traceability.
- Bad Case feedback loop.

## 3. Pressure Test Results

| Check | Result | Reason |
| --- | --- | --- |
| Real demand | Pass | CustomerOpsAgent needs reliable knowledge to avoid unstable answers. |
| Clear user scenario | Pass | Phase one serves the data maintainer and CustomerOpsAgent. |
| Differentiation | Pass | It is a governed knowledge production workflow, not only vector search. |
| MVP size | Conditional pass | It is manageable only after narrowing to text customer service data. |
| Technical feasibility | Pass | Import, cleaning, review, and retrieval are controllable with a lightweight stack. |
| Cost | Conditional pass | LLM extraction must be batchable and optional through mock mode. |
| Portfolio value | Pass | Demonstrates RAG, data governance, API boundaries, and AI feedback loops. |
| False demand risk | Medium | Multimodal and fine-tuning are future needs, not phase-one needs. |
| Over-design risk | High | The project can easily drift into an enterprise data platform. |

## 4. Biggest Risk

The biggest risk is scope explosion.

If DataHub tries to support multimodal assets, sales training exports, fine-tuning datasets, MCP, BI dashboards, and enterprise data platform features in the first phase, it will lose the core CustomerOpsAgent loop.

The second major risk is safety leakage:

- Raw data may contain private information.
- Unreviewed knowledge may be incorrect.
- LLM extraction may hallucinate business rules.

Therefore, phase one must enforce a strict rule:

> Un-desensitized data and unreviewed knowledge must never enter RAG or export flows.

## 5. Why The Scope Must Be Narrowed

The useful core is not "manage all company data".

The useful core is:

> Make customer service knowledge reliable enough for CustomerOpsAgent.

This requires narrowing by:

- Data type: text only.
- Consumer: CustomerOpsAgent only.
- Workflow: import, clean, desensitize, extract, review, index, retrieve, feedback.
- Output: RAG-ready approved knowledge.

Everything outside this loop is postponed.

## 6. Why Phase One Only Handles Text Customer Service

Text customer service records are the best phase-one data because:

- They are directly useful to CustomerOpsAgent.
- They contain repeated questions and answers suitable for FAQ extraction.
- They naturally expose rules, escalation conditions, and forbidden answers.
- They can be reviewed manually without building complex media tooling.
- They allow a full closed loop without image, video, or large-scale infrastructure.

Multimodal data is valuable later, but it adds OCR, captioning, tagging, storage, review UI, and quality control problems. Those would distract from the first proof.

## 7. Why CustomerOpsAgent Is The Only Core Consumer

CustomerOpsAgent is the only phase-one core consumer because:

- It is the nearest real user of DataHub knowledge.
- Its Bad Cases can directly validate DataHub's usefulness.
- A single consumer keeps API design stable.
- It prevents premature platformization.
- It creates a clear acceptance path: CustomerOpsAgent can retrieve approved knowledge and return Bad Cases.

Future consumers such as sales agents, operations agents, and agent clusters are reserved as architecture extension points only.

## 8. Final Judgment

DataHub is worth building.

The correct first-phase judgment is:

> Worth building, but only with a narrowed MVP focused on the CustomerOpsAgent text knowledge loop.

The project should move forward only after the scope, API contract, safety rules, and acceptance criteria are documented and kept stable.
