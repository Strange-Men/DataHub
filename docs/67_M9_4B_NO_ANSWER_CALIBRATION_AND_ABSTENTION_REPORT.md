# P1/P2-M9.4B No-answer Calibration and Abstention Report

## 1. Risk

P1/P2/Unified could correctly filter unreviewed, archived and superseded knowledge yet still return weak keyword or semantic candidates for an out-of-domain or underspecified query. A caller could mistake those candidates for reliable evidence. Provider/database failures also needed to remain operational failures rather than being mislabeled as a knowledge-base miss.

## 2. Central decision design

`backend/app/answerability.py` owns `AnswerabilityConfig`, `AnswerabilityEvidence`, `AnswerabilityDecision`, `AnswerabilityReason` and `evaluate_answerability`. Routes expose results; they do not contain threshold branches. The decision is deterministic and does not depend on an LLM self-reported confidence.

Modes are:

| Mode | Decision metadata | Raw Retrieval | CustomerOpsAgent |
|---|---|---|---|
| `disabled` (default) | calculated | unchanged | unchanged |
| `shadow` | calculated/observable | unchanged | unchanged |
| `enforced` | calculated/enforced | candidates retained | unreliable evidence removed; safe abstention text returned |

The safe text is: `当前知识库中没有找到足够可靠的信息，暂时无法准确回答该问题。` No citation is fabricated and no low-score result is exposed as Agent evidence after enforcement.

## 3. Signals and stable reasons

Signals are normalized query length, effective candidate count, governance-valid evidence count, source-local top score, decision threshold, top1/top2 margin, explicit governed conflict key/value and retrieval branch availability. P2 candidates have already passed active Knowledge Asset, serving index, ready sync, embedding profile/fingerprint and Source Trace validation.

Stable reasons are `ANSWERABLE`, `NO_EVIDENCE`, `LOW_RELEVANCE`, `INSUFFICIENT_EVIDENCE`, `CONFLICTING_EVIDENCE`, `ALL_CANDIDATES_FILTERED`, `QUERY_TOO_AMBIGUOUS` and `RETRIEVAL_UNAVAILABLE`. The final reason is operationally unavailable when retrieval failed and no healthy branch supplied reliable evidence. A healthy Unified branch may still answer while the other branch is unavailable.

## 4. Score semantics and calibrated thresholds

P1 native scores and P2 cosine scores are route-local. Unified `fused_score` is an RRF rank contribution and is never treated as confidence. Unified converts each candidate's `original_score` to a bounded source-local threshold ratio before applying its own gate.

| Scope | Default threshold | Meaning |
|---|---:|---|
| P1 | 0.45 | P1 native retrieval score |
| P2 | 0.55 | P2 native cosine score after governance validation |
| Unified | 1.00 | source-local score divided by that source threshold, capped at 1 |

The offline grid calibration selected the lowest threshold with maximal labeled separation: 0.45 / 0.55 / 1.00, matching runtime defaults. `NO_ANSWER_MIN_EVIDENCE=1` and `NO_ANSWER_AMBIGUOUS_QUERY_MIN_LENGTH=4` are centralized and validated. Values outside their safe bounds, nonnumeric thresholds and unknown modes fail startup/request configuration validation rather than silently degrading.

## 5. Raw Retrieval compatibility

P1 `/api/rag/search`, P2 `/api/v2/retrieval/p2/search` and Unified `/api/v2/retrieval/search` preserve existing candidates, evidence, Source Trace, fallback fields and `retrieval_mode`. They add nested `answerability` metadata containing `answerable`, `no_answer_reason`, `decision_score`, `decision_threshold`, `valid_evidence_count`, mode, enforcement state and bounded decision signals.

P2 failure responses and Unified branch failure responses use `RETRIEVAL_UNAVAILABLE`. Existing failure HTTP semantics remain intact. Retrieval logs add only decision metadata; they contain no vector, Key, Token or connection URL.

## 6. Agent behavior

