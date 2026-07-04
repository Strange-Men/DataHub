# P1-M12 Advanced Cleaning Rules

## 1. Machine Cleaning Goal

P1-M12 upgrades DataHub from basic sanitization to deterministic machine cleaning with data quality scoring.

The goal is not to approve knowledge automatically. The goal is to produce safer and more useful sanitized data for:

- P1-M13 manual cleaning.
- P1-M14 knowledge review.
- P1-M15 high-quality DataHub final release.

## 2. Cleaning Rule List

Existing M3 rules remain:

- Trim leading and trailing whitespace.
- Drop empty content.
- Standardize role to `customer`, `agent`, or `system`.
- Apply safe fallback ids for missing fields.
- Mask supported PII patterns.

P1-M12 adds:

- Exact duplicate detection.
- Near duplicate detection.
- Low-quality text detection.
- Possible ad/noise/off-topic labeling.
- Weak customer question and weak agent answer labeling.
- Message-level quality scoring.
- Suggested action for later manual cleaning.

## 3. PII Sanitization Rules

Supported PII and sensitive business identifiers:

- `EMAIL` -> `[EMAIL]`
- `PHONE` -> `[PHONE]`
- `ORDER_ID` -> `[ORDER_ID]`
- `TRACKING_ID` -> `[TRACKING_ID]`
- `ADDRESS` -> `[ADDRESS]`
- `NAME` -> `[NAME]`
- `ZIP_CODE` -> `[ZIP_CODE]`
- `PAYMENT_SENSITIVE` -> `[PAYMENT_SENSITIVE]`

PII detection can add risk flags:

- `contains_personal_data`
- `contains_business_identifier`
- `contains_payment_sensitive`

## 4. Duplicate And Near-Duplicate Detection

Exact duplicate:

- Normalize content by lowercasing and collapsing whitespace.
- If normalized content already appeared in the same batch, mark `exact_duplicate`.

Near duplicate:

- Compare normalized content against prior messages in the same batch.
- Use Python standard library `difflib.SequenceMatcher`.
- If similarity is `>= 0.92`, mark `near_duplicate`.
- Near duplicates are not automatically deleted in P1-M12.

## 5. Low-Quality Text Rules

P1-M12 can mark these issues:

- `low_quality`
- `too_short`
- `too_long`
- `repeated_chars`
- `symbol_noise`
- `possible_garbled_text`

Rule examples:

- Fewer than 3 effective semantic characters -> `too_short`.
- More than 1000 characters -> `too_long`.
- Six or more repeated non-space characters -> `repeated_chars`.
- Very high punctuation/symbol ratio -> `symbol_noise`.
- High non-semantic character ratio in longer content -> `possible_garbled_text`.

## 6. Noise And Ad Rules

P1-M12 uses conservative keyword labels and does not automatically delete suspected noise.

Possible ad terms:

- `free money`
- `click here`
- `promo spam`
- `subscribe now`
- `limited offer`
- `buy now`

Possible noise/off-topic terms:

- `haha`
- `lol`
- `random text`
- `asdf`
- `test test`

Labels:

- `possible_ad`
- `possible_noise`
- `off_topic`

## 7. Quality Score Rules

Each sanitized message receives `quality_score` from `0.0` to `1.0`.

Scoring approach:

- Start from `1.0`.
- Deduct for cleaning issues.
- Deduct lightly for detected PII because masked PII can still leave useful customer service knowledge.
- Deduct more for low-quality, noise, garbled text, and duplicate issues.
- Floor score at `0.0`.

Typical deductions:

- `exact_duplicate`: 0.20
- `near_duplicate`: 0.15
- `too_short`: 0.35
- `too_long`: 0.25
- `repeated_chars`: 0.25
- `symbol_noise`: 0.40
- `possible_garbled_text`: 0.40
- `possible_ad`: 0.30
- `possible_noise`: 0.20
- `weak_answer`: 0.20
- `weak_question`: 0.15

## 8. Quality Level Rules

Quality levels:

- `high`: `quality_score >= 0.8`
- `medium`: `0.5 <= quality_score < 0.8`
- `low`: `quality_score < 0.5`

## 9. Suggested Action Rules

Suggested actions:

- `keep`: high-quality messages that can continue through the pipeline.
- `review`: medium-quality messages or messages with issues that may still be useful.
- `drop`: low-quality messages that should not enter knowledge extraction by default.

P1-M12 does not perform manual cleaning. It only prepares machine suggestions for P1-M13.

## 10. Extraction Usage

P1-M12 extraction behavior:

- `suggested_action: drop` messages are skipped.
- `quality_level: low` messages are skipped.
- Candidate `quality_score` is capped by the average quality score of the source question and answer messages.
- Candidate `cleaning_issues` and `risk_flags` inherit a summary from the source messages.

Extraction remains `rule_based_mock`.

## 11. Current Limitations

- Rules are deterministic and heuristic-based.
- No real LLM is used.
- No embedding model is used.
- No database or ORM is used.
- No production vector database is used.
- Duplicate detection is within one batch only.
- Near duplicate detection uses simple text similarity and may miss semantic duplicates.
- PII detection is conservative and may produce false positives or false negatives.

## 12. P1-M13 Manual Cleaning Connection

P1-M13 should use these fields to build the manual cleaning workbench:

- `cleaning_issues`
- `risk_flags`
- `quality_score`
- `quality_level`
- `suggested_action`

The future manual cleaning workbench should let operators:

- Compare raw and sanitized content.
- Correct sanitized content.
- Override suggested action.
- Mark keep/drop/review.
- Add cleaning notes.

P1-M13 frontend work must read and follow:

```text
C:\Users\16432\Desktop\AI_workflow\前端工作流.md
```
## P1-M13 Manual Cleaning Handoff

Correct frontend workflow file path:

```text
C:\Users\16432\Desktop\AI_workflow\前端工作流.md
```

P1-M13 implements the manual cleaning workbench described above.

Manual cleaning output fields:

- `manual_cleaning_status`
- `manual_cleaned_content`
- `manual_action`
- `cleaner`
- `cleaning_note`
- `manual_cleaned_at`

Extraction behavior:

- `manual_action=drop`: skip the message.
- `manual_action=needs_review`: skip the message by default.
- `manual_action=keep_edited`: use `manual_cleaned_content`.
- `manual_action=keep`: use current sanitized content.

Manual cleaning records are saved under `backend/storage/manual_cleaning_records/`, which remains ignored by Git.

The detailed cleaner-facing guide is `docs/19_MANUAL_CLEANING_GUIDE.md`.
