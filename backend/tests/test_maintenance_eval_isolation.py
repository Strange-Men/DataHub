"""M9.1 run-scope isolation and non-destructive cleanup gates."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from scripts.eval_run_scope import (  # noqa: E402
    collect_p2_scope_ids,
    filter_p2_results,
    load_run_scope,
    make_run_scope,
)
from scripts.run_p1_pipeline_harness import scoped_import_payload  # noqa: E402
import app.asset_service as asset_service  # noqa: E402
from app.p2_retrieval_schemas import P2RetrievalRequest  # noqa: E402
from app.unified_retrieval_schemas import UnifiedRetrievalRequest  # noqa: E402


def _load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"maintenance_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


p2_eval = _load_script("run_p2_rag_eval")
unified_eval = _load_script("run_unified_retrieval_eval")
acceptance = _load_script("run_p2_local_acceptance")
unified_manifest = _load_script("build_unified_eval_manifest")


def test_run_scope_is_strict_and_filters_only_old_p2_rows() -> None:
    scope = make_run_scope(
        "p2-local-test-scope-001",
        trace_id="p2-local-test-scope-001",
        creator="test",
    )
    assert load_run_scope({"run_scope": scope}) == scope
    ids = collect_p2_scope_ids(
        [{"expected_p2_knowledge_asset_ids": ["ka-current"]}]
    )
    results = [
        {"source_index": "p1", "candidate_id": "candidate"},
        {"source_index": "p2", "knowledge_asset_id": "ka-old"},
        {"source_index": "p2", "knowledge_asset_id": "ka-current"},
    ]
    assert filter_p2_results(results, ids, keep_non_p2=True) == [results[0], results[2]]
    with pytest.raises(ValueError):
        load_run_scope(
            {"run_scope": {**scope, "namespace": "datahub-eval:another-run"}}
        )


def test_backend_eval_scope_contract_is_additive_and_strict() -> None:
    scope = "datahub-eval:p2-local-contract-001"
    assert asset_service.validate_eval_run_scope(scope) == scope
    assert P2RetrievalRequest(query="q", evaluation_scope=scope).evaluation_scope == scope
    assert (
        UnifiedRetrievalRequest(query="q", evaluation_scope=scope).evaluation_scope
        == scope
    )
    with pytest.raises(asset_service.AssetValidationFailure) as invalid_scope:
        asset_service.validate_eval_run_scope("production-corpus")
    assert getattr(invalid_scope.value, "code", None) == "EVAL_RUN_SCOPE_INVALID"
    with pytest.raises(ValueError):
        P2RetrievalRequest(query="q", evaluation_scope="production-corpus")


def test_p1_harness_generates_unique_run_identifiers() -> None:
    first = scoped_import_payload("p1-harness-20260716-000001-aaaaaa")
    second = scoped_import_payload("p1-harness-20260716-000002-bbbbbb")
    assert first["source_name"] != second["source_name"]
    assert first["conversations"][0]["conversation_id"] != second["conversations"][0]["conversation_id"]
    assert first["conversations"][0]["messages"][0]["message_id"] != second["conversations"][0]["messages"][0]["message_id"]
    assert "refund" in json.dumps(first).lower()


def test_p2_eval_uses_larger_pool_and_current_run_only(tmp_path: Path, monkeypatch) -> None:
    eval_file = tmp_path / "eval.json"
    manifest = tmp_path / "manifest.json"
    eval_file.write_text(
        json.dumps({"queries": [{"id": "q", "query": "answer"}]}),
        encoding="utf-8",
    )
    scope = make_run_scope("p2-local-isolated-001", trace_id="trace", creator="test")
    manifest.write_text(
        json.dumps(
            {
                "run_scope": scope,
                "queries": [
                    {
                        "query_id": "q",
                        "expected_knowledge_asset_ids": ["ka-current"],
                        "expected_asset_ids": ["asset-current"],
                        "expected_chunk_ids": ["chunk-current"],
                        "forbidden_knowledge_asset_ids": [],
                        "forbidden_asset_ids": [],
                        "forbidden_chunk_ids": [],
                        "expected_keywords": ["answer"],
                        "should_return_results": True,
                        "should_be_archived": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_post(_url, payload, _timeout):
        assert payload["top_k"] == 20
        return 200, {
            "success": True,
            "data": {
                "retrieval_mode": "p2_vector_retrieval",
                "results": [
                    *[
                        {
                            "knowledge_asset_id": f"ka-old-{index}",
                            "asset_id": f"asset-old-{index}",
                            "chunk_id": f"chunk-old-{index}",
                            "chunk_text": "answer",
                            "score": 0.9,
                        }
                        for index in range(5)
                    ],
                    {
                        "knowledge_asset_id": "ka-current",
                        "asset_id": "asset-current",
                        "chunk_id": "chunk-current",
                        "chunk_text": "answer",
                        "score": 0.8,
                    },
                ],
                "latency_ms": 1,
            },
        }

    monkeypatch.setattr(p2_eval, "_post_json", fake_post)
    with redirect_stdout(io.StringIO()):
        summary = p2_eval.run_eval(
            base_url="http://test",
            top_k=5,
            verbose=False,
            timeout=1,
            eval_file=eval_file,
            expected_manifest=manifest,
        )
    assert summary["candidate_recall@5"] == 1.0
    assert summary["MRR"] == 1.0
    assert summary["run_scope_isolation_enabled"] is True
    assert summary["scope_filtered_result_count"] == 5


def test_unified_eval_filters_historical_p2_but_keeps_p1_control(
    tmp_path: Path, monkeypatch
) -> None:
    eval_file = tmp_path / "eval.json"
    manifest = tmp_path / "manifest.json"
    eval_file.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "id": "q",
                        "query": "answer",
                        "sources": "all",
                        "shadow_mode": True,
                        "expected_sources": ["p1", "p2"],
                        "expected_terms": ["answer"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    scope = make_run_scope("p2-local-unified-001", trace_id="trace", creator="test")
    manifest.write_text(
        json.dumps(
            {
                "run_scope": scope,
                "queries": [
                    {
                        "query_id": "q",
                        "expected_p2_knowledge_asset_ids": ["ka-current"],
                        "expected_p2_chunk_ids": ["chunk-current"],
                        "expected_p2_asset_ids": ["asset-current"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    control = [{"source_index": "p1", "candidate_id": "p1", "evidence_text": "answer"}]
    candidate = [
        *[
            {
                "source_index": "p2",
                "knowledge_asset_id": f"ka-old-{index}",
                "asset_id": f"asset-old-{index}",
                "chunk_id": f"chunk-old-{index}",
                "evidence_text": "answer",
            }
            for index in range(5)
        ],
        control[0],
        {
            "source_index": "p2",
            "knowledge_asset_id": "ka-current",
            "asset_id": "asset-current",
            "chunk_id": "chunk-current",
            "evidence_text": "answer",
        },
    ]

    def fake_post(_url, payload, _timeout):
        assert payload["top_k"] == 20
        return 200, {
            "success": True,
            "data": {
                "retrieval_mode": "shadow_control",
                "control_mode": "customerops_vector_retrieval",
                "candidate_mode": "p1_p2_rrf",
                "results": control,
                "control_results": control,
                "candidate_results": candidate,
                "source_modes": {"p1": {"status": "ok"}, "p2": {"status": "ok"}},
                "shadow_comparison": {},
                "latency": {"total_ms": 1},
                "fallback": {"used": False},
            },
        }

    monkeypatch.setattr(unified_eval, "_post_json", fake_post)
    with redirect_stdout(io.StringIO()):
        summary = unified_eval.run_eval(
            base_url="http://test",
            top_k=5,
            timeout=1,
            verbose=False,
            eval_file=eval_file,
            expected_manifest=manifest,
        )
    assert summary["candidate_exact_recall@5"] == 1.0
    assert summary["candidate_MRR"] == 0.5
    assert summary["candidate_not_below_control"] is True
    assert summary["scope_filtered_result_count"] == 5


def test_unified_manifest_propagates_validated_run_scope() -> None:
    queries = []
    for p2_id in set(unified_manifest.QUERY_MAP.values()):
        queries.append(
            {
                "query_id": p2_id,
                "expected_knowledge_asset_ids": [f"ka-{p2_id}"],
                "expected_asset_ids": [f"asset-{p2_id}"],
                "expected_chunk_ids": [f"chunk-{p2_id}"],
                "forbidden_knowledge_asset_ids": [],
                "forbidden_asset_ids": [],
                "forbidden_chunk_ids": [],
            }
        )
    source = {
        "trace_id": "trace",
        "run_scope": make_run_scope(
            "p2-local-manifest-001", trace_id="trace", creator="test"
        ),
        "queries": queries,
    }
    built = unified_manifest.build_manifest(source)
    assert built["run_scope"] == source["run_scope"]
    assert built["p2_scope_ids"]


class _CleanupClient:
    def __init__(self) -> None:
        self.archived: list[str] = []

    def get(self, path: str):
        return {"success": True, "data": {"id": path.rsplit("/", 1)[-1], "status": "active"}}

    def post(self, path: str, payload=None):
        identifier = path.split("/")[3]
        self.archived.append(identifier)
        return {"success": True, "data": {"id": identifier, "status": "archived"}}


def test_cleanup_requires_explicit_test_scope_and_only_archives_listed_ids(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"queries": []}), encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError):
        acceptance.cleanup_manifest_corpus(client=_CleanupClient(), manifest_path=invalid)

    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "run_scope": make_run_scope(
                    "p2-local-cleanup-001",
                    trace_id="trace",
                    creator="run_p2_local_acceptance",
                ),
                "created_resources": {
                    "cleanup_knowledge_asset_ids": ["ka-one", "ka-two", "ka-one"]
                },
            }
        ),
        encoding="utf-8",
    )
    client = _CleanupClient()
    summary = acceptance.cleanup_manifest_corpus(client=client, manifest_path=valid)
    assert client.archived == ["ka-one", "ka-two"]
    assert summary["deleted_records"] == 0
    assert summary["cleanup_mode"] == "logical_archive_only"
