"""Unit tests for accurate P2-only eval metric semantics."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "run_p2_rag_eval.py"
SPEC = importlib.util.spec_from_file_location("run_p2_rag_eval", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P2RagEvalScriptTest(unittest.TestCase):
    def test_01_keyword_rate_is_explicit_proxy(self) -> None:
        results = [{"chunk_text": "Warranty lasts twelve months."}]
        rate, matched = MODULE.keyword_evidence_rate(
            results, ["warranty", "months", "cancellation"]
        )
        self.assertAlmostEqual(rate, 2 / 3)
        self.assertEqual(matched, ["warranty", "months"])
        self.assertEqual(MODULE.keyword_evidence_rate(results, [])[0], None)

    def test_02_candidate_recall_uses_canonical_exact_identity(self) -> None:
        results = [
            {
                "knowledge_asset_id": "knowledge_expected",
                "asset_id": "asset_expected",
                "chunk_text": "unrelated proxy terms",
            }
        ]
        recall = MODULE.candidate_recall_at_k(
            results, ["knowledge_expected"], ["asset_expected", "asset_missing"], 5
        )
        self.assertEqual(recall, 1.0)
        self.assertEqual(
            MODULE.candidate_recall_at_k(
                [
                    {
                        "knowledge_asset_id": "superseded_version",
                        "asset_id": "shared_asset",
                        "chunk_id": "old_chunk",
                    }
                ],
                ["current_version"],
                ["shared_asset"],
                5,
                ["current_chunk"],
            ),
            0.0,
        )
        self.assertEqual(
            MODULE.candidate_recall_at_k(
                [{"chunk_id": "expected_chunk", "asset_id": "asset"}],
                [],
                ["asset"],
                5,
                ["expected_chunk"],
            ),
            1.0,
        )
        self.assertIsNone(MODULE.candidate_recall_at_k(results, [], [], 5))

    def test_03_mrr_uses_first_exact_identifier_rank(self) -> None:
        results = [
            {"knowledge_asset_id": "other", "asset_id": "other"},
            {"knowledge_asset_id": "expected", "asset_id": "asset_expected"},
        ]
        self.assertEqual(
            MODULE.reciprocal_rank_at_k(results, ["expected"], [], 5), 0.5
        )
        self.assertIsNone(MODULE.reciprocal_rank_at_k(results, [], [], 5))

    def test_04_archive_leakage_and_duplicate_asset_rate(self) -> None:
        results = [
            {
                "knowledge_asset_id": "archived",
                "asset_id": "same",
                "chunk_id": "archived_chunk",
            },
            {"knowledge_asset_id": "active", "asset_id": "same", "chunk_id": "active_chunk"},
            {"knowledge_asset_id": "other", "asset_id": "different", "chunk_id": "other_chunk"},
        ]
        self.assertEqual(
            MODULE.archived_leakage(
                results, ["archived"], [], ["archived_chunk"]
            ),
            ["archived", "archived_chunk"],
        )
        self.assertAlmostEqual(MODULE.duplicate_asset_fraction(results), 1 / 3)

    def test_05_p95_uses_nearest_rank(self) -> None:
        self.assertEqual(MODULE.percentile_95([1, 2, 3, 4, 100]), 100)
        self.assertEqual(MODULE.percentile_95([]), 0.0)

    def test_06_fixture_covers_m81_categories_and_exact_metric_notes(self) -> None:
        payload = json.loads(
            (ROOT_DIR / "samples" / "p2_rag_eval_queries.json").read_text(
                encoding="utf-8"
            )
        )
        categories = {item["category"] for item in payload["queries"]}
        self.assertTrue(
            {
                "product_information",
                "warranty",
                "cancellation_policy",
                "return_policy",
                "caption_derived_knowledge",
                "ocr_derived_knowledge",
                "metadata_derived_knowledge",
                "faq",
                "archived_content",
                "replaced_version",
                "no_answer",
                "semantic_paraphrase",
            }
            <= categories
        )
        self.assertGreaterEqual(len(payload["queries"]), 12)
        self.assertIn("never reported as formal", payload["metric_notes"]["expected_terms"])
        self.assertIn("Knowledge Asset", payload["metric_notes"]["runtime_manifest"])

    def test_07_no_answer_query_is_counted_without_fake_recall(self) -> None:
        fixture = {
            "queries": [
                {
                    "id": "no_answer",
                    "query": "unknown question",
                    "expected_knowledge_asset_ids": [],
                    "expected_asset_ids": [],
                    "expected_terms": [],
                    "expect_no_hit": True,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eval.json"
            path.write_text(json.dumps(fixture), encoding="utf-8")
            envelope = {
                "success": True,
                "data": {
                    "retrieval_mode": "p2_vector_retrieval",
                    "results": [],
                    "latency_ms": 1.5,
                },
            }
            with patch.object(MODULE, "_post_json", return_value=(200, envelope)):
                summary = MODULE.run_eval(
                    base_url="http://local.test",
                    top_k=5,
                    verbose=False,
                    timeout=1,
                    eval_file=path,
                )
        self.assertEqual(summary["no_hit_count"], 1)
        self.assertIsNone(summary["candidate_recall@5"])
        self.assertIn("not recall", summary["candidate_recall_note"])
        self.assertEqual(summary["candidate_recall_query_count"], 0)
        self.assertEqual(summary["mrr_query_count"], 0)
        self.assertEqual(summary["archived_leakage_count"], 0)

    def test_08_runtime_manifest_is_strict_and_archived_ids_become_forbidden(self) -> None:
        fixture_queries = [
            {"id": "current", "query": "current version"},
            {"id": "archived", "query": "archived version"},
        ]
        manifest_payload = {
            "queries": [
                {
                    "query_id": "current",
                    "expected_knowledge_asset_ids": ["ka_v2"],
                    "expected_asset_ids": ["shared_asset"],
                    "expected_chunk_ids": ["chunk_v2"],
                    "expected_keywords": ["current"],
                    "forbidden_knowledge_asset_ids": ["ka_v1"],
                    "forbidden_chunk_ids": ["chunk_v1"],
                    "should_return_results": True,
                    "should_be_archived": False,
                },
                {
                    "query_id": "archived",
                    "expected_knowledge_asset_ids": ["ka_archived"],
                    "expected_asset_ids": ["asset_archived"],
                    "expected_chunk_ids": ["chunk_archived"],
                    "expected_keywords": [],
                    "should_return_results": False,
                    "should_be_archived": True,
                    "runtime_query": "What did archived nonce ARCHIVE-7F3A specify?",
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
            manifest = MODULE.load_expected_manifest(manifest_path)
        merged = MODULE.apply_expected_manifest(fixture_queries, manifest)
        self.assertEqual(merged[0]["expected_knowledge_asset_ids"], ["ka_v2"])
        self.assertEqual(merged[0]["forbidden_knowledge_asset_ids"], ["ka_v1"])
        self.assertEqual(merged[1]["forbidden_knowledge_asset_ids"], ["ka_archived"])
        self.assertEqual(merged[1]["forbidden_chunk_ids"], ["chunk_archived"])
        self.assertEqual(
            merged[1]["query"], "What did archived nonce ARCHIVE-7F3A specify?"
        )
        self.assertTrue(merged[1]["expect_no_hit"])

        with self.assertRaisesRegex(ValueError, "missing query ids"):
            MODULE.apply_expected_manifest(fixture_queries, {"current": manifest["current"]})

    def test_09_runtime_query_override_is_archived_only_and_length_limited(self) -> None:
        base_entry = {
            "query_id": "query",
            "expected_knowledge_asset_ids": ["ka"],
            "expected_asset_ids": [],
            "expected_chunk_ids": [],
            "expected_keywords": [],
            "should_return_results": True,
            "should_be_archived": False,
            "runtime_query": "not allowed for an active query",
        }
        invalid_entries = [
            (base_entry, "only when archived"),
            (
                {
                    **base_entry,
                    "should_return_results": False,
                    "should_be_archived": True,
                    "runtime_query": "   ",
                },
                "1 to 500 characters",
            ),
            (
                {
                    **base_entry,
                    "should_return_results": False,
                    "should_be_archived": True,
                    "runtime_query": "x" * 501,
                },
                "1 to 500 characters",
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            for entry, error in invalid_entries:
                path.write_text(json.dumps({"queries": [entry]}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, error):
                    MODULE.load_expected_manifest(path)

    def test_10_runtime_manifest_drives_version_aware_recall_and_mrr(self) -> None:
        fixture = {
            "queries": [
                {"id": "positive", "query": "warranty query"},
                {"id": "archived", "query": "archived query"},
                {"id": "no_answer", "query": "no answer query"},
            ]
        }
        manifest = {
            "queries": [
                {
                    "query_id": "positive",
                    "expected_knowledge_asset_ids": ["ka_current"],
                    "expected_asset_ids": ["shared_asset"],
                    "expected_chunk_ids": ["chunk_current"],
                    "expected_keywords": ["twelve months"],
                    "should_return_results": True,
                    "should_be_archived": False,
                },
                {
                    "query_id": "archived",
                    "expected_knowledge_asset_ids": ["ka_archived"],
                    "expected_asset_ids": ["asset_archived"],
                    "expected_chunk_ids": ["chunk_archived"],
                    "expected_keywords": [],
                    "should_return_results": False,
                    "should_be_archived": True,
                },
                {
                    "query_id": "no_answer",
                    "expected_knowledge_asset_ids": [],
                    "expected_asset_ids": [],
                    "expected_chunk_ids": [],
                    "expected_keywords": [],
                    "should_return_results": False,
                    "should_be_archived": False,
                },
            ]
        }

        def response_for_query(_url, payload, _timeout):
            results = []
            if payload["query"] == "warranty query":
                results = [
                    {
                        "knowledge_asset_id": "ka_wrong_version",
                        "asset_id": "shared_asset",
                        "chunk_id": "chunk_wrong",
                        "chunk_text": "old warranty",
                        "score": 0.9,
                    },
                    {
                        "knowledge_asset_id": "ka_current",
                        "asset_id": "shared_asset",
                        "chunk_id": "chunk_current",
                        "chunk_text": "Warranty lasts twelve months.",
                        "score": 0.8,
                    },
                ]
            return 200, {
                "success": True,
                "data": {
                    "retrieval_mode": "p2_vector_retrieval",
                    "results": results,
                    "latency_ms": 2.0,
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            eval_path = Path(directory) / "eval.json"
            manifest_path = Path(directory) / "manifest.json"
            eval_path.write_text(json.dumps(fixture), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(MODULE, "_post_json", side_effect=response_for_query):
                summary = MODULE.run_eval(
                    base_url="http://local.test",
                    top_k=5,
                    verbose=False,
                    timeout=1,
                    eval_file=eval_path,
                    expected_manifest=manifest_path,
                )

        self.assertEqual(summary["candidate_recall@5"], 1.0)
        self.assertEqual(summary["candidate_recall_query_count"], 1)
        self.assertEqual(summary["MRR"], 0.5)
        self.assertEqual(summary["mrr_query_count"], 1)
        self.assertEqual(summary["semantic_mode_count"], 3)
        self.assertEqual(summary["archived_leakage_count"], 0)
        self.assertEqual(summary["failed_queries"], [])


if __name__ == "__main__":
    unittest.main()
