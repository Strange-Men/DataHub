"""Metric/contract tests for the M8.3 public-API smoke runner."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "run_customerops_unified_opt_in_smoke.py"
SPEC = importlib.util.spec_from_file_location("customerops_opt_in_smoke", SCRIPT_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def _fixtures(tmp_path: Path) -> tuple[Path, Path]:
    sample = tmp_path / "sample.json"
    manifest = tmp_path / "manifest.json"
    sample.write_text(
        json.dumps(
            {
                "queries": [
                    {"id": "active", "query": "active governed answer"},
                    {"id": "archived", "query": "archived governed answer"},
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query_id": "active",
                        "expected_knowledge_asset_ids": ["knowledge-active"],
                        "expected_asset_ids": ["asset-active"],
                        "expected_chunk_ids": ["chunk-active"],
                        "should_return_results": True,
                        "should_be_archived": False,
                    },
                    {
                        "query_id": "archived",
                        "runtime_query": "unique archived answer",
                        "expected_knowledge_asset_ids": ["knowledge-archived"],
                        "expected_asset_ids": ["asset-archived"],
                        "expected_chunk_ids": ["chunk-archived"],
                        "should_return_results": False,
                        "should_be_archived": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return sample, manifest


def _args(sample: Path, manifest: Path, *, active: bool) -> argparse.Namespace:
    return argparse.Namespace(
        base_url="http://test",
        top_k=5,
        timeout=1.0,
        expected_manifest=manifest,
        sample_file=sample,
        expect_opt_in_active=active,
        verbose=False,
    )


def _envelope(data: dict[str, object]) -> dict[str, object]:
    return {"success": True, "data": data, "requestId": "req-test"}


def test_active_smoke_requires_both_sources_and_zero_archive_leakage(
    tmp_path: Path, monkeypatch
) -> None:
    sample, manifest = _fixtures(tmp_path)

    def fake_post(_base: str, path: str, payload: dict[str, object], _timeout: float):
        if path == "/api/customer-ops-agent/retrieve":
            return _envelope({"retrieval_mode": "customerops_vector_retrieval"})
        if payload.get("retrieval_strategy") != "unified":
            return _envelope(
                {
                    "actual_retrieval_strategy": "p1",
                    "retrieval_mode": "customerops_vector_retrieval",
                }
            )
        if "archived" in str(payload.get("query")):
            results = [
                {
                    "source_index": "p1",
                    "chunk_id": "p1-safe",
                    "source_trace": {"chunk_id": "p1-safe"},
                }
            ]
        else:
            results = [
                {
                    "source_index": "p1",
                    "chunk_id": "p1-safe",
                    "source_trace": {"chunk_id": "p1-safe"},
                },
                {
                    "source_index": "p2",
                    "knowledge_asset_id": "knowledge-active",
                    "asset_id": "asset-active",
                    "chunk_id": "chunk-active",
                    "source_trace": {"asset_id": "asset-active"},
                },
            ]
        return _envelope(
            {
                "actual_retrieval_strategy": "unified",
                "retrieval_mode": "customerops_unified_retrieval",
                "fallback_used": False,
                "fallback_reason": None,
                "results": results,
            }
        )

    monkeypatch.setattr(smoke, "_post", fake_post)
    summary = smoke.run(_args(sample, manifest, active=True))
    assert summary["passed"] is True
    assert summary["archived_leakage_count"] == 0
    assert summary["opt_in_source_indexes"] == ["p1", "p2"]


def test_disabled_smoke_requires_observable_p1_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    sample, manifest = _fixtures(tmp_path)

    def fake_post(_base: str, path: str, payload: dict[str, object], _timeout: float):
        if path == "/api/customer-ops-agent/retrieve":
            return _envelope({"retrieval_mode": "customerops_vector_retrieval"})
        if payload.get("retrieval_strategy") == "unified":
            return _envelope(
                {
                    "actual_retrieval_strategy": "p1",
                    "retrieval_mode": "customerops_vector_retrieval",
                    "fallback_used": True,
                    "fallback_reason": "customerops_unified_retrieval_disabled",
                    "results": [],
                }
            )
        return _envelope(
            {
                "actual_retrieval_strategy": "p1",
                "retrieval_mode": "customerops_vector_retrieval",
                "results": [],
            }
        )

    monkeypatch.setattr(smoke, "_post", fake_post)
    summary = smoke.run(_args(sample, manifest, active=False))
    assert summary["passed"] is True
    assert summary["opt_in_actual_strategy"] == "p1"
    assert summary["opt_in_fallback_used"] is True
