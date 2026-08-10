from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "plugins/clickt-reporting/templates/report-package/deploy/deploy.sh"


@pytest.fixture()
def package(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / "report-package"
    (root / "deploy").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "template").mkdir()
    shutil.copy2(DEPLOY, root / "deploy/deploy.sh")
    (root / "config/client.json").write_text(
        json.dumps({"client": {"slug": "acme-client"}}), encoding="utf-8"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "node").write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "if [[ ${1:-} == -p ]]; then echo \"${FAKE_CLIENT_SLUG:-acme-client}\"; exit 0; fi\n"
        "mkdir -p \"dist/${FAKE_CLIENT_SLUG:-acme-client}\"\n"
        "printf ok > \"dist/${FAKE_CLIENT_SLUG:-acme-client}/index.html\"\n",
        encoding="utf-8",
    )
    (bin_dir / "rsync").write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$RSYNC_LOG\"\n",
        encoding="utf-8",
    )
    os.chmod(bin_dir / "node", 0o755)
    os.chmod(bin_dir / "rsync", 0o755)
    log = tmp_path / "rsync.log"
    env = os.environ.copy()
    env.update({"PATH": f"{bin_dir}:{env['PATH']}", "RSYNC_LOG": str(log)})
    return root, env, log


def run_deploy(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "deploy/deploy.sh", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_missing_arguments_refuse_before_build_or_sync(package) -> None:
    root, env, log = package
    result = run_deploy(root, env)
    assert result.returncode == 2
    assert result.stderr.startswith("Usage:")
    assert not log.exists()
    assert not (root / "dist").exists()


def test_invalid_slug_refuses_before_sync(package) -> None:
    root, env, log = package
    env["FAKE_CLIENT_SLUG"] = "../production"
    result = run_deploy(
        root,
        env,
        "--destination",
        str(root / "local-destination/production"),
        "--confirm",
        "deploy:production",
    )
    assert result.returncode == 2
    assert "client slug must match" in result.stderr
    assert not log.exists()


def test_destination_must_end_in_exact_slug(package) -> None:
    root, env, log = package
    result = run_deploy(
        root,
        env,
        "--destination",
        str(root / "local-destination/wrong-client"),
        "--confirm",
        "deploy:acme-client",
    )
    assert result.returncode == 2
    assert "destination must end in the exact client slug" in result.stderr
    assert not log.exists()


def test_wrong_confirmation_stops_after_dry_run(package) -> None:
    root, env, log = package
    destination = root / "local-destination/acme-client"
    result = run_deploy(
        root,
        env,
        "--destination",
        str(destination),
        "--confirm",
        "yes",
    )
    assert result.returncode == 2
    assert "confirmation must be exactly 'deploy:acme-client'" in result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert "-azn --itemize-changes" in calls[0]


def test_local_deploy_runs_dry_run_then_non_deleting_sync(package) -> None:
    root, env, log = package
    destination = root / "local-destination/acme-client"
    result = run_deploy(
        root,
        env,
        "--destination",
        str(destination),
        "--confirm",
        "deploy:acme-client",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 2
    assert "-azn --itemize-changes" in calls[0]
    assert calls[1].startswith("-az ")
    assert all("--delete" not in call for call in calls)
    assert all(str(destination) in call for call in calls)
