"""Offline metric and contract tests for the M8.2 Unified Shadow Eval runner."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "run_unified_retrieval_eval.py"
SPEC = importlib.util.spec_from_file_location("run_unified_retrieval_eval", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

MANIFEST_SCRIPT = ROOT_DIR / "scripts" / "build_unified_eval_manifest.py"
MANIFEST_SPEC = importlib.util.spec_from_file_location(
    "build_unified_eval_manifest", MANIFEST_SCRIPT
)
assert MANIFEST_SPEC is not None and MANIFEST_SPEC.loader is not None
MANIFEST_MODULE = importlib.util.module_from_spec(MANIFEST_SPEC)
MANIFEST_SPEC.loader.exec_module(MANIFEST_MODULE)


class UnifiedRetrievalEvalTest(unittest.TestCase):
    def test_p2_acceptance_manifest_translates_to_exact_and_forbidden_labels(self) -> None:
        p2_queries = []
        required = set(MANIFEST_MODULE.QUERY_MAP.values())
        for query_id in required:
            item = {
                "query_id": query_id,
                "expected_knowledge_asset_ids": [f"ka-{query_id}"],
                "expected_chunk_ids": [f"chunk-{query_id}"],
                "expected_asset_ids": [f"asset-{query_id}"],
            }
            if query_id == "p2_archive_001":
                item["runtime_query"] = "unique archived rule"
            if query_id == "p2_version_001":
                item.update(
                    {
                        "forbidden_knowledge_asset_ids": ["ka-old"],
                        "forbidden_chunk_ids": ["chunk-old"],
                        "forbidden_asset_ids": [],
                    }
                )
            p2_queries.append(item)
        translated = MANIFEST_MODULE.build_manifest(
            {"trace_id": "trace", "queries": p2_queries}
        )
        by_id = {item["query_id"]: item for item in translated["queries"]}
        archived = by_id["unified_archived_001"]
        versioned = by_id["unified_replaced_001"]
        self.assertEqual(archived["runtime_query"], "unique archived rule")
        self.assertTrue(archived["forbidden_p2_knowledge_asset_ids"])
        self.assertEqual(versioned["forbidden_p2_knowledge_asset_ids"], ["ka-old"])
        self.assertTrue(versioned["expected_p2_knowledge_asset_ids"])

    def test_fixture_covers_all_shadow_gate_scenarios(self) -> None:
        payload = json.loads(
            (ROOT_DIR / "samples" / "unified_retrieval_eval_queries.json").read_text(
                encoding="utf-8"
            )
        )
        categories = {query["category"] for query in payload["queries"]}
        self.assertGreaterEqual(len(payload["queries"]), 10)
        self.assertTrue(
            {
                "p1_only",
                "p2_only",
                "mixed",
                "archived",
                "replaced_version",
                "conflict",
                "no_answer",
                "p1_branch_failure",
                "p2_branch_failure",
                "duplicate_asset",
                "latency_comparison",
            }
            <= categories
        )
        self.assertIn("never reported as formal recall", payload["metric_notes"]["expected_terms"])

    def test_keyword_evidence_is_an_explicit_proxy(self) -> None:
        rate, matched = MODULE.keyword_evidence_rate(
            [{"chunk_text": "Warranty applies for twelve months."}],
            ["warranty", "months", "refund"],
        )
        self.assertAlmostEqual(rate, 2 / 3)
        self.assertEqual(matched, ["warranty", "months"])
        self.assertIsNone(MODULE.keyword_evidence_rate([], [])[0])

    def test_exact_recall_uses_route_aware_canonical_ids(self) -> None:
        labels = {
            "expected_p1_candidate_ids": ["p1-a"],
            "expected_p1_chunk_ids": ["ignored-p1-chunk-grain"],
            "expected_p2_knowledge_asset_ids": ["p2-a"],
            "expected_p2_chunk_ids": ["ignored-p2-chunk-grain"],
            "expected_p2_asset_ids": ["ignored-p2-asset-grain"],
        }
        results = [
            {
                "source_index": "p1_rag_embeddings",
                "candidate_id": "p1-a",
                "chunk_id": "p1-chunk",
            },
            {
                "source_index": "p2_knowledge_embeddings",
                "knowledge_asset_id": "p2-a",
                "chunk_id": "p2-chunk",
                "asset_id": "asset-a",
            },
        ]
        self.assertEqual(MODULE.exact_recall_at_k(results, labels, 5), 1.0)
        self.assertEqual(MODULE.exact_reciprocal_rank_at_k(results, labels, 5), 1.0)
        self.assertEqual(MODULE.exact_recall_at_k(results[:1], labels, 5), 0.5)
        self.assertIsNone(MODULE.exact_recall_at_k(results, {}, 5))

    def test_archive_leakage_and_duplicate_assets_are_exact(self) -> None:
        labels = {
            "forbidden_p2_knowledge_asset_ids": ["archived"],
            "forbidden_p2_chunk_ids": ["old-chunk"],
        }
        results = [
            {
                "source_type": "p2",
                "knowledge_asset_id": "archived",
                "chunk_id": "old-chunk",
                "asset_id": "same",
            },
            {
                "source_type": "p2",
                "knowledge_asset_id": "active",
                "chunk_id": "new-chunk",
                "asset_id": "same",
            },
            {"source_type": "p1", "candidate_id": "candidate"},
        ]
        self.assertEqual(
            MODULE.archived_leakage(results, labels),
            ["p2:chunk:old-chunk", "p2:knowledge_asset:archived"],
        )
        self.assertEqual(MODULE.duplicate_asset_fraction(results), 0.5)

    def test_runtime_manifest_is_optional_partial_and_strict(self) -> None:
        manifest_payload = {
            "queries": [
                {
                    "query_id": "mixed",
                    "expected_p1_candidate_ids": ["p1-a"],
                    "expected_p2_knowledge_asset_ids": ["p2-a"],
                    "forbidden_p2_knowledge_asset_ids": ["p2-old"],
                    "expected_keywords": ["warranty", "material"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest_payload), encoding="utf-8")
            manifest = MODULE.load_expected_manifest(path)
        merged = MODULE.apply_expected_manifest(
            [
                {"id": "p1", "query": "p1"},
                {"id": "mixed", "query": "mixed", "expected_terms": []},
            ],
            manifest,
        )
        self.assertNotIn("expected_p1_candidate_ids", merged[0])
        self.assertEqual(merged[1]["expected_p1_candidate_ids"], ["p1-a"])
        self.assertEqual(merged[1]["expected_terms"], ["warranty", "material"])
        with self.assertRaisesRegex(ValueError, "unknown query ids"):
            MODULE.apply_expected_manifest([{"id": "known"}], {"unknown": {}})

    def test_run_eval_compares_control_candidate_and_propagates_request_modes(self) -> None:
        fixture = {
            "queries": [
                {
                    "id": "mixed",
                    "query": "mixed query",
                    "sources": "all",
                    "fusion_enabled": True,
                    "shadow_mode": True,
                    "expected_sources": ["p1", "p2"],
                    "expected_terms": ["alpha"],
                    "expected_p1_candidate_ids": ["p1-a"],
                    "expected_p2_knowledge_asset_ids": ["p2-a"],
                },
                {
                    "id": "archive",
                    "query": "archive query",
                    "sources": "all",
                    "fusion_enabled": True,
                    "shadow_mode": True,
                    "expected_sources": [],
                    "expected_terms": [],
                    "forbidden_p2_knowledge_asset_ids": ["p2-old"],
                },
                {
                    "id": "no-answer",
                    "query": "unknown query",
                    "sources": "p1",
                    "fusion_enabled": False,
                    "shadow_mode": True,
                    "expected_sources": [],
                    "expected_terms": [],
                    "expect_no_hit": True,
                },
            ]
        }
        requests: list[dict[str, object]] = []

        def response(_url, payload, _timeout):
            requests.append(dict(payload))
            if payload["query"] == "mixed query":
                control = [
                    {
                        "source_index": "p1_rag_embeddings",
                        "candidate_id": "p1-a",
                        "chunk_id": "p1-c",
                        "evidence_text": "alpha support",
                    }
                ]
                candidate = [
                    *control,
                    {
                        "source_index": "p2_knowledge_embeddings",
                        "knowledge_asset_id": "p2-a",
                        "chunk_id": "p2-c",
                        "asset_id": "asset-a",
                        "evidence_text": "alpha material",
                    },
                ]
                latency = {"total_ms": 10, "p1_ms": 3, "p2_ms": 4, "fusion_ms": 1}
                fallback = {"used": False}
            elif payload["query"] == "archive query":
                control = []
                candidate = []
                latency = {"total_ms": 20}
                fallback = {"used": True, "reason": "p2_timeout"}
            else:
                control = []
                candidate = []
                latency = {"total_ms": 100}
                fallback = {"used": False}
            return 200, {
                "success": True,
                "data": {
                    "retrieval_id": "unified-test",
                    "retrieval_mode": "shadow_control",
                    "control_mode": "customerops_vector_retrieval",
                    "candidate_mode": "p1_p2_rrf",
                    "results": control,
                    "control_results": control,
                    "candidate_results": candidate,
                    "source_modes": {
                        "p1": {"status": "ok"},
                        "p2": {"status": "ok"},
                    },
                    "shadow_comparison": {},
                    "latency_ms": {
                        "total": latency["total_ms"],
                        "p1": latency.get("p1_ms"),
                        "p2": latency.get("p2_ms"),
                        "fusion": latency.get("fusion_ms", 0),
                    },
                    "fallback_used": fallback["used"],
                    "fallback_reason": fallback.get("reason"),
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with patch.object(MODULE, "_post_json", side_effect=response):
                with redirect_stdout(io.StringIO()):
                    summary = MODULE.run_eval(
                        base_url="http://local.test",
                        top_k=5,
                        timeout=1,
                        verbose=False,
                        eval_file=path,
                    )

        self.assertEqual(requests[0]["sources"], "all")
        self.assertTrue(requests[0]["shadow_mode"])
        self.assertTrue(requests[0]["fusion_enabled"])
        self.assertEqual(summary["control_exact_recall@5"], 0.5)
        self.assertEqual(summary["candidate_exact_recall@5"], 1.0)
        self.assertTrue(summary["candidate_not_below_control"])
        self.assertEqual(summary["source_coverage_rate"], 1.0)
        self.assertEqual(summary["archived_leakage_count"], 0)
        self.assertEqual(summary["archived_labeled_query_count"], 1)
        self.assertEqual(summary["duplicate_asset_rate"], 0.0)
        self.assertEqual(summary["fallback_count"], 1)
        self.assertEqual(summary["fallback_rate"], round(1 / 3, 4))
        self.assertEqual(summary["fallback_reasons"], {"p2_timeout": 1})
        self.assertEqual(summary["p50_latency_ms"], 20.0)
        self.assertEqual(summary["p95_latency_ms"], 100.0)
        self.assertEqual(summary["shadow_response_count"], 3)
        self.assertEqual(summary["failed_queries"], [])

    def test_keyword_proxy_is_not_promoted_to_exact_recall(self) -> None:
        fixture = {
            "queries": [
                {
                    "id": "proxy-only",
                    "query": "proxy",
                    "sources": "all",
                    "shadow_mode": True,
                    "expected_sources": ["p1"],
                    "expected_terms": ["answer"],
                }
            ]
        }
        envelope = {
            "success": True,
            "data": {
                "retrieval_id": "id",
                "retrieval_mode": "shadow_control",
                "control_mode": "customerops_vector_retrieval",
                "candidate_mode": "p1_p2_rrf",
                "results": [{"source_type": "p1", "candidate_id": "p1", "evidence_text": "answer"}],
                "control_results": [{"source_type": "p1", "candidate_id": "p1", "evidence_text": "answer"}],
                "candidate_results": [{"source_type": "p1", "candidate_id": "p1", "evidence_text": "answer"}],
                "source_modes": {"p1": {"status": "ok"}},
                "shadow_comparison": {},
                "latency": {"total_ms": 1},
                "fallback": {"used": False},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with patch.object(MODULE, "_post_json", return_value=(200, envelope)):
                with redirect_stdout(io.StringIO()):
                    summary = MODULE.run_eval(
                        base_url="http://local.test",
                        top_k=5,
                        timeout=1,
                        verbose=False,
                        eval_file=path,
                    )
        self.assertEqual(summary["candidate_keyword_hit_rate@5"], 1.0)
        self.assertIsNone(summary["candidate_exact_recall@5"])
        self.assertIsNone(summary["candidate_MRR"])
        self.assertIn("not recall", summary["exact_recall_note"])

    def test_candidate_regression_is_reported_as_failure(self) -> None:
        fixture = {
            "queries": [
                {
                    "id": "regression",
                    "query": "answer",
                    "sources": "all",
                    "shadow_mode": True,
                    "expected_terms": ["answer"],
                    "expected_sources": [],
                }
            ]
        }
        envelope = {
            "success": True,
            "data": {
                "retrieval_id": "id",
                "retrieval_mode": "shadow_control",
                "control_mode": "customerops_vector_retrieval",
                "candidate_mode": "p1_p2_rrf",
                "results": [{"source_type": "p1", "chunk_text": "answer"}],
                "control_results": [{"source_type": "p1", "chunk_text": "answer"}],
                "candidate_results": [],
                "source_modes": {
                    "p1": {"status": "ok"},
                    "p2": {"status": "ok"},
                },
                "shadow_comparison": {},
                "latency": {"total_ms": 1},
                "fallback": {"used": False},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with patch.object(MODULE, "_post_json", return_value=(200, envelope)):
                with redirect_stdout(io.StringIO()):
                    summary = MODULE.run_eval(
                        base_url="http://local.test",
                        top_k=5,
                        timeout=1,
                        verbose=False,
                        eval_file=path,
                    )
        self.assertFalse(summary["candidate_not_below_control"])
        self.assertEqual(
            summary["failed_queries"],
            [{"query_id": "regression", "reason": "candidate_keyword_below_control"}],
        )


if __name__ == "__main__":
    unittest.main()