Both legacy and v2 CustomerOpsAgent paths evaluate P1 evidence. The v2 explicit Unified path reuses the Unified decision. In enforced mode, a negative decision empties `results`, supplies `abstention_message`, retains trace/reason metadata and does not run an answer generator. DataHub still has no internal LLM final-answer generation. Default CustomerOpsAgent routing remains P1-only, and Unified still requires all existing explicit opt-in flags.

## 7. Run-scoped Eval dataset

`backend/tests/fixtures/no_answer_eval.json` contains 26 safe synthetic samples: 11 answerable and 15 no-answer/failure. It includes exact P1/P2/Unified hits, synonym/typo/long-query forms, irrelevant and keyword-overlap negatives, nonexistent claims, archived/old/ready-only candidates, ambiguous/guess/fabrication prompts, explicit conflict and Provider/database/branch failures. Every row declares retrieval mode, expected decision/reason, allowed sources and forbidden sources.

`scripts/run_no_answer_eval.py` writes only to ignored `.local-data/no-answer-eval/<run_id>.json` under `datahub-eval:<run_id>`. It does not seed or clean business corpus.

## 8. Eval results

Authoritative run `m94b-authoritative`:

| Metric | Result |
|---|---:|
| Answerable precision | 1.0000 |
| Answerable recall | 1.0000 |
| No-answer precision | 1.0000 |
| No-answer recall | 1.0000 |
| No-answer F1 | 1.0000 |
| False-answer rate | 0.0000 |
| False-rejection rate | 0.0000 |
| archived leakage | 0 |
| old-version leakage | 0 |
| reason accuracy | 1.0000 |

The dataset has both positive and negative cases, so the result is not achieved by rejecting every query. Its small, curated size is a maintenance gate rather than a claim of production-domain statistical coverage; future corpus growth requires fresh labeled calibration before changing defaults.

## 9. Frontend

The retrieval validation page displays whether the result is answerable, a stable Chinese reason, reliable evidence count, threshold and gate mode. It explicitly explains that `RETRIEVAL_UNAVAILABLE` is a system failure rather than proof that the knowledge base has no answer. It does not show vectors, internal stacks, Secrets or connection details.

## 10. Runtime and regression evidence

- No-answer focused tests: 29 passed, 2 existing FastAPI deprecation warnings.
- Auth/M9.1/frontend/no-answer contracts: 68 passed.
- Unified and CustomerOpsAgent opt-in regression: 33 passed.
- P2 Retrieval foundation within the related run: 20 passed, including Ready/Serve/Archive, fingerprint and old-version gates.
- Clean Git export: 464 collected; 459 passed, 5 explicit disposable-PostgreSQL skips, 44 warnings, 90.24 seconds.
- Frontend production build: PASS, 54 modules, 0.893 seconds.
- Independent test Compose in enforced mode: P1 Harness 10/10 PASS.
- Real SiliconFlow development stack P2 Acceptance: PASS; Ready-before-Serve 0, Serve hit, Archive 0, old version not retrieved, embedding retained, manifest-scoped cleanup performed.
- Test Compose containers, network and volumes were removed; the healthy development stack and its volumes were not removed.

## 11. Preserved boundaries

RRF ranking code, embedding model, database schema, P1/P2 index structures, CustomerOpsAgent default P1-only behavior and Unified opt-in gates are unchanged. Archived and superseded content remain zero-recall. No No-answer runtime manifest, `.env`, Provider Key, Token, database file, frontend `dist` or Docker volume content is committed.

## 12. Known limits and M9.5 entry

Conflict detection requires an explicit governed `conflict_key` and `claim_value`; the gate does not attempt unsafe free-text contradiction inference. The initial labeled set is intentionally small and deterministic. Default deployment mode remains `disabled`; operators should observe `shadow` decisions before explicitly enabling `enforced` in a new environment.

M9.5 may perform clone-style release closure using these exact defaults and must verify disabled/shadow/enforced behavior, P1/P2/Unified/Agent/Auth/frontend chains, persistence, full tests, secret scan and Git cleanliness. M9.5 is not included in this phase.
