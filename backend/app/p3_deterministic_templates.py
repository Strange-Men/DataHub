"""Versioned, provider-free deterministic templates for P3 draft assets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ValidationError

from app.p3_asset_schemas import (
    ASSET_PAYLOAD_SCHEMAS,
    P3_DETERMINISTIC_TEMPLATE_VERSION,
    P3DeterministicAssetPayload,
    P3GenerationSourceMaterial,
    P3QaBankPayload,
    P3QaItem,
    P3ServiceResponseStep,
    P3ServiceScriptPayload,
    P3SftDatasetPayload,
    P3SftRecord,
    P3SopPayload,
    P3SopStep,
    P3TrainingMaterialPayload,
    P3TrainingSection,
)
from app.p3_reuse_models import ReuseAssetType


@dataclass(frozen=True)
class P3TemplateError(RuntimeError):
    code: str
    message: str
    template_key: str

    def __str__(self) -> str:
        return self.message


TemplateRenderer = Callable[
    [tuple[P3GenerationSourceMaterial, ...]],
    P3DeterministicAssetPayload,
]


@dataclass(frozen=True)
class P3DeterministicTemplate:
    template_key: str
    template_version: str
    asset_type: ReuseAssetType
    renderer: TemplateRenderer

    def render(
        self,
        materials: tuple[P3GenerationSourceMaterial, ...],
    ) -> dict[str, object]:
        if not materials:
            raise P3TemplateError(
                "P3_ASSET_TEMPLATE_INVALID",
                "A deterministic template requires governed source material.",
                self.template_key,
            )
        try:
            payload = self.renderer(materials)
            schema = ASSET_PAYLOAD_SCHEMAS[self.asset_type]
            validated: BaseModel = schema.model_validate(
                payload.model_dump(mode="json")
            )
        except (ValidationError, TypeError, ValueError, KeyError) as exc:
            raise P3TemplateError(
                "P3_ASSET_TEMPLATE_INVALID",
                "Deterministic template output is invalid.",
                self.template_key,
            ) from exc
        return validated.model_dump(mode="json")


def _refs(materials: tuple[P3GenerationSourceMaterial, ...]):
    return [material.source_ref for material in materials]


def _training_material(
    materials: tuple[P3GenerationSourceMaterial, ...],
) -> P3TrainingMaterialPayload:
    return P3TrainingMaterialPayload(
        title="审核知识培训资料",
        learning_objectives=[material.title for material in materials],
        sections=[
            P3TrainingSection(
                heading=material.title,
                content=material.approved_content,
                source_refs=[material.source_ref],
            )
            for material in materials
        ],
        key_points=[material.approved_content for material in materials],
        source_refs=_refs(materials),
    )


def _sop(
    materials: tuple[P3GenerationSourceMaterial, ...],
) -> P3SopPayload:
    return P3SopPayload(
        title="审核知识标准操作手册",
        purpose="依据审核通过的治理知识执行标准操作。",
        scope="本手册仅覆盖所引用的审核知识。",
        prerequisites=[],
        steps=[
            P3SopStep(
                order=index,
                instruction=material.approved_content,
                source_refs=[material.source_ref],
            )
            for index, material in enumerate(materials, start=1)
        ],
        cautions=[],
        escalation_rules=[],
        source_refs=_refs(materials),
    )


def _service_script(
    materials: tuple[P3GenerationSourceMaterial, ...],
) -> P3ServiceScriptPayload:
    return P3ServiceScriptPayload(
        title="审核知识客服标准话术",
        scenario=materials[0].title,
        opening="",
        response_steps=[
            P3ServiceResponseStep(
                order=index,
                response=material.approved_content,
                source_refs=[material.source_ref],
            )
            for index, material in enumerate(materials, start=1)
        ],
        prohibited_claims=[],
        escalation=[],
        source_refs=_refs(materials),
    )


def _qa_bank(
    materials: tuple[P3GenerationSourceMaterial, ...],
) -> P3QaBankPayload:
    return P3QaBankPayload(
        title="审核知识场景问答题库",
        items=[
            P3QaItem(
                question=material.title,
                answer=material.approved_content,
                source_refs=[material.source_ref],
            )
            for material in materials
        ],
        source_refs=_refs(materials),
    )


def _sft_dataset(
    materials: tuple[P3GenerationSourceMaterial, ...],
) -> P3SftDatasetPayload:
    return P3SftDatasetPayload(
        records=[
            P3SftRecord(
                instruction=material.title,
                input="",
                output=material.approved_content,
                metadata={
                    "source_type": material.source_type.value,
                    "source_version": material.source_version,
                },
                source_refs=[material.source_ref],
            )
            for material in materials
        ]
    )


_TEMPLATES = (
    P3DeterministicTemplate(
        "p3.training_material.v1",
        P3_DETERMINISTIC_TEMPLATE_VERSION,
        ReuseAssetType.TRAINING_MATERIAL,
        _training_material,
    ),
    P3DeterministicTemplate(
        "p3.sop.v1",
        P3_DETERMINISTIC_TEMPLATE_VERSION,
        ReuseAssetType.SOP,
        _sop,
    ),
    P3DeterministicTemplate(
        "p3.service_script.v1",
        P3_DETERMINISTIC_TEMPLATE_VERSION,
        ReuseAssetType.SERVICE_SCRIPT,
        _service_script,
    ),
    P3DeterministicTemplate(
        "p3.qa_bank.v1",
        P3_DETERMINISTIC_TEMPLATE_VERSION,
        ReuseAssetType.QA_BANK,
        _qa_bank,
    ),
    P3DeterministicTemplate(
        "p3.sft_dataset.v1",
        P3_DETERMINISTIC_TEMPLATE_VERSION,
        ReuseAssetType.SFT_DATASET,
        _sft_dataset,
    ),
)
TEMPLATE_REGISTRY = {template.template_key: template for template in _TEMPLATES}
DEFAULT_TEMPLATE_KEYS = {
    template.asset_type: template.template_key for template in _TEMPLATES
}


def get_deterministic_template(
    asset_type: ReuseAssetType,
    template_key: str | None = None,
) -> P3DeterministicTemplate:
    key = template_key or DEFAULT_TEMPLATE_KEYS.get(asset_type)
    template = TEMPLATE_REGISTRY.get(str(key or ""))
    if template is None:
        raise P3TemplateError(
            "P3_ASSET_TEMPLATE_NOT_FOUND",
            "Deterministic template was not found.",
            str(key or ""),
        )
    if template.asset_type is not asset_type:
        raise P3TemplateError(
            "P3_ASSET_TEMPLATE_INVALID",
            "Deterministic template does not match the requested asset type.",
            template.template_key,
        )
    return template


__all__ = [
    "DEFAULT_TEMPLATE_KEYS",
    "P3DeterministicTemplate",
    "P3TemplateError",
    "TEMPLATE_REGISTRY",
    "get_deterministic_template",
]
