"""Run-scoped offline calibration and evaluation for the M9.4B abstention gate."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.answerability import (  # noqa: E402
    AnswerabilityConfig,
    AnswerabilityEvidence,
    AnswerabilityReason,
    evaluate_answerability,
)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _evidence(sample: dict[str, Any], config: AnswerabilityConfig) -> list[AnswerabilityEvidence]:
    scope = sample["retrieval_mode"]
    evidence: list[AnswerabilityEvidence] = []
    for raw in sample.get("evidence", []):
        source = raw["source"]
        score = float(raw["score"])
        if scope == "unified":
            score = config.normalize_unified_score(source, score)
        evidence.append(
            AnswerabilityEvidence(
                score=score,
                source=source,
                valid=bool(raw.get("valid", True)),
                conflict_key=raw.get("conflict_key"),
                claim_value=raw.get("claim_value"),
            )
        )
    return evidence


def _best_threshold(samples: list[dict[str, Any]], scope: str, config: AnswerabilityConfig) -> float:
    rows: list[tuple[float, bool]] = []
    for sample in samples:
        if sample["retrieval_mode"] != scope or sample.get("retrieval_unavailable"):
            continue
        if sample["expected_reason"] not in {"ANSWERABLE", "LOW_RELEVANCE"}:
            continue
        valid = [item for item in sample.get("evidence", []) if item.get("valid", True)]
        if not valid:
            continue
        if scope == "unified":
            score = max(
                config.normalize_unified_score(item["source"], float(item["score"]))
                for item in valid
            )
        else:
            score = max(float(item["score"]) for item in valid)
        rows.append((score, bool(sample["expected_answerable"])))

    best: tuple[float, float] | None = None
    for index in range(101):
        threshold = index / 100
        correct = sum((score >= threshold) == expected for score, expected in rows)
        accuracy = _ratio(correct, len(rows))
        candidate = (accuracy, -threshold)
        if best is None or candidate > best:
            best = candidate
    return round(-best[1], 2) if best else 0.0


def run_eval(dataset: dict[str, Any], config: AnswerabilityConfig) -> dict[str, Any]:
    samples = list(dataset["samples"])
    rows: list[dict[str, Any]] = []
    tp = fp = tn = fn = 0
    reason_hits = 0
    archived_leakage = old_version_leakage = 0
    threshold_neighborhood: dict[str, dict[str, int]] = {
        scope: {"sample_count": 0, "below_threshold": 0, "at_or_above_threshold": 0, "classification_errors": 0}
        for scope in ("p1", "p2", "unified")
    }

    for sample in samples:
        decision = evaluate_answerability(
            query=sample["query"],
            evidence=_evidence(sample, config),
            scope=sample["retrieval_mode"],
            config=config,
            filtered_candidate_count=int(sample.get("filtered_candidate_count", 0)),
            retrieval_unavailable=bool(sample.get("retrieval_unavailable", False)),
        )
        expected = bool(sample["expected_answerable"])
        predicted = decision.answerable
        tp += int(predicted and expected)
        fp += int(predicted and not expected)
        tn += int(not predicted and not expected)
        fn += int(not predicted and expected)
        reason_hits += int(decision.no_answer_reason.value == sample["expected_reason"])
        if (
            decision.decision_score is not None
            and decision.decision_threshold is not None
            and abs(decision.decision_score - decision.decision_threshold) <= 0.05
        ):
            bucket = threshold_neighborhood[sample["retrieval_mode"]]
            bucket["sample_count"] += 1
            bucket[
                "at_or_above_threshold"
                if decision.decision_score >= decision.decision_threshold
                else "below_threshold"
            ] += 1
            bucket["classification_errors"] += int(predicted != expected)
        forbidden = set(sample.get("forbidden_sources", []))
        if predicted and any(value.startswith("archived-") for value in forbidden):
            archived_leakage += 1
        if predicted and any(value.startswith("old-version-") for value in forbidden):
            old_version_leakage += 1
        rows.append(
            {
                "query": sample["query"],
                "retrieval_mode": sample["retrieval_mode"],
                "expected_answerable": expected,
                "expected_reason": sample["expected_reason"],
                "actual": decision.model_dump(mode="json"),
                "passed": predicted == expected
                and decision.no_answer_reason.value == sample["expected_reason"],
            }
        )

    answerable_precision = _ratio(tp, tp + fp)
    answerable_recall = _ratio(tp, tp + fn)
    no_answer_precision = _ratio(tn, tn + fn)
    no_answer_recall = _ratio(tn, tn + fp)
    no_answer_f1 = (
        round(2 * no_answer_precision * no_answer_recall / (no_answer_precision + no_answer_recall), 4)
        if no_answer_precision + no_answer_recall
        else 0.0
    )
    return {
        "dataset_version": dataset["dataset_version"],
        "sample_count": len(samples),
        "answerable_sample_count": sum(bool(item["expected_answerable"]) for item in samples),
        "no_answer_sample_count": sum(not bool(item["expected_answerable"]) for item in samples),
        "thresholds": {
            "p1": config.p1_min_score,
            "p2": config.p2_min_score,
            "unified_normalized": config.unified_min_score,
        },
        "calibrated_thresholds": {
            "p1": _best_threshold(samples, "p1", config),
            "p2": _best_threshold(samples, "p2", config),
            "unified_normalized": _best_threshold(samples, "unified", config),
        },
        "metrics": {
            "answerable_precision": answerable_precision,
            "answerable_recall": answerable_recall,
            "no_answer_precision": no_answer_precision,
            "no_answer_recall": no_answer_recall,
            "no_answer_f1": no_answer_f1,
            "false_answer_rate": _ratio(fp, fp + tn),
            "false_rejection_rate": _ratio(fn, fn + tp),
            "archived_leakage": archived_leakage,
            "old_version_leakage": old_version_leakage,
            "reason_accuracy": _ratio(reason_hits, len(samples)),
        },
        "threshold_neighborhood": threshold_neighborhood,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "backend" / "tests" / "fixtures" / "no_answer_eval.json",
    )
    parser.add_argument("--run-id", default=f"no-answer-{uuid4().hex[:12]}")
    parser.add_argument("--namespace")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="Evaluate fixed thresholds on an independent set without recalibrating them.",
    )
    args = parser.parse_args()

    namespace = args.namespace or f"datahub-eval:{args.run_id}"
    if not namespace.startswith("datahub-eval:"):
        raise SystemExit("namespace must use the isolated datahub-eval: prefix")
    output = args.output or ROOT / ".local-data" / "no-answer-eval" / f"{args.run_id}.json"
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    config = AnswerabilityConfig.from_environment()
    summary = run_eval(dataset, config)
    summary.update(
        {
            "run_id": args.run_id,
            "namespace": namespace,
            "dataset_path": str(args.dataset.resolve()),
            "created_at": datetime.now(UTC).isoformat(),
            "evaluation_role": "holdout" if args.holdout else "calibration",
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, ensure_ascii=False, indent=2))

    metrics = summary["metrics"]
    thresholds_match = summary["thresholds"] == summary["calibrated_thresholds"]
    passed = (
        metrics["answerable_recall"] >= 0.95
        and metrics["no_answer_precision"] >= 0.95
        and metrics["false_answer_rate"] <= 0.05
        and metrics["archived_leakage"] == 0
        and metrics["old_version_leakage"] == 0
        and metrics["reason_accuracy"] >= 0.95
        and (args.holdout or thresholds_match)
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
