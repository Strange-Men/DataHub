# Manual Cleaning Guide For DataHub Cleaners

This guide is written for DataHub cleaning operators. It explains how to review machine-cleaned customer service messages before they are used for knowledge extraction.

## 1. Manual Cleaning Goal

Manual cleaning improves sanitized messages after machine cleaning.

The goal is to keep useful customer service knowledge, remove or mark low-value content, and make sure private data stays masked.

Manual cleaning must not change the original raw batch. Raw data is the audit source and remains read-only.

## 2. What Cleaners Check Every Day

For each sanitized batch, check:

- Messages marked `low` quality.
- Messages with `suggested_action: review` or `drop`.
- Messages with PII types.
- Messages with duplicate or near-duplicate issues.
- Messages with weak customer questions or weak agent answers.
- Messages that look like business rules, escalation rules, or forbidden-answer rules.

## 3. What Can Be Kept

Choose `keep` when:

- The content is already safely sanitized.
- The message has clear business value.
- The customer question or agent answer is meaningful.
- No additional rewriting is needed.

Example:

```text
Customer: How long does shipping take to Germany?
Agent: Shipping to Germany usually takes 7-12 business days after dispatch.
Action: keep
```

## 4. What Should Be Edited And Kept

Choose `keep_edited` when:

- PII is already masked but wording needs cleanup.
- The message has business value but contains extra noise.
- The answer is useful but should be normalized before extraction.
- The original meaning can be preserved.

Before:

```text
yeah it should arrive around 7-12 biz days after it ships!!!
```

After:

```text
Shipping usually takes 7-12 business days after dispatch.
```

Action: `keep_edited`

Do not rewrite the business meaning.

## 5. What Should Be Dropped

Choose `drop` when:

- The message is empty or meaningless.
- The text is only punctuation, emoji, or repeated characters.
- The message is advertising or spam.
- The content is unrelated to customer service.
- The answer is unsafe or too broken to repair.

Example:

```text
!!!!!!
Action: drop
```

Dropped messages are skipped by knowledge extraction.

## 6. What Needs Review

Choose `needs_review` when:

- The cleaner is not sure whether the text is safe.
- The text may contain policy, legal, payment, or privacy risk.
- The answer may conflict with business rules.
- The message may be valuable but needs a senior reviewer.

Messages marked `needs_review` are skipped by extraction by default.

## 7. PII Handling

Private data must stay masked.

Common PII markers:

- `[EMAIL]`
- `[PHONE]`
- `[ORDER_ID]`
- `[TRACKING_ID]`
- `[ADDRESS]`
- `[NAME]`
- `[ZIP_CODE]`
- `[PAYMENT_SENSITIVE]`

If a machine-cleaned message still exposes private data, edit it and choose `keep_edited`, or mark `needs_review` if unsure.

Never restore real private data into sanitized content.

## 8. Duplicate And Near-Duplicate Handling

For exact duplicates:

- Keep the clearest first useful copy.
- Drop repeated copies when they add no new information.

For near duplicates:

- Keep the version with the clearest question and answer.
- Mark the weaker version as `drop` or `needs_review`.

## 9. Low-Quality Text Handling

Low-quality markers include:

- `too_short`
- `too_long`
- `repeated_chars`
- `symbol_noise`
- `possible_garbled_text`
- `weak_question`
- `weak_answer`

If the business meaning is still clear, edit and keep. If not, drop or mark for review.

## 10. Ads, Noise, And Chatter

Messages marked as `possible_ad`, `possible_noise`, or `off_topic` should normally be dropped unless they contain a real customer service issue.

Examples to drop:

```text
free money click here
haha lol random text
subscribe now promo spam
```

## 11. Customer Service Value

Useful customer service knowledge often includes:

- Shipping timelines.
- Refund and return rules.
- Order status handling.
- Product information.
- Escalation or handoff triggers.
- Forbidden answers or sensitive response boundaries.

Keep or edit messages that help produce these knowledge types.

## 12. Human Handoff Rules

Preserve messages that explain when the agent should escalate to a human.

Example:

```text
If tracking is unavailable or the customer reports payment risk, escalate to a human agent.
```

Action: `keep` or `keep_edited`.

## 13. Forbidden-Answer Rules

Preserve rules that tell the agent what not to answer.

Example:

```text
Do not promise guaranteed delivery dates when the logistics carrier has not confirmed tracking.
```

Action: `keep` or `keep_edited`.

## 14. How To Write Cleaning Notes

Good notes are short and specific:

- `PII checked, business meaning preserved.`
- `Dropped duplicate with no additional value.`
- `Marked for senior review due to payment-sensitive content.`
- `Normalized answer wording without changing policy.`

Avoid vague notes like:

- `fixed`
- `ok`
- `done`

## 15. Examples

Good example:

```text
Before: Ship Germany 7-12 days after dispatch, pls wait.
After: Shipping to Germany usually takes 7-12 business days after dispatch.
Action: keep_edited
Note: Normalized wording and preserved shipping rule.
```

Bad example:

```text
Before: My phone is 202-555-0101 and order is ORDER-12345.
After: My phone is 202-555-0101 and order is ORDER-12345.
Action: keep
Problem: PII was restored or left exposed.
```

Corrected example:

```text
After: My phone is [PHONE] and order is [ORDER_ID].
Action: keep_edited
Note: Masked remaining private data.
```

## 16. After Manual Cleaning

Manual cleaning affects knowledge extraction:

- `keep`: extraction uses current sanitized content.
- `keep_edited`: extraction uses `manual_cleaned_content`.
- `drop`: extraction skips the message.
- `needs_review`: extraction skips the message by default.

Manual cleaning does not approve knowledge and does not write RAG chunks. Cleaned messages still go through knowledge extraction and human review before they can become retrieval-ready knowledge.
