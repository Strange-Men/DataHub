"""M9.5 holdout integrity checks; metrics run only in the closure command."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = ROOT / "backend" / "tests" / "fixtures" / "no_answer_eval.json"
CHALLENGE = ROOT / "backend" / "tests" / "fixtures" / "no_answer_challenge.json"


def _queries(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(sample["query"]) for sample in payload["samples"]}


def test_holdout_is_balanced_independent_and_run_scope_safe() -> None:
    payload = json.loads(CHALLENGE.read_text(encoding="utf-8"))
    samples = payload["samples"]
    assert payload["dataset_version"] == "m9.5-holdout-v1"
    assert len(samples) == 48
    assert sum(bool(item["expected_answerable"]) for item in samples) == 24
    assert _queries(CALIBRATION).isdisjoint(_queries(CHALLENGE))
    for sample in samples:
        assert sample["retrieval_mode"] in {"p1", "p2", "unified"}
        assert isinstance(sample["allowed_sources"], list)
        assert isinstance(sample["forbidden_sources"], list)
