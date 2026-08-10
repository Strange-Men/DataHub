"""Static regression tests for the P1 legacy/runtime persistence boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_p1_persistence_boundary.py"


def test_p1_runtime_persistence_boundary_gate_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(CHECK)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "P1 persistence boundary: PASS" in result.stdout


def test_gate_detects_legacy_import_and_filesystem_write(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("p1_boundary_check", CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    unsafe = tmp_path / "unsafe_runtime.py"
    unsafe.write_text(
        "from app.p1_legacy_storage import load_legacy_inventory\n"
        "Path('legacy.json').write_text('[]')\n",
        encoding="utf-8",
    )
    violations = module._violations(unsafe)
    assert any("legacy module import" in item for item in violations)
    assert any("filesystem method write_text" in item for item in violations)
