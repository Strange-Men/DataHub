"""Provider-neutral contract and safe configuration for P3 LLM drafts."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

from app.p3_asset_schemas import P3GenerationSourceMaterial
from app.p3_deterministic_templates import get_deterministic_template
from app.p3_reuse_models import ReuseAssetType


P3_LLM_DEFAULT_MAX_OUTPUT_CHARS = 200_000


P3_LLM_ERROR_CODES = frozenset(
    {
        "P3_LLM_DRAFT_DISABLED",
        "P3_LLM_PROVIDER_NOT_CONFIGURED",
        "P3_LLM_CONTEXT_LIMIT_EXCEEDED",
        "P3_LLM_PROVIDER_TIMEOUT",
        "P3_LLM_PROVIDER_UNAVAILABLE",
        "P3_LLM_OUTPUT_INVALID_JSON",
        "P3_LLM_OUTPUT_SCHEMA_INVALID",
        "P3_LLM_UNKNOWN_SOURCE_REF",
        "P3_LLM_GROUNDING_INCOMPLETE",
        "P3_LLM_OUTPUT_TOO_LARGE",
        "P3_LLM_GENERATION_FAILED",
    }
)


@dataclass(frozen=True)
class P3LLMDraftError(RuntimeError):
    code: str
    message: str

    def __post_init__(self) -> None:
        if self.code not in P3_LLM_ERROR_CODES:
            raise ValueError("Unknown P3 LLM draft error code.")

    def __str__(self) -> str:
        return self.message


def _error(code: str, message: str) -> P3LLMDraftError:
    return P3LLMDraftError(code, message)


def _bounded_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise _error(
            "P3_LLM_PROVIDER_NOT_CONFIGURED",
            f"{name} must be an integer.",
        ) from exc
    if value < minimum or value > maximum:
        raise _error(
            "P3_LLM_PROVIDER_NOT_CONFIGURED",
            f"{name} must be between {minimum} and {maximum}.",
        )
    return value


def _enabled_from_environment() -> bool:
    value = os.getenv("P3_LLM_DRAFT_ENABLED", "false").strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off", ""}:
        return False
    raise _error(
        "P3_LLM_PROVIDER_NOT_CONFIGURED",
        "P3_LLM_DRAFT_ENABLED must be true or false.",
    )


@dataclass(frozen=True)
class P3LLMDraftSettings:
    enabled: bool
    provider_profile: str
    base_url: str
    model_alias: str
    api_key: str = field(repr=False)
    max_source_count: int
    max_context_chars: int
    max_output_chars: int
    max_output_tokens: int
    timeout_seconds: int

    @classmethod
    def from_environment(cls) -> "P3LLMDraftSettings":
        return cls(
            enabled=_enabled_from_environment(),
            provider_profile=(
                os.getenv("P3_LLM_PROVIDER_PROFILE", "openai_compatible").strip()
                or "openai_compatible"
            ),
            base_url=os.getenv("P3_LLM_BASE_URL", "").strip(),
            model_alias=os.getenv("P3_LLM_MODEL", "").strip(),
            api_key=os.getenv("P3_LLM_API_KEY", "").strip(),
            max_source_count=_bounded_int(
                "P3_LLM_MAX_SOURCE_COUNT",
                100,
                minimum=1,
                maximum=100,
            ),
            max_context_chars=_bounded_int(
                "P3_LLM_MAX_CONTEXT_CHARS",
                80_000,
                minimum=1_000,
                maximum=1_000_000,
            ),
            max_output_chars=_bounded_int(
                "P3_LLM_MAX_OUTPUT_CHARS",
                P3_LLM_DEFAULT_MAX_OUTPUT_CHARS,
                minimum=1_000,
                maximum=1_000_000,
            ),
            max_output_tokens=_bounded_int(
                "P3_LLM_MAX_OUTPUT_TOKENS",
                4_096,
                minimum=1,
                maximum=65_536,
            ),
            timeout_seconds=_bounded_int(
                "P3_LLM_TIMEOUT_SECONDS",
                120,
                minimum=1,
                maximum=300,
            ),
        )

    def require_enabled(self) -> None:
        if not self.enabled:
            raise _error(
                "P3_LLM_DRAFT_DISABLED",
                "Governed LLM draft generation is disabled.",
            )

    def require_provider_configuration(self) -> None:
        if self.provider_profile != "openai_compatible":
            raise _error(
                "P3_LLM_PROVIDER_NOT_CONFIGURED",
                "Configured P3 LLM provider profile is unsupported.",
            )
        if not self.base_url or not self.model_alias or not self.api_key:
            raise _error(
                "P3_LLM_PROVIDER_NOT_CONFIGURED",
                "P3 LLM provider configuration is incomplete.",
            )


@dataclass(frozen=True)
class P3LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class P3LLMDraftProviderRequest:
    asset_type: ReuseAssetType
    prompt_key: str
    prompt_version: str
    source_manifest_hash: str
    source_materials: tuple[P3GenerationSourceMaterial, ...]
    response_schema: dict[str, object]
    model_parameters: Mapping[str, object]
    messages: tuple[P3LLMMessage, ...]


@dataclass(frozen=True)
class P3LLMDraftProviderResult:
    parsed_payload: object
    provider_profile: str
    model_alias: str
    usage_summary: Mapping[str, int] | None = None
    finish_reason: str | None = None


@runtime_checkable
class P3LLMDraftProvider(Protocol):
    @property
    def provider_profile(self) -> str:
        """Stable non-secret provider profile name."""

    @property
    def model_alias(self) -> str:
        """Stable configured model alias."""

    def generate_structured_draft(
        self,
        request: P3LLMDraftProviderRequest,
    ) -> P3LLMDraftProviderResult:
        """Generate one structured draft without persisting it."""


class OpenAICompatibleP3LLMDraftProvider:
    """Minimal adapter; credentials remain in memory and are never serialized."""

    def __init__(self, settings: P3LLMDraftSettings) -> None:
        settings.require_provider_configuration()
        self._base_url = settings.base_url.rstrip("/")
        self._model_alias = settings.model_alias
        self._api_key = settings.api_key
        self._timeout_seconds = settings.timeout_seconds
        self._max_output_tokens = settings.max_output_tokens

    @property
    def provider_profile(self) -> str:
        return "openai_compatible"

    @property
    def model_alias(self) -> str:
        return self._model_alias

    def generate_structured_draft(
        self,
        request: P3LLMDraftProviderRequest,
    ) -> P3LLMDraftProviderResult:
        body = json.dumps(
            {
                "model": self._model_alias,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in request.messages
                ],
                "temperature": request.model_parameters.get("temperature", 0),
                "max_tokens": request.model_parameters.get(
                    "max_output_tokens",
                    self._max_output_tokens,
                ),
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        http_request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self._timeout_seconds,
            ) as response:
                envelope = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise _error(
                "P3_LLM_PROVIDER_TIMEOUT",
                "P3 LLM provider timed out.",
            ) from exc
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            OSError,
        ) as exc:
            raise _error(
                "P3_LLM_PROVIDER_UNAVAILABLE",
                "P3 LLM provider is unavailable.",
            ) from exc
        try:
            choice = envelope["choices"][0]
            content = choice["message"]["content"]
            finish_reason = str(choice.get("finish_reason") or "")[:100] or None
        except (KeyError, IndexError, TypeError) as exc:
            raise _error(
                "P3_LLM_PROVIDER_UNAVAILABLE",
                "P3 LLM provider returned an invalid response envelope.",
            ) from exc
        usage = envelope.get("usage")
        safe_usage = (
            {
                key: int(value)
                for key, value in usage.items()
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            }
            if isinstance(usage, dict)
            else None
        )
        return P3LLMDraftProviderResult(
            parsed_payload=content,
            provider_profile="openai_compatible",
            model_alias=self._model_alias,
            usage_summary=safe_usage or None,
            finish_reason=finish_reason,
        )


class FakeP3LLMDraftProvider:
    """Offline test double. It is injectable but never environment-selectable."""

    def __init__(
        self,
        *,
        mode: str = "valid",
        provider_profile: str = "fake_test_only",
        model_alias: str = "fake-governed-model",
    ) -> None:
        self.mode = mode
        self.provider_profile = provider_profile
        self.model_alias = model_alias
        self.calls: list[P3LLMDraftProviderRequest] = []

    def generate_structured_draft(
        self,
        request: P3LLMDraftProviderRequest,
    ) -> P3LLMDraftProviderResult:
        self.calls.append(request)
        if self.mode == "timeout":
            raise _error("P3_LLM_PROVIDER_TIMEOUT", "Fake provider timed out.")
        if self.mode == "unavailable":
            raise _error(
                "P3_LLM_PROVIDER_UNAVAILABLE",
                "Fake provider is unavailable.",
            )
        if self.mode == "malformed_json":
            payload: object = "{not-json"
        elif self.mode == "schema_error":
            payload = {"unexpected": True}
        else:
            template = get_deterministic_template(request.asset_type)
            payload = template.render(request.source_materials)
            if self.mode == "unknown_source_ref":
                payload = json.loads(json.dumps(payload))
                _replace_first_source_ref(payload, source_item_id="unknown")
            elif self.mode == "missing_source_refs":
                payload = json.loads(json.dumps(payload))
                _replace_first_source_refs(payload, [])
            elif self.mode == "empty_content":
                payload = _empty_payload(request.asset_type)
        return P3LLMDraftProviderResult(
            parsed_payload=payload,
            provider_profile=self.provider_profile,
            model_alias=self.model_alias,
            usage_summary={"total_tokens": 0},
            finish_reason="stop",
        )


def _replace_first_source_ref(value: object, *, source_item_id: str) -> bool:
    if isinstance(value, dict):
        refs = value.get("source_refs")
        if isinstance(refs, list) and refs and isinstance(refs[0], dict):
            refs[0]["source_item_id"] = source_item_id
            return True
        return any(
            _replace_first_source_ref(child, source_item_id=source_item_id)
            for child in value.values()
        )
    if isinstance(value, list):
        return any(
            _replace_first_source_ref(child, source_item_id=source_item_id)
            for child in value
        )
    return False


def _replace_first_source_refs(value: object, replacement: list[object]) -> bool:
    if isinstance(value, dict):
        if "source_refs" in value:
            value["source_refs"] = replacement
            return True
        return any(
            _replace_first_source_refs(child, replacement)
            for child in value.values()
        )
    if isinstance(value, list):
        return any(_replace_first_source_refs(child, replacement) for child in value)
    return False


def _empty_payload(asset_type: ReuseAssetType) -> dict[str, object]:
    if asset_type is ReuseAssetType.TRAINING_MATERIAL:
        return {
            "title": "",
            "learning_objectives": [],
            "sections": [],
            "key_points": [],
            "source_refs": [],
        }
    if asset_type is ReuseAssetType.SOP:
        return {
            "title": "",
            "purpose": "",
            "scope": "",
            "prerequisites": [],
            "steps": [],
            "cautions": [],
            "escalation_rules": [],
            "source_refs": [],
        }
    if asset_type is ReuseAssetType.SERVICE_SCRIPT:
        return {
            "title": "",
            "scenario": "",
            "opening": "",
            "response_steps": [],
            "prohibited_claims": [],
            "escalation": [],
            "source_refs": [],
        }
    if asset_type is ReuseAssetType.QA_BANK:
        return {"title": "", "items": [], "source_refs": []}
    return {"records": []}


def validate_context_budget(
    materials: tuple[P3GenerationSourceMaterial, ...],
    settings: P3LLMDraftSettings,
) -> int:
    if len(materials) > settings.max_source_count:
        raise _error(
            "P3_LLM_CONTEXT_LIMIT_EXCEEDED",
            "P3 LLM source count exceeds the configured limit.",
        )
    context_chars = sum(
        len(material.title)
        + len(material.approved_content)
        + len(material.source_item_id)
        + len(material.source_id)
        for material in materials
    )
    if context_chars > settings.max_context_chars:
        raise _error(
            "P3_LLM_CONTEXT_LIMIT_EXCEEDED",
            "P3 LLM source context exceeds the configured limit.",
        )
    return context_chars


__all__ = [
    "FakeP3LLMDraftProvider",
    "OpenAICompatibleP3LLMDraftProvider",
    "P3_LLM_DEFAULT_MAX_OUTPUT_CHARS",
    "P3_LLM_ERROR_CODES",
    "P3LLMDraftError",
    "P3LLMDraftProvider",
    "P3LLMDraftProviderRequest",
    "P3LLMDraftProviderResult",
    "P3LLMDraftSettings",
    "P3LLMMessage",
    "validate_context_budget",
]
