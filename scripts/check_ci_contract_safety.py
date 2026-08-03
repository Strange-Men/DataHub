"""Static, zero-side-effect safety gate for the P1-P3 R1 CI workflow."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable
from urllib.parse import urlsplit

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs a pinned copy.
    yaml = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = Path(".github/workflows/p1-p3-r1-quality-gates.yml")
JOBS = ("backend-unit", "frontend-quality", "postgres-integration", "contract-safety")
CONTRACT_TESTS = (
    "test_governance_auth_rbac.py",
    "test_capability_service.py",
    "test_capability_route_safety.py",
    "test_runtime_health.py",
    "test_migration_baseline.py",
)
REQUIRED_PATHS = (
    "backend/pytest.ini",
    "backend/requirements.txt",
    "backend/tests/test_migration_postgres.py",
    "backend/tests/test_postgres_pgvector_reliability.py",
    "frontend/package-lock.json",
    "frontend/package.json",
    "scripts/check_ci_contract_safety.py",
    "scripts/manage_migrations.py",
)
DOC_PATHS = (
    ".github/README.md",
    "README.md",
    "README.en.md",
    "docs/08_DEV_STATUS.md",
    "docs/09_STAGE_CHECKLIST.md",
    "docs/85_P1_P3_R1_CONTRACT_FREEZE_AND_PLATFORM_ADR.md",
)
SECRET_PATTERNS = {
    "PRIVATE_KEY": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "AWS_KEY": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GITHUB_TOKEN": re.compile(
        r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,})"
    ),
    "PROVIDER_KEY": re.compile(
        r"(?:sk-proj-|sk-)[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}"
    ),
    "SLACK_TOKEN": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
}
FAKE_MARKERS = ("test", "fake", "dummy", "example", "placeholder", "must-not-leak", "this-is-a-secret")
TEXT_SUFFIXES = {
    ".cfg", ".css", ".example", ".html", ".ini", ".js", ".json", ".jsx",
    ".md", ".py", ".sh", ".sql", ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
}


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    path: str
    line: int
    message: str

    def render(self) -> str:
        location = self.path if not self.line else f"{self.path}:{self.line}"
        return f"{self.code} {location} {self.message}"


if yaml is not None:

    class WorkflowLoader(yaml.SafeLoader):
        """Keep GitHub's ``on`` key from YAML 1.1 boolean coercion."""


    WorkflowLoader.yaml_implicit_resolvers = {
        key: [item for item in values if item[0] != "tag:yaml.org,2002:bool"]
        for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    WorkflowLoader.add_implicit_resolver(
        "tag:yaml.org,2002:bool",
        re.compile(r"^(?:true|false)$", re.IGNORECASE),
        list("tTfF"),
    )


def _finding(code: str, path: Path | str, message: str, line: int = 0) -> Finding:
    return Finding(code, Path(path).as_posix(), line, message)


def _line(text: str, needle: str) -> int:
    offset = text.lower().find(needle.lower())
    return 0 if offset < 0 else text.count("\n", 0, offset) + 1


def _runs(job: object) -> str:
    if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
        return ""
    return "\n".join(
        str(step.get("run", ""))
        for step in job["steps"]
        if isinstance(step, dict)
    ).lower()


def _database_target_is_test(database_url: str) -> bool:
    """Require the database name/path itself, not credentials, to identify CI."""

    normalized = database_url.replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )
    parsed = urlsplit(normalized)
    target = parsed.path.rstrip("/").rsplit("/", 1)[-1].lower()
    return any(marker in target for marker in ("test", "ci"))


