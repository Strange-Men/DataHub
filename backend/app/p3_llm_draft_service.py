"""Governed orchestration for optional LLM-assisted P3 draft generation."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app import p3_asset_repositories as asset_repositories
from app.p3_asset_service import (
    P3AssetService,
    P3AssetServiceError,
    _asset_type,
    _repository_call,
    _snapshot_input,
    build_source_manifest,
)
from app.p3_llm_draft_contract import (
    OpenAICompatibleP3LLMDraftProvider,
    P3LLMDraftError,
    P3LLMDraftProvider,
    P3LLMDraftProviderRequest,
    P3LLMDraftSettings,
    validate_context_budget,
)
from app.p3_llm_prompt_registry import (
    get_llm_prompt,
    validate_and_ground_llm_output,
)
from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProjectStatus,
)
from app.p3_reuse_service import P3ServiceError
from app.p3_source_material_reader import (
    P3SourceMaterialReadError,
    read_generation_source_materials,
)


_MODEL_PARAMETERS = {"temperature": 0}


def _error(
    code: str,
    message: str,
    **context: str,
) -> P3AssetServiceError:
    return P3AssetServiceError(code, message, context)


def _identity_text(value: object, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(
            "P3_LLM_PROVIDER_NOT_CONFIGURED",
            f"{field} is not configured.",
        )
    normalized = value.strip()
    if len(normalized) > max_length:
        raise _error(
            "P3_LLM_PROVIDER_NOT_CONFIGURED",
            f"{field} exceeds the safe identity limit.",
        )
    return normalized


def _request_identity(
    *,
    prompt_key: str,
    provider_profile: str,
    model_alias: str,
    model_parameters: dict[str, object],
) -> str:
    canonical_parameters = json.dumps(
        model_parameters,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    parameters_hash = hashlib.sha256(
        canonical_parameters.encode("utf-8")
    ).hexdigest()[:16]
    identity = (
        f"llm|prompt={prompt_key}|provider={provider_profile}|"
        f"model={model_alias}|config={parameters_hash}"
    )
    if len(identity) > 200:
        raise _error(
            "P3_LLM_PROVIDER_NOT_CONFIGURED",
            "P3 LLM provider identity exceeds the storage limit.",
        )
    return identity


class P3LLMDraftService(P3AssetService):
    """Create immutable LLM draft attempts using existing M1/M2/M3 gates."""

    def __init__(
        self,
        db: Session,
        *,
        provider: P3LLMDraftProvider | None = None,
        settings: P3LLMDraftSettings | None = None,
    ) -> None:
        super().__init__(db)
        self.settings = settings or P3LLMDraftSettings.from_environment()
        self.provider = provider

    def _resolve_provider(
        self,
        requested_profile: str | None,
    ) -> tuple[P3LLMDraftProvider, str, str]:
        self.settings.require_enabled()
        provider = self.provider
        if provider is None:
            self.settings.require_provider_configuration()
            provider = OpenAICompatibleP3LLMDraftProvider(self.settings)
        profile = _identity_text(
            provider.provider_profile,
            "provider_profile",
            50,
        )
        model_alias = _identity_text(provider.model_alias, "model_alias", 100)
        if requested_profile is not None:
            requested = _identity_text(
                requested_profile,
                "provider_profile",
                50,
            )
            if requested != profile:
                raise _error(
                    "P3_LLM_PROVIDER_NOT_CONFIGURED",
                    "Requested P3 LLM provider profile is unavailable.",
                )
        return provider, profile, model_alias

    @staticmethod
    def _check_llm_replay(
        row: ReuseAssetVersion,
        *,
        project_id: str,
        asset_type: ReuseAssetType,
        request_identity: str,
        prompt_version: str,
        source_manifest_hash: str,
        actor_role: str,
    ) -> ReuseAssetVersion:
        if any(
            (
                row.project_id != project_id,
                row.asset_type is not asset_type,
                row.generation_mode is not ReuseGenerationMode.LLM_DRAFT,
                row.template_key != request_identity,
                row.template_version != prompt_version,
                row.source_manifest_hash != source_manifest_hash,
                row.created_by_role != actor_role,
            )
        ):
            raise _error(
                "P3_ASSET_IDEMPOTENCY_CONFLICT",
                "Idempotency key is bound to a different LLM draft request.",
                asset_version_id=row.id,
            )
        if row.status in {
            ReuseAssetVersionStatus.GENERATED,
            ReuseAssetVersionStatus.FAILED,
        }:
            return row
        raise _error(
            "P3_ASSET_IDEMPOTENCY_CONFLICT",
            "The idempotent LLM draft attempt is still in progress.",
            asset_version_id=row.id,
        )

    def _safe_mark_failed(
        self,
        version: ReuseAssetVersion,
        error: P3AssetServiceError,
    ) -> None:
        self._mark_failed(version, code=error.code, message=error.message)

    def generate_llm_draft(
        self,
        *,
        project_id: str,
        asset_type: ReuseAssetType,
        prompt_key: str | None,
        provider_profile: str | None,
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> ReuseAssetVersion:
        normalized_type = _asset_type(asset_type)
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise _error(
                "P3_ASSET_VALIDATION_ERROR",
                "idempotency_key must not be blank.",
            )
        try:
            provider, profile, model_alias = self._resolve_provider(
                provider_profile
            )
            prompt = get_llm_prompt(normalized_type, prompt_key)
        except P3LLMDraftError as exc:
            raise _error(exc.code, exc.message) from exc

        model_parameters = {
            **_MODEL_PARAMETERS,
            "max_output_tokens": self.settings.max_output_tokens,
        }
        request_identity = _request_identity(
            prompt_key=prompt.prompt_key,
            provider_profile=profile,
            model_alias=model_alias,
            model_parameters=model_parameters,
        )
        try:
            project = self.reuse_service.get_project(project_id)
            sources = self._project_sources(project.id)
        except P3AssetServiceError:
            raise
        except P3ServiceError as exc:
            raise _error(
                "P3_ASSET_PROJECT_NOT_FOUND",
                "Reuse project was not found.",
                project_id=project_id,
            ) from exc
        _manifest, manifest_hash = build_source_manifest(sources)
        existing = self._existing_by_idempotency_key(idempotency_key.strip())
        if existing is not None:
            return self._check_llm_replay(
                existing,
                project_id=project.id,
                asset_type=normalized_type,
                request_identity=request_identity,
                prompt_version=prompt.prompt_version,
                source_manifest_hash=manifest_hash,
                actor_role=actor_role,
            )
        if project.status is not ReuseProjectStatus.ACTIVE:
            raise _error(
                "P3_ASSET_PROJECT_NOT_ACTIVE",
                "Only active reuse projects may generate LLM drafts.",
                project_id=project.id,
                project_status=project.status.value,
            )

        self._revalidate_sources(project.id, sources)
        try:
            materials = read_generation_source_materials(self.db, sources)
        except P3SourceMaterialReadError as exc:
            raise _error(
                exc.code,
                exc.message,
                project_id=project.id,
                source_item_id=exc.source_item_id,
            ) from exc
        materials.sort(
            key=lambda material: (
                material.source_type.value,
                material.source_id,
                material.source_version or 0,
                material.source_item_id,
            )
        )
        try:
            validate_context_budget(tuple(materials), self.settings)
        except P3LLMDraftError as exc:
            raise _error(exc.code, exc.message, project_id=project.id) from exc

        snapshots = tuple(_snapshot_input(source) for source in sources)
        version = _repository_call(
            asset_repositories.create_asset_version_with_source_snapshots,
            self.db,
            project_id=project.id,
            asset_type=normalized_type,
            generation_mode=ReuseGenerationMode.LLM_DRAFT,
            template_key=request_identity,
            template_version=prompt.prompt_version,
            source_manifest_hash=manifest_hash,
            idempotency_key=idempotency_key.strip(),
            created_by_role=actor_role,
            request_id=request_id,
            source_snapshots=snapshots,
            context={"project_id": project.id},
        )
        if version.status in {
            ReuseAssetVersionStatus.GENERATED,
            ReuseAssetVersionStatus.FAILED,
        }:
            return version

        provider_request = P3LLMDraftProviderRequest(
            asset_type=normalized_type,
            prompt_key=prompt.prompt_key,
            prompt_version=prompt.prompt_version,
            source_manifest_hash=manifest_hash,
            source_materials=tuple(materials),
            response_schema=prompt.output_schema,
            model_parameters=model_parameters,
            messages=prompt.build_messages(tuple(materials)),
        )
        try:
            result = provider.generate_structured_draft(provider_request)
            if (
                result.provider_profile != profile
                or result.model_alias != model_alias
            ):
                raise P3LLMDraftError(
                    "P3_LLM_GENERATION_FAILED",
                    "P3 LLM provider identity changed during generation.",
                )
            self._revalidate_sources(project.id, sources)
            current_sources = self._project_sources(project.id)
            _current_manifest, current_manifest_hash = build_source_manifest(
                current_sources
            )
            payload = validate_and_ground_llm_output(
                asset_type=normalized_type,
                provider_payload=result.parsed_payload,
                allowed_refs=tuple(
                    material.source_ref for material in materials
                ),
                expected_source_manifest_hash=manifest_hash,
                current_source_manifest_hash=current_manifest_hash,
                max_output_chars=self.settings.max_output_chars,
            )
            return _repository_call(
                asset_repositories.mark_asset_generated,
                self.db,
                version.id,
                content_payload=payload,
                conflict_code="P3_LLM_GENERATION_FAILED",
                context={"asset_version_id": version.id},
            )
        except P3LLMDraftError as exc:
            service_error = _error(
                exc.code,
                exc.message,
                asset_version_id=version.id,
            )
            self._safe_mark_failed(version, service_error)
            raise service_error from exc
        except P3AssetServiceError as exc:
            self._safe_mark_failed(version, exc)
            raise
        except Exception as exc:
            service_error = _error(
                "P3_LLM_GENERATION_FAILED",
                "Governed P3 LLM draft generation failed.",
                asset_version_id=version.id,
            )
            self._safe_mark_failed(version, service_error)
            raise service_error from exc


__all__ = ["P3LLMDraftService"]
