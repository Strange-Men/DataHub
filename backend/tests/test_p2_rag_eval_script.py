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

    def test_02_candidate_recall_uses_exact_ids_only(self) -> None:
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
        self.assertAlmostEqual(recall, 2 / 3)
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
            {"knowledge_asset_id": "archived", "asset_id": "same"},
            {"knowledge_asset_id": "active", "asset_id": "same"},
            {"knowledge_asset_id": "other", "asset_id": "different"},
        ]
        self.assertEqual(
            MODULE.archived_leakage(results, ["archived"], []), ["archived"]
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
                "caption_derived_knowledge",
                "ocr_derived_knowledge",
                "metadata_derived_knowledge",
                "archived_content",
                "replaced_version",
                "no_answer",
                "semantic_paraphrase",
            }
            <= categories
        )
        self.assertIn("never reported as formal", payload["metric_notes"]["expected_terms"])

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
        self.assertEqual(summary["archived_leakage_count"], 0)


if __name__ == "__main__":
    unittest.main()
