from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / ".test-inventory.json"


def discovered_test_files() -> list[str]:
    return sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "plugins").glob("*/**/test_*.py")
        if "__pycache__" not in path.parts
    )


def inventory_test_files() -> list[str]:
    data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert data.get("schemaVersion") == 1
    files = data.get("files")
    assert isinstance(files, list) and files == sorted(set(files))
    return files


def test_inventory_matches_shipped_test_population_bidirectionally() -> None:
    assert inventory_test_files() == discovered_test_files()


@pytest.mark.parametrize("relative", inventory_test_files())
def test_plugin_test_file_passes_in_isolated_pytest_process(relative: str) -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    plugin_root = ROOT / "/".join(relative.split("/")[:2])
    pyproject = plugin_root / "pyproject.toml"
    uses_pytest = pyproject.is_file() and "[tool.pytest" in pyproject.read_text(encoding="utf-8")
    if uses_pytest:
        command = [sys.executable, "-B", "-m", "pytest", "-q", str(ROOT / relative)]
        cwd = plugin_root
        env["PYTHONPATH"] = str(plugin_root) + os.pathsep + env.get("PYTHONPATH", "")
    else:
        command = [sys.executable, "-B", str(ROOT / relative)]
        cwd = ROOT
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
