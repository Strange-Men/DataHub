"""P2-M2 orchestration for extraction jobs and versioned results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.asset_repositories import get_asset
from app.extraction_providers import (
    ExtractionContext,
    ExtractionOutput,
    ExtractionProvider,
    ExtractionProviderError,
)
from app.extraction_repositories import (
    create_asset_extraction,
    create_extraction_job,
    get_extraction_job,
    update_extraction_job,
)
from app.extraction_schemas import AssetExtractionRecord, ExtractionJobRecord


SUPPORTED_EXTRACTION_TYPES = frozenset({"ocr", "caption", "metadata"})


class ExtractionAssetNotFoundError(RuntimeError):
    pass


class ExtractionJobNotFoundError(RuntimeError):
    pass


class ExtractionStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractionExecution:
    job: ExtractionJobRecord
    result: AssetExtractionRecord | None


class ExtractionService:
    """Owns job creation, state transitions, provider execution, and results."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_job(
        self,
        *,
        asset_id: str,
        extract_type: str,
        provider: ExtractionProvider,
    ) -> ExtractionJobRecord:
        if get_asset(self.db, asset_id) is None:
            raise ExtractionAssetNotFoundError(asset_id)
        normalized_type = extract_type.strip().lower()
        if normalized_type not in SUPPORTED_EXTRACTION_TYPES:
            raise ExtractionStateError("Unsupported extraction type.")
        return create_extraction_job(
            self.db,
            asset_id=asset_id,
            extract_type=normalized_type,
            provider=provider.provider_name,
        )

    def execute_job(
        self,
        job_id: str,
        provider: ExtractionProvider,
    ) -> ExtractionExecution:
        job = get_extraction_job(self.db, job_id)
        if job is None:
            raise ExtractionJobNotFoundError(job_id)
        if job.status not in {"pending", "retrying"}:
            raise ExtractionStateError(
                f"Extraction job in '{job.status}' state cannot be executed."
            )
        if provider.provider_name != job.provider:
            raise ExtractionStateError("Retry provider must match the original job provider.")
        asset = get_asset(self.db, job.asset_id)
        if asset is None:
            raise ExtractionAssetNotFoundError(job.asset_id)

        running = update_extraction_job(
            self.db,
            job.id,
            status="running",
            retry_count=job.retry_count,
            error_message=None,
            started_at=datetime.now(UTC),
            clear_completed_at=True,
        )
        try:
            output = provider.extract(
                ExtractionContext(
                    job_id=running.id,
                    extract_type=running.extract_type,
                    asset=asset,
                )
            )
            self._validate_output(output)
            result = create_asset_extraction(
                self.db,
                asset_id=running.asset_id,
                job_id=running.id,
                extract_type=running.extract_type,
                content=output.content,
                metadata_json={
                    **output.metadata,
                    "provider": provider.provider_name,
                    "mock_execution": provider.provider_name == "mock",
                },
            )
        except ExtractionProviderError as exc:
            return self._mark_failed(running, str(exc))
        except Exception:
            return self._mark_failed(running, "Extraction execution failed.")

        completed = update_extraction_job(
            self.db,
            running.id,
            status="success",
            retry_count=running.retry_count,
            error_message=None,
            completed_at=datetime.now(UTC),
        )
        return ExtractionExecution(job=completed, result=result)

    def create_and_execute(
        self,
        *,
        asset_id: str,
        extract_type: str,
        provider: ExtractionProvider,
    ) -> ExtractionExecution:
        job = self.create_job(
            asset_id=asset_id,
            extract_type=extract_type,
            provider=provider,
        )
        return self.execute_job(job.id, provider)

    def retry_job(
        self,
        job_id: str,
        provider: ExtractionProvider,
    ) -> ExtractionExecution:
        job = get_extraction_job(self.db, job_id)
        if job is None:
            raise ExtractionJobNotFoundError(job_id)
        if job.status != "failed":
            raise ExtractionStateError("Only failed extraction jobs can be retried.")
        if provider.provider_name != job.provider:
            raise ExtractionStateError("Retry provider must match the original job provider.")
        retrying = update_extraction_job(
            self.db,
            job.id,
            status="retrying",
            retry_count=job.retry_count + 1,
            error_message=None,
            clear_completed_at=True,
        )
        return self.execute_job(retrying.id, provider)

    @staticmethod
    def _validate_output(output: ExtractionOutput) -> None:
        if not isinstance(output.content, str) or not output.content.strip():
            raise ExtractionProviderError("Extraction provider returned empty content.")
        if not isinstance(output.metadata, dict):
            raise ExtractionProviderError("Extraction provider returned invalid metadata.")

    def _mark_failed(
        self,
        job: ExtractionJobRecord,
        message: str,
    ) -> ExtractionExecution:
        safe_message = (message.strip() or "Extraction execution failed.")[:1000]
        failed = update_extraction_job(
            self.db,
            job.id,
            status="failed",
            retry_count=job.retry_count,
            error_message=safe_message,
            completed_at=datetime.now(UTC),
        )
        return ExtractionExecution(job=failed, result=None)
