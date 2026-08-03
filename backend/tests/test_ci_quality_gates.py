"""Focused tests for the zero-side-effect CI contract checker."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import check_ci_contract_safety as ci_safety  # noqa: E402


WORKFLOW = ROOT / ".github/workflows/p1-p3-r1-quality-gates.yml"


def _codes(findings: list[ci_safety.Finding]) -> set[str]:
    return {finding.code for finding in findings}


def _mutated_workflow(tmp_path: Path, old: str, new: str) -> Path:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert old in source
    path = tmp_path / "quality-gates.yml"
    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    return path


def test_repository_ci_contract_safety_passes() -> None:
    assert ci_safety.run_checks(ROOT) == []


def test_yaml_on_key_and_required_triggers_are_preserved(tmp_path: Path) -> None:
    workflow = _mutated_workflow(
        tmp_path,
        "  workflow_dispatch:\n",
        "  schedule:\n    - cron: '0 0 * * *'\n",
    )

    findings = ci_safety._audit_workflow(ROOT, workflow)

    assert "TRIGGER_MISSING" in _codes(findings)
    assert not any(finding.code == "TRIGGERS" for finding in findings)


def test_stable_job_names_and_failure_masking_are_enforced(tmp_path: Path) -> None:
    renamed = _mutated_workflow(
        tmp_path,
        "    name: backend-unit\n",
        "    name: Backend unit\n",
    )
    renamed_findings = ci_safety._audit_workflow(ROOT, renamed)
    masked = _mutated_workflow(
        tmp_path,
        "run: python -m compileall -q backend scripts",
        "run: python -m compileall -q backend scripts || true",
    )

    assert "JOB_NAME" in _codes(renamed_findings)
    assert "FAILURE_MASKING" in _codes(ci_safety._audit_workflow(ROOT, masked))


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    (
        (
            "      EMBEDDING_PROVIDER: mock\n",
            "      EMBEDDING_PROVIDER: openai\n",
            "REAL_PROVIDER",
        ),
        (
            "      DATABASE_URL: sqlite:///${{ runner.temp }}/datahub-ci-unit-test.db\n",
            "      DATABASE_URL: postgresql://127.0.0.1:5433/datahub\n",
            "CI_ISOLATION",
        ),
        (
            "      DATABASE_URL: sqlite:///${{ runner.temp }}/datahub-ci-unit-test.db\n",
            "      DATABASE_URL: postgresql://datahub_ci:ci_password@127.0.0.1:5432/datahub\n",
            "DATABASE_SCOPE",
        ),
        (
            "      DATAHUB_AUTH_MODE: disabled\n",
            "      DATAHUB_AUTH_MODE: ${{ secrets.DATAHUB_TOKEN }}\n",
            "CI_ISOLATION",
        ),
    ),
)
def test_real_provider_development_database_and_secrets_are_rejected(
    tmp_path: Path,
    old: str,
    new: str,
    expected: str,
) -> None:
    workflow = _mutated_workflow(tmp_path, old, new)

    assert expected in _codes(ci_safety._audit_workflow(ROOT, workflow))


def test_secret_scan_allows_known_test_fake_but_suppresses_real_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_dir = tmp_path / "backend/tests"
    test_dir.mkdir(parents=True)
    fake = test_dir / "test_fake_secret.py"
    fake.write_text('KEY = "sk-test-secret-key-1234567890"\n', encoding="utf-8")
    leaked_value = "sk-" + "live" + "A" * 24
    leaked = tmp_path / "settings.py"
    leaked.write_text(f'KEY = "{leaked_value}"\n', encoding="utf-8")
    monkeypatch.setattr(ci_safety, "_tracked_text_files", lambda _root: [fake, leaked])

    findings = ci_safety._audit_text_safety(tmp_path)

    secret_findings = [item for item in findings if item.code == "SECRET_PATTERN"]
    assert len(secret_findings) == 1
    assert secret_findings[0].path == "settings.py"
    assert leaked_value not in secret_findings[0].render()


def test_postgres_service_user_must_be_explicitly_ci_scoped(tmp_path: Path) -> None:
    workflow = _mutated_workflow(
        tmp_path,
        "          POSTGRES_USER: datahub_ci\n",
        "          POSTGRES_USER: datahub\n",
    )

    assert "POSTGRES_SCOPE" in _codes(ci_safety._audit_workflow(ROOT, workflow))


def test_conflict_marker_scan_reports_location_without_source_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conflicted = tmp_path / "module.py"
    conflicted.write_text("value = 1\n<<<<<<< HEAD\nvalue = 2\n", encoding="utf-8")
    monkeypatch.setattr(ci_safety, "_tracked_text_files", lambda _root: [conflicted])

    findings = ci_safety._audit_text_safety(tmp_path)

    conflict = next(item for item in findings if item.code == "CONFLICT_MARKER")
    assert conflict.path == "module.py"
    assert conflict.line == 2
    assert "<<<<<<<" not in conflict.render()
