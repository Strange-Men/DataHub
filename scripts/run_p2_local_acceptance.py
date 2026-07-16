"""Run the P2-M8.1 local acceptance chain exclusively through public HTTP APIs.

The script deliberately creates no database session and imports no backend business
module. Runtime identifiers are written to an ignored manifest so the independent
P2 eval runner can calculate exact recall and MRR without committing local IDs.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

try:
    from eval_run_scope import load_run_scope, make_run_scope, normalize_run_id
except ModuleNotFoundError:  # imported as scripts.run_p2_local_acceptance in tests
    from scripts.eval_run_scope import load_run_scope, make_run_scope, normalize_run_id


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT_DIR / ".local-data" / "p2-eval-expected-manifest.json"
EXPECTED_PROVIDER = "siliconflow"
EXPECTED_MODEL = "Qwen/Qwen3-Embedding-4B"
EXPECTED_DIMENSION = 1536
EXPECTED_PROFILE = (
    "text_bridge:siliconflow:Qwen/Qwen3-Embedding-4B:1536"
)

# A valid 1x1 PNG. Appending a per-run marker keeps the SHA-256 unique while the
# uploaded bytes remain a valid PNG and never need to touch the local filesystem.
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
    "AQUBAScY42YAAAAASUVORK5CYII="
)


class AcceptanceError(RuntimeError):
    """A safe, user-facing acceptance failure."""


def unique_png(trace_id: str, label: str) -> bytes:
    """Return a valid, unique in-memory PNG without creating a repository file."""
    marker = f"\nP2-LOCAL-ACCEPTANCE:{trace_id}:{label}\n".encode("utf-8")
    return _PNG_1X1 + marker


def _safe_message(value: object) -> str:
    """Bound and redact common credential/connection patterns from errors."""
    text = str(value or "request failed").replace("\r", " ").replace("\n", " ")
    text = re.sub(
        r"(?i)(api[_-]?key|authorization|database_url|token|password)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(r"(?i)(postgres(?:ql)?://)[^\s]+", r"\1[REDACTED]", text)
    return text[:400]


def _response_data(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data")
    if not envelope.get("success") or not isinstance(data, dict):
        detail = envelope.get("detail")
        if isinstance(detail, dict):
            code = detail.get("code", "API_ERROR")
            message = detail.get("message", "request failed")
        else:
            code = envelope.get("code", "API_ERROR")
            message = envelope.get("message", detail or "request failed")
        raise AcceptanceError(f"{code}: {_safe_message(message)}")
    return data


class AcceptanceClient:
    """Small standard-library HTTP client for the project's public API."""

    def __init__(self, base_url: str, timeout: float) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AcceptanceError("--base-url must be an HTTP(S) origin.")
        if parsed.username or parsed.password:
            raise AcceptanceError("Credentials must not be embedded in --base-url.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                error_payload = json.loads(raw)
            except json.JSONDecodeError:
                error_payload = {"message": f"HTTP {exc.code}"}
            detail = error_payload.get("detail", error_payload)
            if isinstance(detail, dict):
                code = detail.get("code", f"HTTP_{exc.code}")
                message = detail.get("message", f"HTTP {exc.code}")
            else:
                code, message = f"HTTP_{exc.code}", detail
            raise AcceptanceError(f"{code}: {_safe_message(message)}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise AcceptanceError(
                f"API_UNAVAILABLE: {_safe_message(type(exc).__name__)}"
            ) from None
        try:
            result = json.loads(payload)
        except json.JSONDecodeError:
            raise AcceptanceError("INVALID_API_RESPONSE: response was not JSON.") from None
        if not isinstance(result, dict):
            raise AcceptanceError("INVALID_API_RESPONSE: expected a JSON object.")
        return result

    def get(self, path: str, params: dict[str, object] | None = None) -> dict[str, Any]:
        if params:
            path = f"{path}?{urlencode(params)}"
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, object] | None = None) -> dict[str, Any]:
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        return self._request("POST", path, body=body, content_type="application/json")

    def patch(self, path: str, payload: dict[str, object]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._request("PATCH", path, body=body, content_type="application/json")

    def upload_asset(
        self,
        file_name: str,
        content: bytes,
        *,
        eval_run_scope: str | None = None,
    ) -> dict[str, Any]:
        boundary = f"----DataHubP2Acceptance{uuid4().hex}"
        parts = [
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="asset_type"\r\n\r\n'
            "image\r\n",
            *(
                [
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="eval_run_scope"\r\n\r\n'
                    f"{eval_run_scope}\r\n"
                ]
                if eval_run_scope
                else []
            ),
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
            "Content-Type: image/png\r\n\r\n",
        ]
        body = b"".join(part.encode() for part in parts[:-1]) + parts[-1].encode() + content
        body += f"\r\n--{boundary}--\r\n".encode()
        return self._request(
            "POST",
            "/api/assets/upload",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )


@dataclass(frozen=True)
class GovernedVersion:
    asset_id: str
    extraction_job_id: str
    extraction_id: str
    review_id: str
    snapshot_id: str
    knowledge_asset_id: str
    index_entry_id: str
    chunk_id: str
    embedding_id: str
    content_type: str
    source_trace: dict[str, object]

    def ids(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "extraction_job_id": self.extraction_job_id,
            "extraction_id": self.extraction_id,
            "review_id": self.review_id,
            "snapshot_id": self.snapshot_id,
            "knowledge_asset_id": self.knowledge_asset_id,
            "index_entry_id": self.index_entry_id,
            "chunk_id": self.chunk_id,
            "embedding_id": self.embedding_id,
            "content_type": self.content_type,
            "source_trace": self.source_trace,
        }


class LocalAcceptanceRunner:
    def __init__(
        self,
        client: AcceptanceClient,
        *,
        trace_id: str,
        run_id: str,
        verbose: bool,
        keep_data: bool,
    ) -> None:
        self.client = client
        self.trace_id = trace_id
        self.run_id = normalize_run_id(run_id)
        self.verbose = verbose
        self.keep_data = keep_data
        self._request_counter = 0

    def _step(self, message: str) -> None:
        if self.verbose:
            print(f"[P2 local acceptance] {message}", file=sys.stderr)

    def _request_id(self, label: str) -> str:
        self._request_counter += 1
        return f"{self.trace_id}-{label}-{self._request_counter}"

    def upload(self, label: str) -> str:
        file_name = f"{label}-{self.trace_id[-12:]}.png"
        data = _response_data(
            self.client.upload_asset(
                file_name,
                unique_png(self.trace_id, label),
                eval_run_scope=f"datahub-eval:{self.run_id}",
            )
        )
        asset_id = str(data.get("id", ""))
        if not asset_id:
            raise AcceptanceError("UPLOAD_INVALID: Asset id was missing.")
        self._step(f"uploaded {label}: {asset_id}")
        return asset_id

    def search(self, query: str, label: str, top_k: int = 5) -> dict[str, Any]:
        data = _response_data(
            self.client.post(
                "/api/v2/retrieval/p2/search",
                {
                    "query": query,
                    "top_k": top_k,
                    "debug": False,
                    "request_id": self._request_id(label),
                    "evaluation_scope": f"datahub-eval:{self.run_id}",
                },
            )
        )
        if data.get("retrieval_mode") != "p2_vector_retrieval":
            raise AcceptanceError("RETRIEVAL_MODE_INVALID: expected P2-only retrieval.")
        if data.get("fallback_used") is not False:
            raise AcceptanceError("P1_FALLBACK_FORBIDDEN: P2 retrieval used fallback.")
        return data

    def govern_version(
        self,
        *,
        asset_id: str,
        label: str,
        extract_type: str,
        approved_content: str,
        probe_query: str,
        require_pre_serve_empty: bool = False,
    ) -> GovernedVersion:
        extraction = _response_data(
            self.client.post(
                f"/api/assets/{asset_id}/extract",
                {"extract_type": extract_type, "provider": "mock"},
            )
        )
        job = extraction.get("job") or {}
        result = extraction.get("result") or {}
        if job.get("status") != "success" or not result.get("id"):
            raise AcceptanceError("EXTRACTION_FAILED: mock extraction did not succeed.")
        extraction_list = _response_data(
            self.client.get(f"/api/assets/{asset_id}/extractions")
        )
        if not any(
            str(item.get("id")) == str(result["id"])
            for item in extraction_list.get("extractions", [])
        ):
            raise AcceptanceError(
                "EXTRACTION_RESULT_MISSING: result was not visible through the public API."
            )

        review = _response_data(
            self.client.post(
                f"/api/assets/{asset_id}/reviews",
                {"extraction_id": result["id"], "reviewer": "p2-local-acceptance"},
            )
        )
        approved = _response_data(
            self.client.patch(
                f"/api/reviews/{review['id']}",
                {
                    "review_status": "approved",
                    "reviewer": "p2-local-acceptance",
                    "review_comment": f"Approved by {self.trace_id}",
                    "revised_content": approved_content,
                },
            )
        )
        snapshot = approved.get("snapshot") or {}
        published = _response_data(
            self.client.post(f"/api/snapshots/{snapshot.get('id', '')}/publish")
        )
        knowledge = published.get("knowledge_asset") or {}
        indexed = _response_data(
            self.client.post(f"/api/knowledge-assets/{knowledge.get('id', '')}/index")
        )
        index_entry = indexed.get("index_entry") or {}
        chunks = index_entry.get("chunks") or []
        if len(chunks) != 1:
            raise AcceptanceError("INDEX_PROJECTION_INVALID: expected one governed chunk.")

        embedded = _response_data(
            self.client.post(f"/api/knowledge-index/{index_entry.get('id', '')}/embed")
        )
        embeddings = embedded.get("embeddings") or []
        if embedded.get("index_status") != "ready":
            raise AcceptanceError("AUTO_SERVING_REGRESSION: embed must leave Entry ready.")
        self._validate_profile(embedded)
        if len(embeddings) != 1:
            raise AcceptanceError("EMBEDDING_INVALID: expected one embedding record.")

        index_detail = _response_data(
            self.client.get(f"/api/knowledge-index/{index_entry['id']}")
        )
        if index_detail.get("status") != "ready" or index_detail.get("sync_state") != "ready":
            raise AcceptanceError("INDEX_NOT_READY: expected ready/ready before serve.")

        # Acceptance validates the current run's exact ID. Request the maximum
        # supported management pool so retained, semantically similar test runs
        # cannot hide a newly served candidate from the proof.
        before = self.search(probe_query, f"{label}-before-serve", top_k=20)
        before_ids = {str(item.get("knowledge_asset_id")) for item in before.get("results", [])}
        if str(knowledge.get("id")) in before_ids:
            raise AcceptanceError("READY_LEAKAGE: ready content was retrieved before serve.")
        if require_pre_serve_empty and before.get("matched_count") != 0:
            raise AcceptanceError("READY_LEAKAGE: dedicated pre-serve query was not empty.")

        served = _response_data(
            self.client.post(f"/api/knowledge-index/{index_entry['id']}/serve")
        )
        self._validate_profile(served)
        if served.get("index_status") != "serving":
            raise AcceptanceError("SERVING_GATE_FAILED: Entry did not become serving.")
        after = self.search(probe_query, f"{label}-after-serve", top_k=20)
        hit = next(
            (
                item
                for item in after.get("results", [])
                if str(item.get("knowledge_asset_id")) == str(knowledge.get("id"))
            ),
            None,
        )
        if hit is None:
            raise AcceptanceError("SERVING_RETRIEVAL_MISS: served content was not retrieved.")
        trace = hit.get("source_trace")
        required_trace = {
            "index_entry_id",
            "knowledge_asset_id",
            "knowledge_asset_version",
            "snapshot_id",
            "snapshot_version",
            "review_id",
            "review_status",
            "review_version",
            "extraction_id",
            "extraction_job_id",
            "extraction_type",
            "extraction_version",
            "asset_id",
            "asset_file_name",
            "asset_hash",
            "asset_status",
        }
        if not isinstance(trace, dict) or not required_trace <= set(trace):
            raise AcceptanceError("SOURCE_TRACE_INVALID: retrieval trace was incomplete.")
        expected_trace_ids = {
            "index_entry_id": str(index_entry["id"]),
            "knowledge_asset_id": str(knowledge["id"]),
            "snapshot_id": str(snapshot["id"]),
            "review_id": str(review["id"]),
            "extraction_id": str(result["id"]),
            "extraction_job_id": str(job["id"]),
            "asset_id": asset_id,
        }
        if any(str(trace.get(key)) != value for key, value in expected_trace_ids.items()):
            raise AcceptanceError("SOURCE_TRACE_INVALID: retrieval trace was inconsistent.")

        version = GovernedVersion(
            asset_id=asset_id,
            extraction_job_id=str(job["id"]),
            extraction_id=str(result["id"]),
            review_id=str(review["id"]),
            snapshot_id=str(snapshot["id"]),
            knowledge_asset_id=str(knowledge["id"]),
            index_entry_id=str(index_entry["id"]),
            chunk_id=str(chunks[0]["id"]),
            embedding_id=str(embeddings[0]["id"]),
            content_type=extract_type,
            source_trace=dict(trace),
        )
        self._step(f"governed and served {label}: {version.knowledge_asset_id}")
        return version

    @staticmethod
    def _validate_profile(payload: dict[str, Any]) -> None:
        actual = (
            payload.get("provider"),
            payload.get("model"),
            payload.get("dimension"),
            payload.get("embedding_profile"),
        )
        expected = (
            EXPECTED_PROVIDER,
            EXPECTED_MODEL,
            EXPECTED_DIMENSION,
            EXPECTED_PROFILE,
        )
        if actual != expected:
            raise AcceptanceError(
                "EMBEDDING_PROFILE_INVALID: expected SiliconFlow Qwen 1536 profile."
            )

    def archive_and_assert_zero(self, version: GovernedVersion, query: str) -> dict[str, object]:
        archived = _response_data(
            self.client.post(
                f"/api/knowledge-assets/{version.knowledge_asset_id}/archive"
            )
        )
        if archived.get("status") != "archived":
            raise AcceptanceError("ARCHIVE_FAILED: Knowledge Asset was not archived.")
        after = self.search(query, "archive-after")
        returned_ids = {
            str(item.get("knowledge_asset_id")) for item in after.get("results", [])
        }
        if version.knowledge_asset_id in returned_ids or after.get("matched_count") != 0:
            raise AcceptanceError("ARCHIVED_LEAKAGE: archived content remained retrievable.")

        embedding_list = _response_data(
            self.client.get(
                "/api/knowledge-embeddings",
                {"index_entry_id": version.index_entry_id, "page_size": 20},
            )
        )
        physically_retained = any(
            str(item.get("id")) == version.embedding_id
            for item in embedding_list.get("embeddings", [])
        )
        if not physically_retained:
            raise AcceptanceError(
                "ARCHIVE_PROOF_INVALID: embedding was not physically retained."
            )
        return {
            "before_serve_matched_count": 0,
            "after_serve_hit": True,
            "after_archive_matched_count": int(after.get("matched_count", -1)),
            "embedding_physically_retained": True,
        }

    def run(self) -> tuple[dict[str, Any], dict[str, Any]]:
        nonce = self.trace_id[-12:]

        # Independent ready -> serve -> archive proof runs before the Eval corpus.
        smoke_query = f"What is the local acceptance rule {nonce}?"
        smoke_asset = self.upload("archive-smoke")
        smoke = self.govern_version(
            asset_id=smoke_asset,
            label="archive-smoke",
            extract_type="ocr",
            approved_content=(
                f"Unique local acceptance rule {nonce}: the withdrawn campaign grants "
                "exactly eleven percent off before archival."
            ),
            probe_query=smoke_query,
            require_pre_serve_empty=True,
        )
        archive_proof = self.archive_and_assert_zero(smoke, smoke_query)

        policy_asset = self.upload("policy-ocr")
        policy = self.govern_version(
            asset_id=policy_asset,
            label="policy-ocr",
            extract_type="ocr",
            approved_content=(
                "Governed OCR product and policy record. SKU DH-100 is made from recycled "
                "aluminum and is intended for indoor use. The DH-100 warranty lasts twelve "
                "months. Customers may cancel an order before shipment. An unused DH-100 "
                "may be returned within thirty days. The campaign poster states a seven-day "
                "price protection rule."
            ),
            probe_query="How long is the warranty for DH-100?",
        )

        caption_asset = self.upload("caption-faq")
        caption = self.govern_version(
            asset_id=caption_asset,
            label="caption-faq",
            extract_type="caption",
            approved_content=(
                "Approved image caption: the DH-100 product image shows a foldable stand. "
                "FAQ: to reset the DH-300 indicator, hold the reset button for five seconds."
            ),
            probe_query="Which product image shows a foldable stand?",
        )

        metadata_asset = self.upload("metadata")
        metadata = self.govern_version(
            asset_id=metadata_asset,
            label="metadata",
            extract_type="metadata",
            approved_content=(
                "Approved asset metadata records the blue desk lamp as SKU LAMP-BLUE in "
                "the Home Office collection."
            ),
            probe_query="Which SKU and collection are recorded for the blue desk lamp asset?",
        )

        version_asset = self.upload("versioned-package")
        old_version = self.govern_version(
            asset_id=version_asset,
            label="version-v1",
            extract_type="caption",
            approved_content=(
                f"Obsolete DH-200 V1 package {nonce} included only a charging cable."
            ),
            probe_query=f"What did obsolete DH-200 V1 package {nonce} include?",
        )
        current_version = self.govern_version(
            asset_id=version_asset,
            label="version-v2",
            extract_type="caption",
            approved_content=(
                "Current DH-200 V2 package includes an adapter and charging cable."
            ),
            probe_query="What accessories are included in the current DH-200 V2 package?",
        )
        old_asset_detail = _response_data(
            self.client.get(f"/api/knowledge-assets/{old_version.knowledge_asset_id}")
        )
        old_index_detail = _response_data(
            self.client.get(f"/api/knowledge-index/{old_version.index_entry_id}")
        )
        version_search = self.search(
            "What accessories are included in the current DH-200 V2 package?",
            "version-current",
        )
        version_ids = {
            str(item.get("knowledge_asset_id"))
            for item in version_search.get("results", [])
        }
        if (
            old_asset_detail.get("status") != "archived"
            or old_index_detail.get("status") != "archived"
            or old_version.knowledge_asset_id in version_ids
            or current_version.knowledge_asset_id not in version_ids
        ):
            raise AcceptanceError("VERSION_REPLACEMENT_FAILED: V1 was not zero-recall.")

        entries = self._manifest_entries(
            policy=policy,
            caption=caption,
            metadata=metadata,
            archived=smoke,
            old_version=old_version,
            current_version=current_version,
            smoke_query=smoke_query,
        )
        manifest = {
            "version": "p1-p2-m9.1-local-runtime-v2",
            "trace_id": self.trace_id,
            "run_scope": make_run_scope(
                self.run_id,
                trace_id=self.trace_id,
                creator="run_p2_local_acceptance",
            ),
            "generated_at_epoch_ms": int(time.time() * 1000),
            "created_resources": {
                "asset_ids": [
                    smoke.asset_id,
                    policy.asset_id,
                    caption.asset_id,
                    metadata.asset_id,
                    old_version.asset_id,
                ],
                "knowledge_asset_ids": [
                    smoke.knowledge_asset_id,
                    policy.knowledge_asset_id,
                    caption.knowledge_asset_id,
                    metadata.knowledge_asset_id,
                    old_version.knowledge_asset_id,
                    current_version.knowledge_asset_id,
                ],
                "chunk_ids": [
                    smoke.chunk_id,
                    policy.chunk_id,
                    caption.chunk_id,
                    metadata.chunk_id,
                    old_version.chunk_id,
                    current_version.chunk_id,
                ],
                "cleanup_knowledge_asset_ids": [
                    policy.knowledge_asset_id,
                    caption.knowledge_asset_id,
                    metadata.knowledge_asset_id,
                    current_version.knowledge_asset_id,
                ],
            },
            "queries": entries,
        }
        summary = {
            "success": True,
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "namespace": f"datahub-eval:{self.run_id}",
            "retrieval_mode": "p2_vector_retrieval",
            "fallback_used": False,
            "embedding": {
                "provider": EXPECTED_PROVIDER,
                "model": EXPECTED_MODEL,
                "dimension": EXPECTED_DIMENSION,
                "profile": EXPECTED_PROFILE,
            },
            "ready_serve_archive": archive_proof,
            "version_replacement": {
                "asset_id": version_asset,
                "old_knowledge_asset_id": old_version.knowledge_asset_id,
                "old_index_entry_id": old_version.index_entry_id,
                "old_status": "archived",
                "current_knowledge_asset_id": current_version.knowledge_asset_id,
                "current_index_entry_id": current_version.index_entry_id,
                "old_version_retrieved": False,
            },
            "source_traces": {
                "archive_smoke": smoke.ids(),
                "policy_ocr": policy.ids(),
                "caption_faq": caption.ids(),
                "metadata": metadata.ids(),
                "version_v1": old_version.ids(),
                "version_v2": current_version.ids(),
            },
            "eval_query_count": len(entries),
            "keep_data": self.keep_data,
        }
        if self.keep_data:
            summary["cleanup"] = {
                "performed": False,
                "reason": "--keep-data retained the serving Eval corpus",
                "archived_knowledge_asset_ids": [],
            }
        else:
            cleaned: list[str] = []
            for version in (policy, caption, metadata, current_version):
                archived_row = _response_data(
                    self.client.post(
                        f"/api/knowledge-assets/{version.knowledge_asset_id}/archive"
                    )
                )
                if archived_row.get("status") != "archived":
                    raise AcceptanceError(
                        "CLEANUP_FAILED: generated Eval Knowledge Asset was not archived."
                    )
                cleaned.append(version.knowledge_asset_id)
            summary["cleanup"] = {
                "performed": True,
                "reason": "default cleanup archived the serving Eval corpus",
                "archived_knowledge_asset_ids": cleaned,
            }
        return summary, manifest

    @staticmethod
    def _manifest_entries(
        *,
        policy: GovernedVersion,
        caption: GovernedVersion,
        metadata: GovernedVersion,
        archived: GovernedVersion,
        old_version: GovernedVersion,
        current_version: GovernedVersion,
        smoke_query: str,
    ) -> list[dict[str, object]]:
        def expected(
            query_id: str,
            version: GovernedVersion,
            keywords: list[str],
            *,
            forbidden: GovernedVersion | None = None,
        ) -> dict[str, object]:
            item: dict[str, object] = {
                "query_id": query_id,
                "expected_knowledge_asset_ids": [version.knowledge_asset_id],
                "expected_asset_ids": [version.asset_id],
                "expected_chunk_ids": [version.chunk_id],
                "expected_keywords": keywords,
                "should_return_results": True,
                "should_be_archived": False,
            }
            if forbidden is not None:
                item.update(
                    {
                        "forbidden_knowledge_asset_ids": [forbidden.knowledge_asset_id],
                        "forbidden_asset_ids": [],
                        "forbidden_chunk_ids": [forbidden.chunk_id],
                    }
                )
            return item

        return [
            expected("p2_product_001", policy, ["recycled aluminum", "indoor"]),
            expected("p2_warranty_001", policy, ["warranty", "twelve months"]),
            expected("p2_cancellation_001", policy, ["cancel", "before shipment"]),
            expected("p2_return_001", policy, ["return", "thirty days"]),
            expected("p2_caption_001", caption, ["foldable", "stand"]),
            expected("p2_ocr_001", policy, ["seven-day", "price protection"]),
            expected("p2_metadata_001", metadata, ["LAMP-BLUE", "Home Office"]),
            expected("p2_faq_001", caption, ["reset button", "five seconds"]),
            {
                "query_id": "p2_archive_001",
                "expected_knowledge_asset_ids": [archived.knowledge_asset_id],
                "expected_asset_ids": [archived.asset_id],
                "expected_chunk_ids": [archived.chunk_id],
                "expected_keywords": [],
                "should_return_results": False,
                "should_be_archived": True,
                "runtime_query": smoke_query,
            },
            expected(
                "p2_version_001",
                current_version,
                ["V2", "adapter"],
                forbidden=old_version,
            ),
            {
                "query_id": "p2_no_answer_001",
                "expected_knowledge_asset_ids": [],
                "expected_asset_ids": [],
                "expected_chunk_ids": [],
                "expected_keywords": [],
                "should_return_results": False,
                "should_be_archived": False,
            },
            expected("p2_paraphrase_001", policy, ["cancel", "before shipment"]),
        ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the governed P2 local retrieval acceptance chain."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--run-id",
        help="Optional stable test-run id; auto-generated when omitted.",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Record that the generated local Eval corpus is retained for follow-up inspection.",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Ignored runtime expected-ID manifest for run_p2_rag_eval.py.",
    )
    parser.add_argument(
        "--cleanup-manifest",
        type=Path,
        help=(
            "Explicitly archive only the active test Knowledge Assets listed by a "
            "validated DataHub Eval manifest, then exit."
        ),
    )
    return parser


def run_acceptance(
    *,
    client: AcceptanceClient,
    verbose: bool,
    keep_data: bool,
    output_manifest: Path,
    trace_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    trace = trace_id or f"p2-local-{time.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    scope_id = normalize_run_id(run_id or trace)
    summary, manifest = LocalAcceptanceRunner(
        client,
        trace_id=trace,
        run_id=scope_id,
        verbose=verbose,
        keep_data=keep_data,
    ).run()
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary["expected_manifest"] = str(output_manifest.resolve())
    return summary


def cleanup_manifest_corpus(
    *, client: AcceptanceClient, manifest_path: Path
) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    scope = load_run_scope(payload)
    if scope is None or scope.get("creator") != "run_p2_local_acceptance":
        raise AcceptanceError(
            "CLEANUP_SCOPE_INVALID: manifest is not an acceptance test corpus."
        )
    created = payload.get("created_resources")
    targets = created.get("cleanup_knowledge_asset_ids") if isinstance(created, dict) else None
    if not isinstance(targets, list) or any(
        not isinstance(value, str) or not value.strip() for value in targets
    ):
        raise AcceptanceError(
            "CLEANUP_SCOPE_INVALID: explicit cleanup targets are missing."
        )
    unique_targets = list(dict.fromkeys(value.strip() for value in targets))
    archived: list[str] = []
    already_archived: list[str] = []
    for knowledge_asset_id in unique_targets:
        detail = _response_data(
            client.get(f"/api/knowledge-assets/{knowledge_asset_id}")
        )
        if detail.get("status") == "archived":
            already_archived.append(knowledge_asset_id)
            continue
        result = _response_data(
            client.post(f"/api/knowledge-assets/{knowledge_asset_id}/archive")
        )
        if result.get("status") != "archived":
            raise AcceptanceError(
                "CLEANUP_FAILED: a scoped test Knowledge Asset was not archived."
            )
        archived.append(knowledge_asset_id)
    return {
        "success": True,
        "run_id": scope["run_id"],
        "namespace": scope["namespace"],
        "cleanup_mode": "logical_archive_only",
        "archived_knowledge_asset_ids": archived,
        "already_archived_knowledge_asset_ids": already_archived,
        "deleted_records": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        client = AcceptanceClient(args.base_url, args.timeout)
        if args.cleanup_manifest is not None:
            summary = cleanup_manifest_corpus(
                client=client,
                manifest_path=args.cleanup_manifest,
            )
        else:
            summary = run_acceptance(
                client=client,
                verbose=args.verbose,
                keep_data=args.keep_data,
                output_manifest=args.output_manifest,
                run_id=args.run_id,
            )
    except (AcceptanceError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"success": False, "error": _safe_message(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
