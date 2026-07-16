#!/usr/bin/env python3
"""P1 Pipeline Harness — one-command end-to-end verification of the DataHub P1 data flow.

Usage:
  python scripts/run_p1_pipeline_harness.py
  python scripts/run_p1_pipeline_harness.py --base-url http://127.0.0.1:8000
  python scripts/run_p1_pipeline_harness.py --base-url https://datahub-jr8x.onrender.com --verbose --stop-on-fail
  python scripts/run_p1_pipeline_harness.py --check-pgvector

The harness calls existing P1 APIs in order and reports PASS / FAIL for each step.
It does NOT create new database tables, modify schemas, or change any business API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import requests

# ---------------------------------------------------------------------------
# Inline minimal sample data — no external file dependency
# ---------------------------------------------------------------------------
SAMPLE_CONVERSATIONS = [
    {
        "conversation_id": "conv_harness_001",
        "messages": [
            {
                "message_id": "msg_harness_001a",
                "role": "customer",
                "content": "Hi, I want to return a pair of shoes I bought last week. The size is wrong. How do I get a refund?",
                "timestamp": "2026-07-04T10:00:00Z",
            },
            {
                "message_id": "msg_harness_001b",
                "role": "agent",
                "content": "You can return the shoes within 30 days. Please send them back in the original box and we will process the refund once we receive the return.",
                "timestamp": "2026-07-04T10:01:00Z",
            },
        ],
    },
    {
        "conversation_id": "conv_harness_002",
        "messages": [
            {
                "message_id": "msg_harness_002a",
                "role": "customer",
                "content": "Where is my order? The tracking number is 1Z999AA10123456784 and I haven't received any updates.",
                "timestamp": "2026-07-04T11:00:00Z",
            },
            {
                "message_id": "msg_harness_002b",
                "role": "agent",
                "content": "Your order is currently in transit. The tracking shows it will arrive in 2-3 business days. If it does not arrive by then, please contact us again.",
                "timestamp": "2026-07-04T11:01:00Z",
            },
        ],
    },
    {
        "conversation_id": "conv_harness_003",
        "messages": [
            {
                "message_id": "msg_harness_003a",
                "role": "customer",
                "content": "I need to speak to a human agent. This chatbot isn't helping me with my refund issue.",
                "timestamp": "2026-07-04T12:00:00Z",
            },
            {
                "message_id": "msg_harness_003b",
                "role": "agent",
                "content": "I understand your frustration. Let me transfer you to a human agent. Please hold for a moment.",
                "timestamp": "2026-07-04T12:01:00Z",
            },
        ],
    },
    {
        "conversation_id": "conv_harness_004",
        "messages": [
            {
                "message_id": "msg_harness_004a",
                "role": "customer",
                "content": "lol haha asdf",
                "timestamp": "2026-07-04T13:00:00Z",
            },
            {
                "message_id": "msg_harness_004b",
                "role": "agent",
                "content": "ok",
                "timestamp": "2026-07-04T13:01:00Z",
            },
        ],
    },
]

IMPORT_PAYLOAD: dict[str, Any] = {
    "source_name": "p1_harness_test",
    "conversations": SAMPLE_CONVERSATIONS,
}


def scoped_import_payload(trace_id: str) -> dict[str, Any]:
    """Create unique P1 test corpus identifiers without changing sample meaning."""
    suffix = "".join(ch for ch in trace_id.lower() if ch.isalnum())[-20:]
    if len(suffix) < 6:
        raise ValueError("trace_id is too short to create a safe run scope")
    payload = deepcopy(IMPORT_PAYLOAD)
    payload["source_name"] = f"p1_harness_test::{trace_id}"
    for conversation in payload["conversations"]:
        conversation["conversation_id"] = (
            f"{conversation['conversation_id']}__{suffix}"
        )
        for message in conversation["messages"]:
            message["message_id"] = f"{message['message_id']}__{suffix}"
    return payload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace_id() -> str:
    return f"p1-harness-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"


def _truncate(text: str, max_len: int = 300) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "...(truncated)"


def _safe_json_dump(obj: object, max_len: int = 500) -> str:
    try:
        dumped = json.dumps(obj, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        dumped = str(obj)
    return _truncate(dumped, max_len)


# ---------------------------------------------------------------------------
# Step result
# ---------------------------------------------------------------------------


class StepResult:
    __slots__ = ("step", "status", "http_status", "message", "detail", "key_ids")

    def __init__(
        self,
        step: str,
        status: str,
        http_status: int | None = None,
        message: str = "",
        detail: str = "",
        key_ids: dict[str, str] | None = None,
    ) -> None:
        self.step = step
        self.status = status  # PASS | FAIL | SKIP
        self.http_status = http_status
        self.message = message
        self.detail = detail
        self.key_ids = key_ids or {}

    def is_pass(self) -> bool:
        return self.status == "PASS"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class PipelineHarness:
    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        verbose: bool = False,
        stop_on_fail: bool = False,
        trace_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verbose = verbose
        self.stop_on_fail = stop_on_fail
        self.trace_id = trace_id or _trace_id()
        self.results: list[StepResult] = []
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"
        # IDs collected across steps
        self.batch_id: str = ""
        self.sanitized_message_id: str = ""
        self.candidate_id: str = ""
        self.retrieval_id: str = ""
        self.bad_case_id: str = ""

    # -- low-level HTTP helpers -------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get(self, path: str) -> requests.Response:
        return self._session.get(self._url(path), timeout=self.timeout)

    def _post(self, path: str, json_data: dict[str, Any] | None = None, extra_headers: dict[str, str] | None = None) -> requests.Response:
        headers = {}
        if extra_headers:
            headers.update(extra_headers)
        return self._session.post(self._url(path), json=json_data, timeout=self.timeout, headers=headers or None)

    def _patch(self, path: str, json_data: dict[str, Any]) -> requests.Response:
        return self._session.patch(self._url(path), json=json_data, timeout=self.timeout)

    def _record(
        self,
        step: str,
        status: str,
        http_status: int | None = None,
        message: str = "",
        detail: str = "",
        key_ids: dict[str, str] | None = None,
    ) -> StepResult:
        result = StepResult(step, status, http_status, message, detail, key_ids)
        self.results.append(result)
        return result

    def _call_and_record(
        self,
        step: str,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        ok_codes: tuple[int, ...] = (200,),
        key_extractor: Any = None,
    ) -> StepResult:
        label = f"{self.results.__len__() + 1:02d} {step}"
        try:
            if method == "GET":
                resp = self._get(path)
            elif method == "POST":
                resp = self._post(path, json_data, extra_headers)
            elif method == "PATCH":
                resp = self._patch(path, json_data or {})
            else:
                return self._record(step, "FAIL", message=f"Unknown method: {method}")

            http_status = resp.status_code
            resp_json: dict[str, Any] | None = None
            try:
                resp_json = resp.json()
            except (ValueError, requests.JSONDecodeError):
                pass

            success = resp_json.get("success") if isinstance(resp_json, dict) else None
            is_ok = http_status in ok_codes or (success is True)

            key_ids: dict[str, str] = {}
            if key_extractor and resp_json:
                key_ids = key_extractor(resp_json)

            if is_ok:
                detail = ""
                if self.verbose and resp_json:
                    detail = _safe_json_dump(resp_json)
                return self._record(step, "PASS", http_status, detail=detail, key_ids=key_ids)
            else:
                error_info = ""
                if isinstance(resp_json, dict):
                    err = resp_json.get("error") or resp_json.get("detail", "")
                    error_info = _safe_json_dump(err) if isinstance(err, (dict, list)) else str(err)[:400]
                else:
                    error_info = _truncate(resp.text, 400)
                return self._record(
                    step,
                    "FAIL",
                    http_status,
                    message=f"HTTP {http_status} | {error_info}",
                    detail=_safe_json_dump(resp_json) if self.verbose else "",
                )

        except requests.ConnectionError:
            return self._record(
                step, "FAIL",
                message=f"Connection refused: {self._url(path)}. Is the backend running?",
            )
        except requests.Timeout:
            return self._record(
                step, "FAIL",
                message=f"Request timed out ({self.timeout}s): {self._url(path)}",
            )
        except Exception:
            return self._record(
                step, "FAIL",
                message=f"Unexpected error: {_truncate(traceback.format_exc(), 400)}",
            )

    # -- step implementations ---------------------------------------------

    def step_health_check(self) -> StepResult:
        return self._call_and_record(
            "health_check", "GET", "/api/health",
            key_extractor=lambda j: {"phase": j.get("data", {}).get("phase", "") or j.get("phase", "")},
        )

    def step_import_sample_data(self) -> StepResult:
        result = self._call_and_record(
            "import_sample_data", "POST", "/api/sources/import-json",
            json_data=scoped_import_payload(self.trace_id),
            key_extractor=lambda j: {"batch_id": str((j.get("data") or {}).get("batch_id", ""))},
        )
        bid = result.key_ids.get("batch_id", "")
        if bid:
            self.batch_id = bid
        return result

    def step_machine_cleaning(self) -> StepResult:
        if not self.batch_id:
            return self._record("machine_cleaning", "SKIP", message="No batch_id from import step")
        return self._call_and_record(
            "machine_cleaning", "POST", f"/api/cleaning/run/{self.batch_id}",
            key_extractor=lambda j: {"sanitized_batch_id": str((j.get("data") or {}).get("sanitized_batch_id", ""))},
        )

    def step_manual_cleaning(self) -> StepResult:
        if not self.batch_id:
            return self._record("manual_cleaning", "SKIP", message="No batch_id from import step")

        # First get the sanitized batch to find a message ID
        try:
            resp = self._get(f"/api/sanitized/{self.batch_id}")
            if resp.status_code != 200:
                return self._record("manual_cleaning", "FAIL", resp.status_code,
                                    message=f"Cannot read sanitized batch: {_truncate(resp.text, 200)}")
            data = resp.json()
            batch_data = data.get("data") or data
            messages = batch_data.get("messages", [])
            if not messages:
                return self._record("manual_cleaning", "SKIP", message="No messages in sanitized batch to manually clean")

            msg = messages[0]
            msg_id = msg.get("message_id", "")
            if not msg_id:
                return self._record("manual_cleaning", "SKIP", message="No message_id in first sanitized message")

            self.sanitized_message_id = msg_id
        except Exception:
            return self._record("manual_cleaning", "FAIL", message=f"Cannot fetch sanitized batch: {_truncate(traceback.format_exc(), 300)}")

        return self._call_and_record(
            "manual_cleaning", "PATCH", f"/api/sanitized/{self.batch_id}/messages/{self.sanitized_message_id}/manual-clean",
            json_data={
                "content": "Manually verified content — harness automated cleaning.",
                "manual_action": "keep_edited",
                "cleaner": "p1_harness",
                "cleaning_note": "Harness automated manual cleaning step.",
            },
            key_extractor=lambda j: {"record_id": str((j.get("data") or {}).get("record_id", ""))},
        )

    def step_generate_candidates(self) -> StepResult:
        if not self.batch_id:
            return self._record("generate_knowledge_candidates", "SKIP", message="No batch_id")
        return self._call_and_record(
            "generate_knowledge_candidates", "POST", f"/api/extraction/run/{self.batch_id}",
            key_extractor=lambda j: {"candidate_count": str((j.get("data") or {}).get("candidate_count", ""))},
        )

    def step_approve_knowledge(self) -> StepResult:
        # Get pending review candidates and approve the first one
        try:
            resp = self._get("/api/review/pending")
            if resp.status_code != 200:
                return self._record("approve_knowledge", "FAIL", resp.status_code,
                                    message=f"Cannot list pending candidates: {_truncate(resp.text, 200)}")
            data = resp.json()
            wrapper = data.get("data") or data
            candidates = wrapper.get("candidates", [])
            scoped_candidates = [
                candidate
                for candidate in candidates
                if str(candidate.get("source_batch_id", "")) == self.batch_id
            ]
            if not scoped_candidates:
                return self._record(
                    "approve_knowledge",
                    "FAIL",
                    message="No pending candidate belongs to this Harness run.",
                )
            c = scoped_candidates[0]
            cid = c.get("candidate_id", "")
            if not cid:
                return self._record("approve_knowledge", "SKIP", message="First pending candidate has no candidate_id")
            self.candidate_id = cid
        except Exception:
            return self._record("approve_knowledge", "FAIL", message=f"Error fetching pending candidates: {_truncate(traceback.format_exc(), 300)}")

        return self._call_and_record(
            "approve_knowledge", "POST", f"/api/review/{self.candidate_id}/approve",
            json_data={"reviewer": "p1_harness", "review_note": "Harness auto-approve for pipeline verification."},
            key_extractor=lambda j: {"candidate_id": str((j.get("data") or {}).get("candidate_id", self.candidate_id))},
        )

    def step_sync_rag(self) -> StepResult:
        def _extract(j: dict[str, Any]) -> dict[str, str]:
            data = j.get("data") or {}
            ids: dict[str, str] = {
                "chunk_count": str(data.get("chunk_count", "")),
            }
            # P1-M22: extract vector sync fields if present
            emb_count = data.get("embedding_count")
            if emb_count is not None:
                ids["embedding_count"] = str(emb_count)
            vec_enabled = data.get("vector_sync_enabled")
            if vec_enabled is not None:
                ids["vector_sync_enabled"] = str(vec_enabled)
            emb_provider = data.get("embedding_provider")
            if emb_provider:
                ids["embedding_provider"] = str(emb_provider)
            emb_dim = data.get("embedding_dimension")
            if emb_dim is not None:
                ids["embedding_dimension"] = str(emb_dim)
            # P1-M22.2: error observability
            failed = data.get("failed_embedding_count")
            if failed:
                ids["failed_embedding_count"] = str(failed)
            err = data.get("vector_sync_error")
            if err:
                ids["vector_sync_error"] = str(err)[:100]
            return ids
        return self._call_and_record(
            "sync_rag", "POST", "/api/rag/build",
            key_extractor=_extract,
        )

    def step_customerops_retrieve(self) -> StepResult:
        def _extract(j: dict[str, Any]) -> dict[str, str]:
            data = j.get("data") or {}
            ids: dict[str, str] = {
                "retrieval_id": str(data.get("retrieval_id", "")),
            }
            # P1-M23: extract retrieval mode and fallback info
            mode = data.get("retrieval_mode")
            if mode:
                ids["retrieval_mode"] = str(mode)
            fb = data.get("fallback_used")
            if fb is not None:
                ids["fallback_used"] = str(fb)
            reason = data.get("fallback_reason")
            if reason:
                ids["fallback_reason"] = str(reason)[:100]
            return ids
        result = self._call_and_record(
            "customerops_retrieve", "POST", "/api/customer-ops-agent/retrieve",
            json_data={"query": "How do I return shoes and get a refund?", "top_k": 3},
            extra_headers={"X-DataHub-Client": "CustomerOpsAgent"},
            key_extractor=_extract,
        )
        rid = result.key_ids.get("retrieval_id", "")
        if rid:
            self.retrieval_id = rid
        return result

    def step_submit_bad_case(self) -> StepResult:
        if not self.retrieval_id:
            return self._record("submit_bad_case", "SKIP", message="No retrieval_id from retrieve step")

        return self._call_and_record(
            "submit_bad_case", "POST", "/api/customer-ops-agent/bad-cases",
            json_data={
                "retrieval_id": self.retrieval_id,
                "user_query": "How do I return shoes and get a refund?",
                "agent_answer": "You can return within 30 days with the original box.",
                "issue_type": "missing_knowledge",
                "expected_answer": "You need to fill out the return form in your account, then ship the item back within 30 days.",
                "severity": "medium",
            },
            extra_headers={"X-DataHub-Client": "CustomerOpsAgent"},
            key_extractor=lambda j: {"bad_case_id": str((j.get("data") or {}).get("bad_case_id", ""))},
        )

    def step_bad_case_to_draft(self) -> StepResult:
        if not self.bad_case_id:
            # Find bad_case_id from previous result
            for r in self.results:
                if r.step == "submit_bad_case":
                    bid = r.key_ids.get("bad_case_id", "")
                    if bid:
                        self.bad_case_id = bid
                        break
        if not self.bad_case_id:
            return self._record("bad_case_to_draft", "SKIP", message="No bad_case_id from submit_bad_case step")

        return self._call_and_record(
            "bad_case_to_draft", "POST", f"/api/bad-cases/{self.bad_case_id}/create-draft",
            json_data={
                "question": "How do I return shoes and get a refund?",
                "answer": "You need to fill out the return form in your account, then ship the item back within 30 days. Refunds are processed within 5-7 business days after we receive the return.",
                "intent": "refund",
                "tags": ["refund", "return", "shoes"],
                "risk_level": "low",
                "quality_score": 0.85,
                "knowledge_type": "faq",
                "reviewer": "p1_harness",
                "review_note": "Harness-generated draft from Bad Case.",
            },
            key_extractor=lambda j: {"candidate_id": str((j.get("data") or {}).get("candidate_id", ""))},
        )

    # -- runner ------------------------------------------------------------

    def run(self, check_pgvector: bool = False) -> bool:
        if check_pgvector:
            return self._run_pgvector_check()

        start = time.monotonic()
        print("P1 Pipeline Harness")
        print(f"base_url: {self.base_url}")
        print(f"trace_id: {self.trace_id}")
        print(f"started:  {_now_iso()}")
        print()

        steps = [
            self.step_health_check,
            self.step_import_sample_data,
            self.step_machine_cleaning,
            self.step_manual_cleaning,
            self.step_generate_candidates,
            self.step_approve_knowledge,
            self.step_sync_rag,
            self.step_customerops_retrieve,
            self.step_submit_bad_case,
            self.step_bad_case_to_draft,
        ]

        for step_fn in steps:
            result = step_fn()
            self._print_result(result)
            # capture bad_case_id from submit step for subsequent draft step
            if result.step == "submit_bad_case" and result.key_ids.get("bad_case_id"):
                self.bad_case_id = result.key_ids["bad_case_id"]
            if self.stop_on_fail and not result.is_pass() and result.status != "SKIP":
                print("\n[stop-on-fail] Aborting after first non-PASS step.")
                break

        elapsed = time.monotonic() - start
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        skipped = sum(1 for r in self.results if r.status == "SKIP")
        total = len(self.results)

        print(f"\nSummary:")
        print(f"  trace_id: {self.trace_id}")
        print(f"  passed:   {passed}")
        print(f"  failed:   {failed}")
        print(f"  skipped:  {skipped}")
        print(f"  total:    {total}")
        print(f"  duration: {elapsed:.1f}s")

        # Print collected key IDs for traceability
        ids = []
        if self.batch_id:
            ids.append(f"batch_id={self.batch_id}")
        if self.sanitized_message_id:
            ids.append(f"sanitized_message_id={self.sanitized_message_id}")
        if self.candidate_id:
            ids.append(f"candidate_id={self.candidate_id}")
        if self.retrieval_id:
            ids.append(f"retrieval_id={self.retrieval_id}")
        if self.bad_case_id:
            ids.append(f"bad_case_id={self.bad_case_id}")
        if ids:
            print(f"  key_ids:  {', '.join(ids)}")

        return failed == 0

    def _print_result(self, result: StepResult) -> None:
        marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(result.status, "[????]")
        line = f"{marker} {result.step}"
        if result.http_status:
            line += f"  (HTTP {result.http_status})"
        if result.key_ids:
            ids = " ".join(f"{k}={v}" for k, v in result.key_ids.items())
            line += f"  [{ids}]"
        if result.status == "FAIL" or result.status == "SKIP":
            line += f"\n       reason: {result.message}"
        if result.status == "FAIL" and result.detail:
            line += f"\n       detail: {result.detail}"
        if self.verbose and result.status == "PASS" and result.detail:
            line += f"\n       detail: {result.detail}"
        print(line)

    # -- pgvector availability check --------------------------------------

    def _run_pgvector_check(self) -> bool:
        """Check pgvector extension availability on the configured database.

        Uses SQLAlchemy to connect via DATABASE_URL.  Safe for local SQLite:
        the check is skipped gracefully.
        """
        print("pgvector Availability Check")
        print(f"trace_id: {self.trace_id}")
        print()

        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            print("SKIP: DATABASE_URL is not set.")
            print("backend: unknown")
            print("pgvector_available: unknown (no DATABASE_URL)")
            print("extension_create_ok: unknown")
            print()
            print("next_action:")
            print("  Set DATABASE_URL to a Render PostgreSQL connection string")
            print("  or run this check from the Render shell / deployment environment.")
            print("  Example: SELECT * FROM pg_available_extensions WHERE name = 'vector';")
            return True  # not a failure — just not checkable locally

        try:
            from sqlalchemy import create_engine, text
        except ImportError:
            print("FAIL: SQLAlchemy is not installed.")
            print("  Install: pip install sqlalchemy")
            return False

        backend = "unknown"
        if database_url.startswith("postgresql") or database_url.startswith("postgres"):
            backend = "postgresql"
        elif database_url.startswith("sqlite"):
            backend = "sqlite"

        print(f"backend: {backend}")
        if backend != "postgresql":
            print("SKIP: pgvector is only relevant for PostgreSQL. Current backend is not PostgreSQL.")
            print("pgvector_available: n/a (not PostgreSQL)")
            print("extension_create_ok: n/a")
            print()
            print("next_action:")
            print("  Deploy to Render with a PostgreSQL DATABASE_URL to check pgvector support.")
            return True

        engine = None
        try:
            engine = create_engine(database_url, echo=False, connect_args={"connect_timeout": 10})
            with engine.connect() as conn:
                # Check if pgvector is available
                result = conn.execute(
                    text("SELECT * FROM pg_available_extensions WHERE name = 'vector';")
                )
                rows = result.fetchall()
                pgvector_available = len(rows) > 0
                print(f"pgvector_available: {pgvector_available}")

                extension_ok = False
                if pgvector_available:
                    try:
                        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                        conn.commit()
                        extension_ok = True
                    except Exception as exc:
                        print(f"extension_create_ok: false  (error: {exc})")
                    else:
                        print("extension_create_ok: true")

                if pgvector_available and extension_ok:
                    print()
                    print("next_action:")
                    print("  pgvector is available and enabled. Proceed with P1-M21 (Vector RAG Foundation).")
                elif pgvector_available:
                    print()
                    print("next_action:")
                    print("  pgvector is available but CREATE EXTENSION failed.")
                    print("  Check database user permissions (superuser or createextenion privilege needed).")
                    print("  Contact Render support or upgrade database plan if needed.")
                else:
                    print()
                    print("next_action:")
                    print("  pgvector is NOT available on this Render PostgreSQL instance.")
                    print("  P1-M21 (Vector RAG Foundation) is BLOCKED until pgvector is available.")
                    print("  Options:")
                    print("    1. Upgrade Render PostgreSQL plan if pgvector requires a higher tier.")
                    print("    2. Use an external vector store (ChromaDB, Pinecone free tier, etc.).")
                    print("    3. Re-evaluate whether vector RAG can be deferred to P2 with a different infra.")
                return pgvector_available and extension_ok
        except Exception as exc:
            print(f"FAIL: Could not connect to database or run pgvector check.")
            print(f"  error: {exc}")
            print(f"  Note: DATABASE_URL value is NOT printed (security).")
            print()
            print("next_action:")
            print("  Verify DATABASE_URL is correct and the database is reachable.")
            print("  Run the following SQL manually on Render PostgreSQL:")
            print("    SELECT * FROM pg_available_extensions WHERE name = 'vector';")
            print("    CREATE EXTENSION IF NOT EXISTS vector;")
            return False
        finally:
            if engine:
                engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P1 Pipeline Harness — one-command P1 data flow verification.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python scripts/run_p1_pipeline_harness.py
              python scripts/run_p1_pipeline_harness.py --base-url http://127.0.0.1:8000 --verbose
              python scripts/run_p1_pipeline_harness.py --base-url https://datahub-jr8x.onrender.com --stop-on-fail
              python scripts/run_p1_pipeline_harness.py --check-pgvector
        """),
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the DataHub FastAPI backend (default: http://127.0.0.1:8000)",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP request timeout in seconds (default: 30)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed response excerpts for each step")
    parser.add_argument("--stop-on-fail", action="store_true", help="Abort on first non-PASS step")
    parser.add_argument("--trace-id", default=None, help="Custom trace ID (auto-generated if not provided)")
    parser.add_argument(
        "--check-pgvector",
        action="store_true",
        help="Check pgvector extension availability instead of running the full pipeline",
    )

    args = parser.parse_args()

    harness = PipelineHarness(
        base_url=args.base_url,
        timeout=args.timeout,
        verbose=args.verbose,
        stop_on_fail=args.stop_on_fail,
        trace_id=args.trace_id,
    )

    ok = harness.run(check_pgvector=args.check_pgvector)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
