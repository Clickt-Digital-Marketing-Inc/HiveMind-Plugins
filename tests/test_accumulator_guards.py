from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUARDS = [
    ROOT / "plugins/google-ads-management/conftest.py",
    ROOT / "plugins/google-ads-management/_shared/conftest.py",
]


@pytest.mark.parametrize("guard", GUARDS, ids=lambda path: path.parent.name)
def test_accumulator_guard_turns_failed_check_red(tmp_path: Path, guard: Path) -> None:
    shutil.copy2(guard, tmp_path / "conftest.py")
    test_dir = tmp_path / "guarded" / "tests"
    test_dir.mkdir(parents=True)
    (test_dir / "test_probe.py").write_text(
        "_failures = []\n"
        "def check(): _failures.append('forced accumulator failure')\n"
        "def test_probe(): check()\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q", str(test_dir / "test_probe.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "failed check(s) accumulated" in output
    assert "forced accumulator failure" in output
