"""Focused P3-M1.1 tests for deterministic, read-only source eligibility."""

from __future__ import annotations

import inspect
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import p3_source_eligibility as eligibility_module  # noqa: E402
from app.database import Base  # noqa: E402
from app.db_models import (  # noqa: E402
    Asset,
    AssetExtraction,
    AssetReviewSnapshot,
    BadCase,
    ExtractionJob,
    ExtractionReview,
    KnowledgeAsset,
    KnowledgeCandidate,
    P2KnowledgeIndexEntry,
    ReviewRecord,
)
from app.p3_source_eligibility import (  # noqa: E402
    check_source_eligibility,
    check_sources_eligibility,
)
from app.p3_source_eligibility_schemas import (  # noqa: E402
    P3SourceEligibilityReason,
    P3SourceReference,
    P3SourceType,
)


class P3SourceEligibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=cls.engine,
        )
        Base.metadata.create_all(bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        self.db = self.SessionLocal()
        for model in (
            P2KnowledgeIndexEntry,
            KnowledgeAsset,
            AssetReviewSnapshot,
            ExtractionReview,
            AssetExtraction,
            ExtractionJob,
            Asset,
            ReviewRecord,
            KnowledgeCandidate,
            BadCase,
        ):
            self.db.query(model).delete()
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def _p1_reference(
        self,
        candidate_id: str,
        source_type: P3SourceType = P3SourceType.P1_KNOWLEDGE,
        **updates: object,
    ) -> P3SourceReference:
        values: dict[str, object] = {
            "source_type": source_type,
            "source_id": candidate_id,
        }
        values.update(updates)
        return P3SourceReference.model_validate(values)

    def _add_p1(
        self,
        *,
        candidate_id: str = "candidate_p1",
        status: str = "approved",
        review_action: str = "approved",
        source_type: str = "sanitized_batch",
        include_review: bool = True,
        include_snapshot: bool = True,
        trace_complete: bool = True,
        drift: bool = False,
    ) -> KnowledgeCandidate:
        metadata = {
            "source_batch_id": "batch_p1",
            "source_bad_case_id": "bad_case_p1" if source_type == "bad_case" else None,
            "source_retrieval_id": "retrieval_p1" if source_type == "bad_case" else None,
            "source_chunk_ids": ["chunk_p1"] if source_type == "bad_case" else [],
            "knowledge_type": "faq",
        }
        candidate = KnowledgeCandidate(
            id=candidate_id,
            source_type=source_type,
            source_id=(
                "bad_case_p1" if source_type == "bad_case" else "batch_p1"
            ),
            question="How long does shipping take?",
            answer="Shipping takes five business days." if not drift else "Changed answer.",
            intent="shipping",
            tags=["shipping", "policy"],
            risk_level="low",
            quality_score=0.95,
            status=status,
            metadata_json=metadata,
        )
        self.db.add(candidate)
        if include_review:
            snapshot = None
            if include_snapshot:
                snapshot = {
                    "candidate_id": candidate_id,
                    "source_type": source_type,
                    "source_batch_id": (
                        "batch_p1" if trace_complete and source_type != "bad_case" else None
                    ),
                    "source_bad_case_id": (
                        "bad_case_p1" if trace_complete and source_type == "bad_case" else None
                    ),
                    "source_retrieval_id": (
                        "retrieval_p1" if source_type == "bad_case" else None
                    ),
                    "source_chunk_ids": ["chunk_p1"] if source_type == "bad_case" else [],
                    "knowledge_type": "faq",
                    "question": "How long does shipping take?",
                    "answer": "Shipping takes five business days.",
                    "intent": "shipping",
                    "tags": ["policy", "shipping"],
                    "risk_level": "low",
                }
            self.db.add(
                ReviewRecord(
                    id=f"review_{candidate_id}",
                    candidate_id=candidate_id,
                    reviewer="reviewer",
                    action=review_action,
                    snapshot_json=snapshot,
                )
            )
        if source_type == "bad_case":
            self.db.add(
                BadCase(
                    id="bad_case_p1",
                    retrieval_id="retrieval_p1",
                    user_question="Original question",
                    bad_answer="Original bad answer",
                    expected_answer="Corrected answer",
                    status="resolved",
                    created_candidate_id=candidate_id,
                    metadata_json={"linked_chunk_ids": ["chunk_p1"]},
                )
            )
        self.db.commit()
        return candidate

    def _add_p2(
        self,
        *,
        knowledge_asset_id: str = "knowledge_p2",
        version: int = 1,
        status: str = "active",
        review_status: str = "approved",
        include_snapshot: bool = True,
        index_status: str | None = None,
        content: str = "Approved governed content.",
        suffix: str = "v1",
    ) -> KnowledgeAsset:
        asset_id = "asset_p2"
        job_id = f"job_{suffix}"
        extraction_id = f"extraction_{suffix}"
        review_id = f"review_{suffix}"
        snapshot_id = f"snapshot_{suffix}"
        if self.db.query(Asset).filter(Asset.id == asset_id).first() is None:
            self.db.add(
                Asset(
                    id=asset_id,
                    asset_type="image",
                    file_name="governed.png",
                    mime_type="image/png",
                    size=128,
                    storage_uri="local://redacted/governed.png",
                    hash="a" * 64,
                    status="uploaded",
                    metadata_json={},
                )
            )
        self.db.add(
            ExtractionJob(
                id=job_id,
                asset_id=asset_id,
                extract_type="ocr",
                provider="mock",
                status="success",
                retry_count=0,
            )
        )
        self.db.add(
            AssetExtraction(
                id=extraction_id,
                asset_id=asset_id,
                job_id=job_id,
                extract_type="ocr",
                content="Machine content.",
                metadata_json={"mock": True},
                version=version,
            )
        )
        self.db.add(
            ExtractionReview(
                id=review_id,
                asset_id=asset_id,
                extraction_id=extraction_id,
                review_status=review_status,
                reviewer="reviewer",
                original_content="Machine content.",
                revised_content="Approved governed content.",
                version=version,
            )
        )
        if include_snapshot:
            self.db.add(
                AssetReviewSnapshot(
                    id=snapshot_id,
                    asset_id=asset_id,
                    extraction_id=extraction_id,
                    review_id=review_id,
                    extract_type="ocr",
                    original_content="Machine content.",
                    approved_content="Approved governed content.",
                    metadata_json={"immutable": True},
                    version=version,
                )
            )
        knowledge = KnowledgeAsset(
            id=knowledge_asset_id,
            source_snapshot_id=snapshot_id,
            asset_id=asset_id,
            content=content,
            content_type="ocr",
            status=status,
            version=version,
            metadata_json={},
        )
        self.db.add(knowledge)
        if index_status is not None:
            self.db.add(
                P2KnowledgeIndexEntry(
                    id=f"index_{suffix}",
                    knowledge_asset_id=knowledge_asset_id,
                    status=index_status,
                    generation=1,
                    fingerprint=f"{suffix:0<64}"[:64],
                    sync_state=index_status,
                )
            )
        self.db.commit()
        return knowledge

    def test_p1_approved_matching_fingerprint_is_eligible(self) -> None:
        self._add_p1()
        decision = check_source_eligibility(
            self.db,
            self._p1_reference("candidate_p1"),
        )
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.reason_code, P3SourceEligibilityReason.ELIGIBLE)
        self.assertEqual(decision.approved_review_id, "review_candidate_p1")

    def test_p1_pending_is_not_approved(self) -> None:
        self._add_p1(status="pending_review")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference("candidate_p1"),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_NOT_APPROVED,
        )

    def test_p1_rejected_is_not_approved(self) -> None:
        self._add_p1(status="rejected", review_action="rejected")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference("candidate_p1"),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_NOT_APPROVED,
        )

    def test_p1_fingerprint_drift_is_rejected(self) -> None:
        self._add_p1(drift=True)
        decision = check_source_eligibility(
            self.db,
            self._p1_reference("candidate_p1"),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH,
        )

    def test_p1_missing_source_is_not_found(self) -> None:
        decision = check_source_eligibility(
            self.db,
            self._p1_reference("missing_candidate"),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_NOT_FOUND,
        )

    def test_p1_incomplete_trace_is_rejected(self) -> None:
        self._add_p1(trace_complete=False)
        decision = check_source_eligibility(
            self.db,
            self._p1_reference("candidate_p1"),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
        )
        self.assertFalse(decision.lineage_complete)

    def test_p2_approved_active_current_snapshot_is_eligible(self) -> None:
        self._add_p2()
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertEqual(decision.reason_code, P3SourceEligibilityReason.ELIGIBLE)
        self.assertEqual(decision.snapshot_id, "snapshot_v1")
        self.assertEqual(decision.knowledge_asset_id, "knowledge_p2")

    def test_p2_ready_not_serving_is_eligible(self) -> None:
        self._add_p2(index_status="ready")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertTrue(decision.eligible)
        self.assertIn("INDEX_STATUS_OBSERVED:ready", decision.checked_conditions)

    def test_p2_serving_is_eligible(self) -> None:
        self._add_p2(index_status="serving")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertTrue(decision.eligible)
        self.assertIn("INDEX_STATUS_OBSERVED:serving", decision.checked_conditions)

    def test_p2_archived_is_rejected(self) -> None:
        self._add_p2(status="archived")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_ARCHIVED,
        )

    def test_p2_superseded_is_rejected(self) -> None:
        self._add_p2(status="superseded")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_SUPERSEDED,
        )

    def test_p2_old_active_version_is_not_current(self) -> None:
        self._add_p2(knowledge_asset_id="knowledge_p2_v1")
        self._add_p2(
            knowledge_asset_id="knowledge_p2_v2",
            version=2,
            suffix="v2",
        )
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2_v1",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_NOT_CURRENT,
        )

    def test_p2_unapproved_review_is_rejected(self) -> None:
        self._add_p2(review_status="pending")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_NOT_APPROVED,
        )

    def test_p2_missing_snapshot_is_incomplete_trace(self) -> None:
        self._add_p2(include_snapshot=False)
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE,
        )

    def test_raw_bad_case_is_never_a_legal_source(self) -> None:
        decision = check_source_eligibility(
            self.db,
            {"source_type": "RAW_BAD_CASE", "source_id": "bad_case_p1"},
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.RAW_BAD_CASE_NOT_ALLOWED,
        )

    def test_approved_bad_case_correction_is_eligible(self) -> None:
        self._add_p1(source_type="bad_case")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "candidate_p1",
                P3SourceType.APPROVED_BAD_CASE_CORRECTION,
            ),
        )
        self.assertEqual(decision.reason_code, P3SourceEligibilityReason.ELIGIBLE)

    def test_unapproved_bad_case_correction_is_rejected(self) -> None:
        self._add_p1(source_type="bad_case", status="pending_review")
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "candidate_p1",
                P3SourceType.APPROVED_BAD_CASE_CORRECTION,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.BAD_CASE_CORRECTION_NOT_APPROVED,
        )

    def test_bad_case_correction_fingerprint_drift_is_rejected(self) -> None:
        self._add_p1(source_type="bad_case", drift=True)
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "candidate_p1",
                P3SourceType.APPROVED_BAD_CASE_CORRECTION,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH,
        )

    def test_bad_case_candidate_cannot_bypass_correction_link_check(self) -> None:
        self._add_p1(source_type="bad_case")
        bad_case = self.db.query(BadCase).filter(BadCase.id == "bad_case_p1").one()
        bad_case.status = "open"
        self.db.commit()
        decision = check_source_eligibility(
            self.db,
            self._p1_reference("candidate_p1"),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.BAD_CASE_CORRECTION_NOT_APPROVED,
        )

    def test_unsupported_source_type_fails_safely(self) -> None:
        decision = check_source_eligibility(
            self.db,
            {"source_type": "P3_ASSET", "source_id": "unsupported"},
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_TYPE_UNSUPPORTED,
        )

    def test_decision_process_performs_zero_writes(self) -> None:
        self._add_p1()
        write_statements: list[str] = []

        def capture_write(
            _conn: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            command = statement.lstrip().split(maxsplit=1)[0].upper()
            if command not in {"SELECT", "PRAGMA"}:
                write_statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", capture_write)
        try:
            check_source_eligibility(
                self.db,
                self._p1_reference("candidate_p1"),
            )
        finally:
            event.remove(self.engine, "before_cursor_execute", capture_write)
        self.assertEqual(write_statements, [])

    def test_decision_does_not_call_provider_embedding_or_network(self) -> None:
        self._add_p1()
        module_source = inspect.getsource(eligibility_module).lower()
        for forbidden_import in (
            "app.embedding",
            "app.extraction_providers",
            "openai",
            "requests",
            "httpx",
        ):
            self.assertNotIn(forbidden_import, module_source)
        with patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("network call is forbidden"),
        ):
            decision = check_source_eligibility(
                self.db,
                self._p1_reference("candidate_p1"),
            )
        self.assertTrue(decision.eligible)

    def test_batch_preserves_input_order(self) -> None:
        self._add_p1()
        self._add_p2()
        decisions = check_sources_eligibility(
            self.db,
            [
                self._p1_reference("candidate_p1"),
                self._p1_reference(
                    "knowledge_p2",
                    P3SourceType.P2_KNOWLEDGE_ASSET,
                ),
                {"source_type": "RAW_BAD_CASE", "source_id": "bad_case_p1"},
            ],
        )
        self.assertEqual(
            [decision.source_id for decision in decisions],
            ["candidate_p1", "knowledge_p2", "bad_case_p1"],
        )

    def test_repeated_checks_are_deterministic(self) -> None:
        self._add_p1()
        reference = self._p1_reference("candidate_p1")
        first = check_source_eligibility(self.db, reference)
        second = check_source_eligibility(self.db, reference)
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_decision_does_not_return_vector_secret_or_raw_content(self) -> None:
        self._add_p2()
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "knowledge_p2",
                P3SourceType.P2_KNOWLEDGE_ASSET,
            ),
        )
        serialized = decision.model_dump_json().lower()
        for forbidden in (
            "embedding",
            "secret",
            "storage_uri",
            "approved governed content",
            "machine content",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_expected_fingerprint_guard_rejects_mismatch(self) -> None:
        self._add_p1()
        decision = check_source_eligibility(
            self.db,
            self._p1_reference(
                "candidate_p1",
                expected_fingerprint="0" * 64,
            ),
        )
        self.assertEqual(
            decision.reason_code,
            P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH,
        )


if __name__ == "__main__":
    unittest.main()
