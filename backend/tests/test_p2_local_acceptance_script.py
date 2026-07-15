"""Tests for the API-only P2 local acceptance orchestrator."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "run_p2_local_acceptance.py"
SPEC = importlib.util.spec_from_file_location("run_p2_local_acceptance", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def envelope(data: dict[str, object]) -> dict[str, object]:
    return {"success": True, "data": data, "requestId": "fake-request"}


class FakePublicApiClient:
    """Stateful public-contract fake; it exposes no direct persistence shortcut."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.counter = 0
        self.extractions: dict[str, dict[str, object]] = {}
        self.reviews: dict[str, dict[str, object]] = {}
        self.snapshots: dict[str, dict[str, object]] = {}
        self.knowledge: dict[str, dict[str, object]] = {}
        self.indexes: dict[str, dict[str, object]] = {}
        self.embeddings: dict[str, dict[str, object]] = {}
        self.serving: list[str] = []

    def _id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}_{self.counter}"

    def upload_asset(self, file_name: str, content: bytes) -> dict[str, object]:
        self.calls.append(("POST", "/api/assets/upload"))
        assert file_name.endswith(".png")
        assert content.startswith(b"\x89PNG\r\n\x1a\n")
        return envelope({"id": self._id("asset")})

    def post(self, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append(("POST", path))
        payload = payload or {}
        if path.endswith("/extract"):
            asset_id = path.split("/")[3]
            job_id = self._id("job")
            extraction_id = self._id("extraction")
            extraction = {
                "id": extraction_id,
                "job_id": job_id,
                "asset_id": asset_id,
                "extract_type": payload["extract_type"],
            }
            self.extractions[extraction_id] = extraction
            return envelope(
                {
                    "job": {"id": job_id, "status": "success"},
                    "result": extraction,
                }
            )
        if path.endswith("/reviews"):
            asset_id = path.split("/")[3]
            review_id = self._id("review")
            review = {
                "id": review_id,
                "asset_id": asset_id,
                "extraction_id": payload["extraction_id"],
            }
            self.reviews[review_id] = review
            return envelope(review)
        if path.startswith("/api/snapshots/") and path.endswith("/publish"):
            snapshot_id = path.split("/")[3]
            snapshot = self.snapshots[snapshot_id]
            extraction = self.extractions[str(snapshot["extraction_id"])]
            asset_id = str(extraction["asset_id"])
            extract_type = str(extraction["extract_type"])
            for knowledge_id, row in self.knowledge.items():
                if (
                    row["asset_id"] == asset_id
                    and row["content_type"] == extract_type
                    and row["status"] == "active"
                ):
                    row["status"] = "archived"
                    self.serving = [item for item in self.serving if item != knowledge_id]
                    for index in self.indexes.values():
                        if index["knowledge_asset_id"] == knowledge_id:
                            index["status"] = "archived"
                            index["sync_state"] = "archived"
            knowledge_id = self._id("knowledge")
            knowledge = {
                "id": knowledge_id,
                "asset_id": asset_id,
                "content_type": extract_type,
                "status": "active",
                "snapshot_id": snapshot_id,
                "extraction_id": extraction["id"],
            }
            self.knowledge[knowledge_id] = knowledge
            return envelope({"knowledge_asset": knowledge, "created": True})
        if path.startswith("/api/knowledge-assets/") and path.endswith("/index"):
            knowledge_id = path.split("/")[3]
            index_id = self._id("index")
            chunk_id = self._id("chunk")
            index = {
                "id": index_id,
                "knowledge_asset_id": knowledge_id,
                "status": "ready",
                "sync_state": "ready",
                "chunks": [{"id": chunk_id}],
            }
            self.indexes[index_id] = index
            return envelope({"index_entry": index, "created": True})
        if path.startswith("/api/knowledge-index/") and path.endswith("/embed"):
            index_id = path.split("/")[3]
            embedding_id = self._id("embedding")
            embedding = {"id": embedding_id, "index_entry_id": index_id}
            self.embeddings[index_id] = embedding
            return envelope(
                {
                    "index_entry_id": index_id,
                    "index_status": "ready",
                    "provider": MODULE.EXPECTED_PROVIDER,
                    "model": MODULE.EXPECTED_MODEL,
                    "dimension": MODULE.EXPECTED_DIMENSION,
                    "embedding_profile": MODULE.EXPECTED_PROFILE,
                    "embeddings": [embedding],
                }
            )
        if path.startswith("/api/knowledge-index/") and path.endswith("/serve"):
            index_id = path.split("/")[3]
            index = self.indexes[index_id]
            index["status"] = "serving"
            knowledge_id = str(index["knowledge_asset_id"])
            if knowledge_id not in self.serving:
                self.serving.append(knowledge_id)
            return envelope(
                {
                    "index_entry_id": index_id,
                    "index_status": "serving",
                    "sync_state": "ready",
                    "provider": MODULE.EXPECTED_PROVIDER,
                    "model": MODULE.EXPECTED_MODEL,
                    "dimension": MODULE.EXPECTED_DIMENSION,
                    "embedding_profile": MODULE.EXPECTED_PROFILE,
                }
            )
        if path == "/api/v2/retrieval/p2/search":
            results: list[dict[str, object]] = []
            for knowledge_id in self.serving[-int(payload.get("top_k", 5)) :]:
                knowledge = self.knowledge[knowledge_id]
                index = next(
                    item
                    for item in self.indexes.values()
                    if item["knowledge_asset_id"] == knowledge_id
                )
                extraction = self.extractions[str(knowledge["extraction_id"])]
                snapshot_id = str(knowledge["snapshot_id"])
                snapshot = self.snapshots[snapshot_id]
                review_id = str(snapshot["review_id"])
                results.append(
                    {
                        "knowledge_asset_id": knowledge_id,
                        "asset_id": knowledge["asset_id"],
                        "index_entry_id": index["id"],
                        "chunk_id": index["chunks"][0]["id"],
                        "source_trace": {
                            "index_entry_id": index["id"],
                            "knowledge_asset_id": knowledge_id,
                            "knowledge_asset_version": 1,
                            "snapshot_id": snapshot_id,
                            "snapshot_version": 1,
                            "review_id": review_id,
                            "review_status": "approved",
                            "review_version": 1,
                            "extraction_id": extraction["id"],
                            "extraction_job_id": extraction["job_id"],
                            "extraction_type": extraction["extract_type"],
                            "extraction_version": 1,
                            "asset_id": knowledge["asset_id"],
                            "asset_file_name": "fixture.png",
                            "asset_hash": "fake-sha256",
                            "asset_status": "uploaded",
                        },
                    }
                )
            return envelope(
                {
                    "retrieval_mode": "p2_vector_retrieval",
                    "fallback_used": False,
                    "matched_count": len(results),
                    "results": results,
                }
            )
        if path.startswith("/api/knowledge-assets/") and path.endswith("/archive"):
            knowledge_id = path.split("/")[3]
            self.knowledge[knowledge_id]["status"] = "archived"
            self.serving = [item for item in self.serving if item != knowledge_id]
            for index in self.indexes.values():
                if index["knowledge_asset_id"] == knowledge_id:
                    index["status"] = "archived"
                    index["sync_state"] = "archived"
            return envelope(self.knowledge[knowledge_id])
        raise AssertionError(f"unexpected POST {path}")

    def patch(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("PATCH", path))
        review_id = path.split("/")[3]
        review = self.reviews[review_id]
        snapshot_id = self._id("snapshot")
        snapshot = {
            "id": snapshot_id,
            "review_id": review_id,
            "extraction_id": review["extraction_id"],
        }
        self.snapshots[snapshot_id] = snapshot
        return envelope({"review": review, "snapshot": snapshot})

    def get(self, path: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append(("GET", path))
        if path.startswith("/api/assets/") and path.endswith("/extractions"):
            asset_id = path.split("/")[3]
            return envelope(
                {
                    "asset_id": asset_id,
                    "extractions": [
                        item
                        for item in self.extractions.values()
                        if item["asset_id"] == asset_id
                    ],
                }
            )
        if path.startswith("/api/knowledge-index/"):
            return envelope(self.indexes[path.split("/")[3]])
        if path.startswith("/api/knowledge-assets/"):
            return envelope(self.knowledge[path.split("/")[3]])
        if path == "/api/knowledge-embeddings":
            index_id = str((params or {})["index_entry_id"])
            return envelope({"embeddings": [self.embeddings[index_id]]})
        raise AssertionError(f"unexpected GET {path}")


class P2LocalAcceptanceScriptTest(unittest.TestCase):
    def test_01_unique_png_is_valid_and_unique_without_a_file(self) -> None:
        first = MODULE.unique_png("trace-a", "asset")
        second = MODULE.unique_png("trace-b", "asset")
        self.assertTrue(first.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertNotEqual(first, second)
        self.assertGreater(len(first), 68)

    def test_02_complete_api_only_chain_and_manifest(self) -> None:
        client = FakePublicApiClient()
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            summary = MODULE.run_acceptance(
                client=client,
                verbose=False,
                keep_data=True,
                output_manifest=manifest_path,
                trace_id="p2-local-test-12345678",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertTrue(summary["success"])
        self.assertEqual(summary["embedding"]["provider"], "siliconflow")
        self.assertEqual(summary["embedding"]["dimension"], 1536)
        self.assertEqual(summary["ready_serve_archive"]["before_serve_matched_count"], 0)
        self.assertEqual(summary["ready_serve_archive"]["after_archive_matched_count"], 0)
        self.assertTrue(summary["ready_serve_archive"]["embedding_physically_retained"])
        self.assertFalse(summary["version_replacement"]["old_version_retrieved"])
        self.assertEqual(len(manifest["queries"]), 12)
        self.assertEqual(
            {item["query_id"] for item in manifest["queries"]},
            {
                "p2_product_001",
                "p2_warranty_001",
                "p2_cancellation_001",
                "p2_return_001",
                "p2_caption_001",
                "p2_ocr_001",
                "p2_metadata_001",
                "p2_faq_001",
                "p2_archive_001",
                "p2_version_001",
                "p2_no_answer_001",
                "p2_paraphrase_001",
            },
        )
        version = next(
            item for item in manifest["queries"] if item["query_id"] == "p2_version_001"
        )
        self.assertEqual(len(version["expected_knowledge_asset_ids"]), 1)
        self.assertEqual(len(version["forbidden_knowledge_asset_ids"]), 1)
        archived = next(
            item for item in manifest["queries"] if item["query_id"] == "p2_archive_001"
        )
        self.assertTrue(archived["should_be_archived"])
        self.assertFalse(archived["should_return_results"])
        self.assertIn("12345678", archived["runtime_query"])

        paths = [path for _, path in client.calls]
        self.assertIn("/api/assets/upload", paths)
        self.assertIn("/api/v2/retrieval/p2/search", paths)
        self.assertTrue(any(path.endswith("/embed") for path in paths))
        self.assertTrue(any(path.endswith("/serve") for path in paths))
        self.assertTrue(any(path.endswith("/archive") for path in paths))
        self.assertFalse(any("customer-ops-agent" in path for path in paths))
        self.assertFalse(any("/api/v2/retrieval/search" == path for path in paths))

    def test_03_output_contains_no_vector_or_secret(self) -> None:
        client = FakePublicApiClient()
        with tempfile.TemporaryDirectory() as directory:
            summary = MODULE.run_acceptance(
                client=client,
                verbose=False,
                keep_data=False,
                output_manifest=Path(directory) / "manifest.json",
                trace_id="p2-local-test-safe",
            )
        serialized = json.dumps(summary).lower()
        self.assertTrue(summary["cleanup"]["performed"])
        self.assertEqual(len(summary["cleanup"]["archived_knowledge_asset_ids"]), 4)
        self.assertNotIn('"embedding": [', serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("database_url", serialized)
        self.assertNotIn("postgresql://", serialized)

    def test_04_source_has_no_database_or_backend_business_import(self) -> None:
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("sqlalchemy", source)
        self.assertNotIn("app.database", source)
        self.assertNotIn("db_models", source)
        self.assertNotIn("customer-ops-agent", source)

    def test_05_cli_contract_and_safe_redaction(self) -> None:
        parser = MODULE.build_parser()
        args = parser.parse_args(
            [
                "--base-url",
                "http://127.0.0.1:8000",
                "--verbose",
                "--timeout",
                "30",
                "--keep-data",
                "--output-manifest",
                "runtime.json",
            ]
        )
        self.assertEqual(args.timeout, 30)
        self.assertTrue(args.verbose)
        self.assertTrue(args.keep_data)
        redacted = MODULE._safe_message(
            "API_KEY=secret DATABASE_URL=postgresql://user:pass@host/db"
        )
        self.assertNotIn("secret", redacted)
        self.assertNotIn("user:pass", redacted)


if __name__ == "__main__":
    unittest.main()
