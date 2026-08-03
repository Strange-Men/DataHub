"""State-matrix tests for runtime capability aggregation."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import capability_probes  # noqa: E402
from app.auth import ROLE_TOKEN_ENV  # noqa: E402
from app.capability_service import get_capabilities  # noqa: E402


_REAL_ASSET_STORAGE_PROBE = capability_probes.asset_storage_readiness


@pytest.fixture(autouse=True)
def capability_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "local")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")
    for name in ROLE_TOKEN_ENV.values():
        monkeypatch.delenv(name, raising=False)
    for name in (
        "RENDER",
        "P3_LLM_DRAFT_ENABLED",
        "UNIFIED_RETRIEVAL_ENABLED",
        "P2_RETRIEVAL_ENABLED",
        "UNIFIED_RETRIEVAL_SHADOW_MODE",
        "CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(capability_probes, "database_available", lambda: True)
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: True)
    monkeypatch.setattr(
        capability_probes,
        "asset_storage_readiness",
        lambda: capability_probes.StorageProbeResult(ready=True, local_only=True),
    )
    monkeypatch.setattr(
        capability_probes,
        "export_storage_readiness",
        lambda: capability_probes.StorageProbeResult(ready=True, local_only=True),
    )


def _payload() -> dict[str, object]:
    return get_capabilities().model_dump(mode="json")


def test_healthy_local_snapshot_is_truthful_and_contract_stable() -> None:
    payload = _payload()

    assert set(payload) == {
        "environment",
        "authority",
        "auth",
        "infrastructure",
        "modules",
        "features",
    }
    assert payload["environment"] == "local"
    assert payload["authority"] == "local_docker"
    assert payload["auth"] == {
        "mode": "disabled",
        "safe_for_environment": True,
    }
    assert payload["infrastructure"] == {
        "database": "available",
        "pgvector": "available",
        "asset_storage": "local_only",
        "export_storage": "local_only",
    }
    modules = payload["modules"]
    assert modules["p1"] == {"status": "available", "reason_codes": []}
    assert modules["p2"] == {
        "status": "local_only",
        "reason_codes": ["ASSET_STORAGE_LOCAL_ONLY"],
    }
    assert modules["p3"] == {
        "status": "local_only",
        "reason_codes": ["EXPORT_STORAGE_LOCAL_ONLY"],
    }


def test_local_docker_environment_is_normalized_to_safe_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "docker")

    payload = _payload()

    assert payload["environment"] == "local"
    assert payload["authority"] == "local_docker"
    assert payload["auth"]["safe_for_environment"] is True


def test_render_signal_overrides_docker_label_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "docker")
    monkeypatch.setenv("RENDER", "true")

    payload = _payload()

    assert payload["environment"] == "production"
    assert payload["authority"] == "deployed_environment"
    assert payload["auth"] == {
        "mode": "disabled",
        "safe_for_environment": False,
    }
    for module_name in ("p1", "p2", "p3"):
        assert payload["modules"][module_name]["status"] == "unavailable"
        assert "AUTH_UNSAFE_FOR_ENVIRONMENT" in payload["modules"][module_name][
            "reason_codes"
        ]


def test_render_persistent_asset_storage_can_be_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "render-assets"
    asset_root.mkdir()
    monkeypatch.setenv("DATAHUB_ENV", "production")
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    monkeypatch.setenv("DATAHUB_ADMIN_TOKEN", "render-admin-token")
    monkeypatch.setenv("ASSET_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ASSET_STORAGE_ROOT", str(asset_root))
    monkeypatch.setattr(
        capability_probes,
        "asset_storage_readiness",
        _REAL_ASSET_STORAGE_PROBE,
    )

    payload = _payload()

    assert payload["infrastructure"]["asset_storage"] == "available"
    assert payload["modules"]["p2"] == {
        "status": "available",
        "reason_codes": [],
    }


def test_pgvector_unavailable_degrades_p1_keyword_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capability_probes, "pgvector_available", lambda: False)

    payload = _payload()

    assert payload["infrastructure"]["pgvector"] == "unavailable"
    assert payload["modules"]["p1"] == {
        "status": "degraded",
        "reason_codes": ["PGVECTOR_UNAVAILABLE"],
    }
    assert payload["modules"]["p2"]["status"] == "degraded"
    assert "PGVECTOR_UNAVAILABLE" in payload["modules"]["p2"]["reason_codes"]


def test_database_unavailable_fails_closed_for_data_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capability_probes, "database_available", lambda: False)

    payload = _payload()

    assert payload["infrastructure"]["database"] == "unavailable"
    for module_name in ("p1", "p2", "p3"):
        module = payload["modules"][module_name]
        assert module["status"] == "unavailable"
        assert "DATABASE_UNAVAILABLE" in module["reason_codes"]


def test_p2_and_p3_storage_failures_are_reported_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unavailable = capability_probes.StorageProbeResult(ready=False, local_only=True)
    monkeypatch.setattr(
        capability_probes,
        "asset_storage_readiness",
        lambda: unavailable,
    )
    monkeypatch.setattr(
        capability_probes,
        "export_storage_readiness",
        lambda: unavailable,
    )

    payload = _payload()

    assert payload["infrastructure"]["asset_storage"] == "unavailable"
    assert payload["infrastructure"]["export_storage"] == "unavailable"
    assert payload["modules"]["p2"] == {
        "status": "unavailable",
        "reason_codes": ["ASSET_STORAGE_UNAVAILABLE"],
    }
    assert payload["modules"]["p3"] == {
        "status": "unavailable",
        "reason_codes": ["EXPORT_STORAGE_UNAVAILABLE"],
    }


def test_production_disabled_auth_is_unsafe_and_modules_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_ENV", "production")
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")

    payload = _payload()

    assert payload["environment"] == "production"
    assert payload["authority"] == "deployed_environment"
    assert payload["auth"] == {
        "mode": "disabled",
        "safe_for_environment": False,
    }
    for module_name in ("p1", "p2", "p3"):
        module = payload["modules"][module_name]
        assert module["status"] == "unavailable"
        assert "AUTH_UNSAFE_FOR_ENVIRONMENT" in module["reason_codes"]


def test_invalid_auth_mode_is_safely_normalized_and_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "private-invalid-mode")

    payload = _payload()

    assert payload["auth"] == {
        "mode": "disabled",
        "safe_for_environment": False,
    }
    assert "private-invalid-mode" not in str(payload)
    for module_name in ("p1", "p2", "p3"):
        module = payload["modules"][module_name]
        assert module["status"] == "unavailable"
        assert "AUTH_CONFIGURATION_INVALID" in module["reason_codes"]
        assert "AUTH_UNSAFE_FOR_ENVIRONMENT" not in module["reason_codes"]


def test_flags_and_p4_planning_state_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled = _payload()
    assert disabled["features"] == {
        "p3_llm_draft": False,
        "unified_retrieval": False,
        "customerops_default_mode": "p1",
    }

    monkeypatch.setenv("P3_LLM_DRAFT_ENABLED", "true")
    monkeypatch.setenv("UNIFIED_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("P2_RETRIEVAL_ENABLED", "true")
    monkeypatch.setenv("CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED", "true")
    enabled = _payload()
    assert enabled["features"] == {
        "p3_llm_draft": True,
        "unified_retrieval": True,
        "customerops_default_mode": "unified",
    }

    monkeypatch.setenv("UNIFIED_RETRIEVAL_SHADOW_MODE", "true")
    shadow = _payload()
    assert shadow["features"]["customerops_default_mode"] == "p1"
    assert shadow["modules"]["p4"] == {
        "status": "planned",
        "reason_codes": ["NOT_IMPLEMENTED"],
    }