def _all_mappings(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _all_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_mappings(child)


def _audit_workflow(root: Path, relative: Path) -> list[Finding]:
    path = relative if relative.is_absolute() else root / relative
    if not path.is_file():
        return [_finding("WORKFLOW_MISSING", relative, "workflow is missing")]
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        return [_finding("PYYAML_MISSING", relative, "install pinned PyYAML in contract-safety")]
    try:
        workflow = yaml.load(text, Loader=WorkflowLoader)
    except yaml.YAMLError:
        return [_finding("WORKFLOW_YAML", relative, "workflow YAML is invalid")]
    if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
        return [_finding("WORKFLOW_SHAPE", relative, "workflow jobs must be a mapping")]

    findings: list[Finding] = []
    triggers = workflow.get("on")
    if not isinstance(triggers, dict):
        findings.append(_finding("TRIGGERS", relative, "on must be a mapping"))
    else:
        for event in ("push", "pull_request", "workflow_dispatch"):
            if event not in triggers:
                findings.append(_finding("TRIGGER_MISSING", relative, f"missing {event}"))
        push = triggers.get("push")
        if isinstance(push, dict) and "branches" in push and "main" not in push["branches"]:
            findings.append(_finding("MAIN_PUSH", relative, "push must include main"))

    permissions = workflow.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("contents") != "read":
        findings.append(_finding("PERMISSIONS", relative, "require top-level contents: read"))
    for mapping in _all_mappings(workflow):
        scoped = mapping.get("permissions")
        if isinstance(scoped, dict) and any(str(value).lower() not in {"read", "none"} for value in scoped.values()):
            findings.append(_finding("PERMISSION_WRITE", relative, "write permissions are forbidden"))

    jobs: dict[str, Any] = workflow["jobs"]
    for job_id in JOBS:
        if job_id not in jobs:
            findings.append(_finding("JOB_MISSING", relative, f"missing {job_id}"))
    if any(job not in jobs for job in JOBS):
        return findings
    for job_id in JOBS:
        if not isinstance(jobs[job_id], dict) or jobs[job_id].get("name") != job_id:
            findings.append(_finding("JOB_NAME", relative, f"job name must remain {job_id}"))

    for masking in ("continue-on-error", "allow_failure", "|| true", "set +e"):
        if masking in text.lower():
            findings.append(
                _finding("FAILURE_MASKING", relative, "CI failures must not be masked", _line(text, masking))
            )
    for job_id, job in jobs.items():
        job_env = job.get("env", {}) if isinstance(job, dict) else {}
        if isinstance(job_env, dict) and any(
            "${{ runner." in str(value).lower() for value in job_env.values()
        ):
            findings.append(
                _finding(
                    "JOB_CONTEXT",
                    relative,
                    f"{job_id} job-level env cannot use the runner context",
                )
            )
    for unsafe in (
        "${{ secrets.", "api.openai.com", "api.siliconflow.cn", "api.jina.ai",
        "api.deepseek.com", "127.0.0.1:5433", "datahub_postgres_data",
        "docker compose down -v", "docker volume rm",
    ):
        if unsafe in text.lower():
            findings.append(
                _finding("CI_ISOLATION", relative, "real secrets/providers or development state are forbidden", _line(text, unsafe))
            )

    pin = re.compile(r"@(?:v\d+(?:\.\d+){0,2}|[0-9a-f]{40})$")
    for job_id, job in jobs.items():
        for step in job.get("steps", []) if isinstance(job, dict) else []:
            if not isinstance(step, dict) or "uses" not in step:
                continue
            action = str(step["uses"])
            if not pin.search(action):
                findings.append(_finding("ACTION_UNPINNED", relative, f"pin actions used by {job_id}"))
        for raw_path in re.findall(r"(?<![\w.-])((?:backend|frontend|scripts)/[\w./-]+)", _runs(job)):
            command_path = raw_path.split("::", 1)[0].rstrip(".,:;)")
            if not (root / command_path).exists():
                findings.append(_finding("COMMAND_PATH", relative, f"{job_id} references a missing path"))

    for mapping in _all_mappings(workflow):
        env = mapping.get("env")
        if not isinstance(env, dict):
            continue
        for name, raw in env.items():
            key, value = str(name).upper(), str(raw).lower()
            if key in {"EMBEDDING_PROVIDER", "LLM_PROVIDER"} and value != "mock":
                findings.append(_finding("REAL_PROVIDER", relative, f"{key} must be mock"))
            if key == "P3_LLM_DRAFT_ENABLED" and value not in {"false", "0", ""}:
                findings.append(_finding("REAL_PROVIDER", relative, "P3 LLM must stay disabled"))
            if "DATABASE_URL" in key and not _database_target_is_test(value):
                findings.append(_finding("DATABASE_SCOPE", relative, f"{key} must identify test/ci"))

    backend, frontend = _runs(jobs["backend-unit"]), _runs(jobs["frontend-quality"])
    postgres, contract = _runs(jobs["postgres-integration"]), _runs(jobs["contract-safety"])
    for token in ("pip install", "backend/requirements.txt", "pytest", "backend/tests", "not postgres_integration", "compileall"):
        if token not in backend:
            findings.append(_finding("BACKEND_COMMAND", relative, f"backend-unit missing {token}"))
    for token in ("npm ci", "npm test", "npm run typecheck", "npm run lint", "npm run build"):
        if token not in frontend:
            findings.append(_finding("FRONTEND_COMMAND", relative, f"frontend-quality missing {token}"))
    if postgres.count("scripts/manage_migrations.py upgrade") < 2:
        findings.append(_finding("MIGRATION_IDEMPOTENCY", relative, "run upgrade twice"))
    if postgres.count("scripts/manage_migrations.py status") < 2:
        findings.append(_finding("MIGRATION_STATUS", relative, "check status before and after upgrade"))
    if "ready_health" not in postgres or "migration_required" not in postgres:
        findings.append(_finding("MIGRATION_READINESS", relative, "prove ready fails before migration and passes after"))
    full_pg = "pytest" in postgres and "backend/tests" in postgres and "-m postgres_integration" in postgres
    core_pg = all(name in postgres for name in ("test_migration_postgres.py", "test_postgres_pgvector_reliability.py"))
    if not (full_pg or core_pg):
        findings.append(_finding("POSTGRES_TESTS", relative, "run all marker tests or migration/reliability core"))

    services = jobs["postgres-integration"].get("services", {})
    pg_services = [
        (name, config) for name, config in services.items()
        if isinstance(config, dict) and str(config.get("image", "")).startswith("pgvector/pgvector:pg16")
    ] if isinstance(services, dict) else []
    if not pg_services:
        findings.append(_finding("POSTGRES_SERVICE", relative, "use PostgreSQL 16 with pgvector"))
    for name, config in pg_services:
        service_env = config.get("env", {})
        database = str(service_env.get("POSTGRES_DB", "")).lower()
        user = str(service_env.get("POSTGRES_USER", "")).lower()
        scoped_values = (str(name).lower(), database, user)
        if any(
            not any(marker in value for marker in ("test", "ci"))
            for value in scoped_values
        ):
            findings.append(
                _finding(
                    "POSTGRES_SCOPE",
                    relative,
                    "service, database, and user names must identify test/ci",
                )
            )
        if "volumes" in config:
            findings.append(_finding("POSTGRES_VOLUME", relative, "CI database must not mount volumes"))

    for test_name in CONTRACT_TESTS:
        if test_name not in contract:
            findings.append(_finding("CONTRACT_TEST", relative, f"contract-safety missing {test_name}"))
    if "scripts/check_ci_contract_safety.py" not in contract:
        findings.append(_finding("CONTRACT_CHECKER", relative, "contract-safety must run this checker"))
    if not re.search(r"pyyaml==\d+\.\d+(?:\.\d+)?", contract):
        findings.append(_finding("PYYAML_PIN", relative, "install pinned PyYAML only in contract-safety"))
    return findings


def _static_assignment(path: Path, name: str) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = node.value
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset":
            value = value.args[0]
        return ast.literal_eval(value)
    raise ValueError(name)


def _audit_repository_contract(root: Path) -> list[Finding]:
    findings = [
        _finding("PATH_MISSING", path, "required command path is missing")
        for path in REQUIRED_PATHS if not (root / path).exists()
    ]
    package_path = root / "frontend/package.json"
    if package_path.is_file():
        try:
            scripts = json.loads(package_path.read_text(encoding="utf-8"))["scripts"]
        except (OSError, KeyError, json.JSONDecodeError):
            findings.append(_finding("PACKAGE_JSON", package_path, "package.json scripts are invalid"))
        else:
            for name in ("test", "typecheck", "lint", "build"):
                if not scripts.get(name):
                    findings.append(_finding("NPM_SCRIPT", package_path, f"missing {name}"))
    marker = root / "backend/pytest.ini"
    if marker.is_file() and "postgres_integration:" not in marker.read_text(encoding="utf-8"):
        findings.append(_finding("PYTEST_MARKER", marker, "postgres_integration is not registered"))

    baseline = root / "backend/migrations/baseline_schema.py"
    revisions = sorted((root / "backend/migrations/versions").glob("*.py"))
    revisions = [path for path in revisions if path.name != "__init__.py"]
    try:
        baseline_revision = _static_assignment(baseline, "BASELINE_REVISION")
        p3_tables = _static_assignment(baseline, "P3_TABLE_NAMES")
        revision = _static_assignment(revisions[0], "revision") if len(revisions) == 1 else None
        down_revision = _static_assignment(revisions[0], "down_revision") if len(revisions) == 1 else "invalid"
    except (OSError, SyntaxError, ValueError):
        findings.append(_finding("MIGRATION_PARSE", baseline, "migration metadata must be static"))
    else:
        if baseline_revision != "20260803_0001" or revision not in {baseline_revision, "BASELINE_REVISION"} or down_revision is not None:
            findings.append(_finding("MIGRATION_HEAD", baseline, "immutable Alembic head changed"))
        if not isinstance(p3_tables, (set, frozenset)) or len(p3_tables) != 7:
            findings.append(_finding("P3_TABLES", baseline, "P3 must retain seven tables"))

    docs = [root / path for path in DOC_PATHS]
    if any(not path.is_file() for path in docs):
        findings.append(_finding("DOC_MISSING", "docs", "required current-status docs are missing"))
        return findings
    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)
    lower = combined.lower()
    for job in JOBS:
        if job not in combined:
            findings.append(_finding("REQUIRED_CHECK_DOC", "docs", f"document {job}"))
    facts = ("p3-m9", "p1-only", "opt-in", "blocked")
    if any(fact not in lower for fact in facts) or not (
        "p4 has not started" in lower or "p4 尚未开始" in lower
    ):
        findings.append(_finding("STATUS_DOC", "docs", "current product boundaries drifted"))
    branch_safe = "branch protection" in lower and re.search(
        r"(?:branch protection.{0,180}(?:建议|recommend|无法|cannot|未确认|not confirmed|未声称|不声称|不代表)|"
        r"(?:建议|recommend|无法|cannot|未确认|not confirmed|未声称|不声称|不代表).{0,180}branch protection)",
        combined, re.IGNORECASE | re.DOTALL,
    )
    if not branch_safe:
        findings.append(_finding("BRANCH_PROTECTION_DOC", "docs", "document recommended checks without claiming enablement"))
    if "状态：已接受" not in docs[-1].read_text(encoding="utf-8"):
        findings.append(_finding("ADR_STATUS", docs[-1], "contract ADR must remain accepted"))
    return findings


