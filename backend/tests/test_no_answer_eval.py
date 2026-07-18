"""Offline M9.4B calibration dataset and metric contracts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.answerability import AnswerabilityConfig, AnswerabilityMode


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_no_answer_eval.py"
DATASET = ROOT / "backend" / "tests" / "fixtures" / "no_answer_eval.json"
SPEC = importlib.util.spec_from_file_location("run_no_answer_eval", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_run_scoped_dataset_meets_release_metrics_without_all_rejecting() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    config = AnswerabilityConfig(mode=AnswerabilityMode.ENFORCED)
    result = MODULE.run_eval(dataset, config)
    metrics = result["metrics"]
    assert result["sample_count"] == 26
    assert result["answerable_sample_count"] > 0
    assert result["no_answer_sample_count"] > 0
    assert metrics["answerable_precision"] == 1.0
    assert metrics["answerable_recall"] == 1.0
    assert metrics["no_answer_precision"] == 1.0
    assert metrics["no_answer_recall"] == 1.0
    assert metrics["no_answer_f1"] == 1.0
    assert metrics["false_answer_rate"] == 0.0
    assert metrics["false_rejection_rate"] == 0.0
    assert metrics["archived_leakage"] == 0
    assert metrics["old_version_leakage"] == 0
    assert metrics["reason_accuracy"] == 1.0


def test_calibrated_thresholds_match_runtime_defaults() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    config = AnswerabilityConfig()
    result = MODULE.run_eval(dataset, config)
    assert result["calibrated_thresholds"] == result["thresholds"] == {
        "p1": 0.45,
        "p2": 0.55,
        "unified_normalized": 1.0,
    }


def test_dataset_declares_sources_and_modes_for_every_sample() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    for sample in dataset["samples"]:
        assert sample["retrieval_mode"] in {"p1", "p2", "unified"}
        assert isinstance(sample["allowed_sources"], list)
        assert isinstance(sample["forbidden_sources"], list)
        assert sample["expected_reason"]
