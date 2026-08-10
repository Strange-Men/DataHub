"""Fail when normal P1 runtime code crosses the sealed legacy JSON boundary."""

from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    ROOT / "backend/app/main.py",
    ROOT / "backend/app/storage.py",
    ROOT / "backend/app/customerops_unified_service.py",
    ROOT / "backend/app/customerops_unified_routes.py",
    ROOT / "backend/app/unified_retrieval_adapters.py",
)
LEGACY_MODULE = ROOT / "backend/app/p1_legacy_storage.py"
FORBIDDEN_NAMES = {
    "_ensure_storage",
    "_read_json_list",
    "_write_json_list",
    "INDEX_FILE",
    "RAW_BATCH_DIR",
    "SANITIZED_BATCH_DIR",
    "KNOWLEDGE_CANDIDATE_DIR",
    "RETRIEVAL_LOG_DIR",
    "BAD_CASE_DIR",
}
FORBIDDEN_METHODS = {"read_text", "write_text", "unlink"}
FORBIDDEN_MODULES = {"app.p1_legacy_storage", "p1_legacy_storage"}


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    failures: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_MODULES:
                    failures.append(f"{path.name}:{node.lineno}: legacy module import")
        elif isinstance(node, ast.ImportFrom):
            if node.module in FORBIDDEN_MODULES:
                failures.append(f"{path.name}:{node.lineno}: legacy module import")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            failures.append(f"{path.name}:{node.lineno}: forbidden name {node.id}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                failures.append(f"{path.name}:{node.lineno}: filesystem open")
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in FORBIDDEN_METHODS
            ):
                failures.append(
                    f"{path.name}:{node.lineno}: filesystem method {node.func.attr}"
                )
    return failures


def main() -> int:
    failures: list[str] = []
    if not LEGACY_MODULE.is_file():
        failures.append("p1_legacy_storage.py: explicit legacy boundary is missing")
    for path in RUNTIME_FILES:
        if not path.is_file():
            failures.append(f"{path.relative_to(ROOT)}: runtime file is missing")
            continue
        failures.extend(_violations(path))
    if failures:
        print("P1 persistence boundary: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("P1 persistence boundary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
