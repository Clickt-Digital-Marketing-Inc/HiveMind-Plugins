from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAVE = ROOT / "plugins/google-ads-management/skills/google-ads/references/save_vault_report.py"


def run_save(source: Path, vault: Path, version: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(SAVE), "--source", str(source), "--vault", str(vault),
         "--stem", "account-health-2026-08-10", "--version", version],
        capture_output=True,
        text=True,
        check=False,
    )


def test_save_creates_versioned_file_and_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text("first version\n", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    first = run_save(source, vault, "v1")
    assert first.returncode == 0, first.stderr
    destination = vault / "raw/reports/account-health-2026-08-10-v1.md"
    assert destination.read_text(encoding="utf-8") == "first version\n"

    source.write_text("replacement attempt\n", encoding="utf-8")
    second = run_save(source, vault, "v1")
    assert second.returncode == 3
    assert "destination already exists" in second.stderr
    assert destination.read_text(encoding="utf-8") == "first version\n"


def test_save_rejects_unsafe_stem_before_write(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text("content\n", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    result = subprocess.run(
        [sys.executable, "-B", str(SAVE), "--source", str(source), "--vault", str(vault),
         "--stem", "../escape", "--version", "v1"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "safe filename components" in result.stderr
    assert not (vault / "raw").exists()