def _tracked_text_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, check=True, capture_output=True, timeout=30,
    )
    return [
        root / name for name in result.stdout.decode("utf-8").split("\0") if name
        and (
            Path(name).suffix.lower() in TEXT_SUFFIXES
            or Path(name).name in {"Dockerfile", ".gitignore", ".gitattributes", ".dockerignore", ".env"}
            or Path(name).name.startswith(".env.")
        )
        and (root / name).is_file() and (root / name).stat().st_size <= 2_000_000
    ]


def _audit_text_safety(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _tracked_text_files(root):
        relative = path.relative_to(root)
        if path.name == ".env" or (path.name.startswith(".env.") and not path.name.endswith(".example")):
            findings.append(_finding("TRACKED_ENV", relative, "runtime environment file is tracked"))
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            if re.fullmatch(r"(?:<<<<<<< .+|=======|>>>>>>> .+)", line):
                findings.append(_finding("CONFLICT_MARKER", relative, "merge marker found", number))
            for kind, pattern in SECRET_PATTERNS.items():
                for match in pattern.finditer(line):
                    value = match.group(0).lower()
                    fake_test = "tests" in relative.parts and any(marker in value for marker in FAKE_MARKERS)
                    if not fake_test:
                        findings.append(_finding("SECRET_PATTERN", relative, f"{kind} candidate; value suppressed", number))
    return findings


def run_checks(root: Path, workflow: Path = DEFAULT_WORKFLOW) -> list[Finding]:
    root = root.resolve()
    findings = _audit_workflow(root, workflow)
    findings.extend(_audit_repository_contract(root))
    findings.extend(_audit_text_safety(root))
    return sorted(set(findings))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workflow", type=Path, default=DEFAULT_WORKFLOW)
    args = parser.parse_args(list(argv) if argv is not None else None)
    findings = run_checks(args.root, args.workflow)
    if findings:
        print(f"contract safety: FAIL ({len(findings)})", file=sys.stderr)
        for finding in findings:
            print(finding.render(), file=sys.stderr)
        return 1
    print("contract safety: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
