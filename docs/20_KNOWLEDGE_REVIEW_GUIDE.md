# Knowledge Review Guide For DataHub Reviewers

This guide is written for knowledge reviewers. It explains how to decide whether a knowledge candidate can become approved DataHub knowledge and later enter RAG.

## 1. Review Goal

Knowledge review protects CustomerOpsAgent from unsafe, inaccurate, low-quality, or untraceable answers.

The reviewer decides whether a candidate should be:

- Approved.
- Rejected.
- Sent back for revision.

Only `approved` candidates can enter local RAG chunks. `pending_review`, `needs_revision`, and `rejected` candidates must not enter RAG.

## 2. What Reviewers Check Every Day

Reviewers should focus on:

- `pending_review` candidates.
- `needs_revision` candidates that were corrected.
- Candidates with low or medium `quality_score`.
- Candidates with `risk_flags`.
- Candidates generated from Bad Cases.
- Legacy RAG migration candidates that require review.
- Public dataset candidates before they are used as product knowledge.

## 3. What Can Be Approved

Approve a candidate when:

- The question is clear.
- The answer is accurate and actionable.
- Private data is not exposed.
- The source trace is present.
- The intent and tags are reasonable.
- The answer does not overpromise.
- The knowledge type is appropriate.
- The content can safely help CustomerOpsAgent answer a customer.

## 4. What Should Be Rejected

Reject a candidate when:

- The answer is wrong.
- The answer is unsafe.
- The candidate contains private data.
- The candidate is spam, noise, or unrelated.
- The business meaning is unclear.
- The answer cannot be fixed with a small edit.
- The source trace is missing and the reviewer cannot verify it.

## 5. What Should Be Sent Back For Revision

Use `needs_revision` when:

- The candidate is useful but incomplete.
- The answer is too vague.
- The tags or intent are wrong.
- The answer needs policy confirmation.
- The candidate may be high-risk and needs a senior reviewer.

Do not approve uncertain knowledge.

## 6. FAQ Review Rules

FAQ candidates should answer one clear customer question.

Approve when:

- The question is specific.
- The answer directly responds to the question.
- The answer can be reused.

Send back when:

- The answer is too generic.
- The question combines multiple unrelated topics.

Reject when:

- The answer is false or unsupported.

## 7. Standard Answer Review Rules

Standard answers should be reusable customer-facing replies.

Approve when:

- The tone is professional and concise.
- The answer is specific enough to help the customer.
- The answer avoids unnecessary AI-like filler.

Avoid:

- `As an AI language model...`
- Excessive apologies.
- Unverifiable guarantees.
- Robotic phrasing that does not match brand service style.

## 8. Business Rule Review Rules

Business rules describe policy or operational constraints.

Approve when:

- The rule is precise.
- The condition and action are clear.
- The rule is safe for agents to follow.

Send back when:

- The rule lacks conditions.
- The rule needs owner confirmation.

Reject when:

- The rule conflicts with known policy.

## 9. Human Handoff Rule Review Rules

Human handoff rules tell the agent when to escalate.

Approve when the rule clearly states:

- Trigger condition.
- Escalation reason.
- What the agent should ask or collect before handoff.

Examples:

- Payment risk.
- Missing tracking data.
- Legal or medical claims.
- Customer asks for account-sensitive changes.

## 10. Forbidden Answer Rule Review Rules

Forbidden answer rules define what the agent must not say.

Approve when:

- The forbidden behavior is clear.
- The replacement behavior is clear.
- The rule reduces safety, compliance, or customer-experience risk.

Examples:

- Do not promise guaranteed delivery dates unless carrier tracking confirms it.
- Do not expose private customer data.
- Do not invent refund approval.

## 11. Bad Case Correction Review Rules

Bad Case candidates are valuable because they came from failed retrieval or failed answers.

Reviewers should check:

- Does the draft actually fix the Bad Case?
- Is the answer grounded in the retrieval trace?
- Does it avoid repeating the original failure?
- Should it become FAQ, standard answer, business rule, handoff rule, or forbidden-answer rule?

Bad Case drafts still require normal review and must not auto-enter RAG.

## 12. Legacy RAG Migration Review Rules

Legacy RAG candidates may already have been used by CustomerOpsAgent, but they still need source trace and quality checks.

For trusted migration:

- Approved status may be used for fast migration.
- Reviewers should still sample and correct risky content.

For review-required migration:

- Treat as normal `pending_review`.
- Approve only after content and source metadata are safe.

## 13. Public Dataset Review Rules

Public dataset candidates are useful for flow validation, but they are not the user's real business knowledge.

Approve only when:

- The content is generic and safe.
- It does not imply false company-specific policy.
- It is clearly useful for testing or general customer-service knowledge.

Do not treat public data as verified private business policy.

## 14. Risk Level Rules

Use `low` when:

- The answer is informational and low-impact.

Use `medium` when:

- The answer involves refund, order status, address, delivery, or business process decisions.

Use `high` when:

- The answer involves payment, legal claims, medical claims, guarantees, privacy, account access, or sensitive escalation.

High-risk knowledge should be reviewed carefully and may require `needs_revision`.

## 15. Intent And Tags Rules

Intent should describe the main purpose:

- `shipping`
- `refund`
- `order_status`
- `product_info`
- `handoff`
- `prohibited_answer`
- `general`

Tags should be:

- Short.
- Lowercase when possible.
- Business-relevant.
- Not overloaded with full sentences.

Good tags:

```text
shipping, delivery, germany
```

Bad tags:

```text
this answer is probably about something related to packages
```

## 16. How To Make Answers Less AI-Like

A good answer:

- Uses direct wording.
- Gives the next action.
- Avoids empty reassurance.
- Avoids unsupported certainty.
- Keeps the customer's context.

Before:

```text
I understand your concern and I am here to assist you with your inquiry.
```

After:

```text
Please provide your order number or tracking number so we can check the shipment status.
```

## 17. How To Write Review Notes

Good review notes:

- `Approved: shipping timeline is clear and source trace is present.`
- `Needs revision: answer must include handoff condition when tracking is missing.`
- `Rejected: contains unsupported refund promise.`

Avoid:

- `ok`
- `done`
- `bad`

## 18. Good And Bad Examples

Good candidate:

```text
Question: How long does shipping take to Germany?
Answer: Shipping to Germany usually takes 7-12 business days after dispatch.
Intent: shipping
Tags: shipping, delivery, germany
Risk: low
Decision: approved
```

Bad candidate:

```text
Question: Where is my order?
Answer: It will definitely arrive tomorrow.
Problem: unsupported guarantee.
Decision: rejected or needs_revision.
```

## 19. Before And After Example

Before:

```text
Question: refund?
Answer: sure we can refund everything
```

After:

```text
Question: How do customers request a refund?
Answer: Customers should provide the order number and reason for the refund request. The agent should follow the refund policy and escalate uncertain cases to a human reviewer.
Intent: refund
Risk: medium
```

## 20. After Approval

After approval:

- The candidate can be used by `POST /api/rag/build`.
- DataHub creates or updates local RAG chunks.
- CustomerOpsAgent retrieval can return the chunk.
- Source trace remains available for debugging and Bad Case feedback.

Approval does not remove the need for future monitoring. Bad Cases can still reveal outdated or weak knowledge.
