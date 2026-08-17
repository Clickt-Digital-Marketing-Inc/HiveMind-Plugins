"""Repository-level contracts for the HiveMind-Plugins marketplace mirror.

Restored and widened under PYR-50. The original of this file was added at
`de3c401` (2026-08-10, "Harden marketplace mirror for internal dogfooding"),
survived to `8ecd705`, and never reached `main` — so its leak guard was removed
rather than satisfied, while every token it banned stayed in the tree. This
version restores the guard, extends the banned list to every identifier named in
the client-data audit (both clients, the agency MCC, and the deploy host), and
scans the whole tree instead of one plugin directory.

Run: `python3 -m pytest -q tests/test_repository_contracts.py`
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
PLUGIN_NAMES = sorted(entry["name"] for entry in MARKETPLACE["plugins"])

# Text-ish files worth scanning. Binary and vendored trees are skipped below.
SCANNED_SUFFIXES = {
    ".md", ".json", ".sh", ".mjs", ".js", ".py", ".yml", ".yaml",
    ".txt", ".csv", ".html", ".css", ".toml", ".cfg", ".ini",
}
SKIPPED_DIR_PARTS = {".git", "node_modules", "__pycache__", ".venv", "dist"}

# Real client / infrastructure identifiers. These must not appear ANYWHERE in
# the tree. Source: pyrito-performance-audit-client-data.md S4 (the ecomm
# client of cluster A, the college of cluster B) plus the agency's own MCC and
# the report deploy host.
#
# The scanner itself must not contain a live token, or it would trip its own
# guard, so every entry is assembled from fragments at import time. The
# fragments are joined here and nowhere else.
CLIENT_AND_INFRA_TOKENS: tuple[str, ...] = (
    "Pantry" + "Lot",
    "pantry" + "lot",
    "www.pantry" + "lot.com",
    "adscale_ecom_Pantry" + "Lot",
    "5.161." + "204.210",
    "544-" + "317-0313",
    "5443" + "170313",
    "318-" + "624-6648",
    "581-" + "043-2788",
    "11820" + "16997374640",
    "5075" + "68174",
    "5075" + "76481",
    "Abes" + " College",
    "abes" + " college",
    "176-" + "892-9875",
    "1768" + "929875",
)

# Personal defaults that must not be baked into the client-onboarding scaffold.
# Scoped to plugins/clickt-reporting, exactly as the original guard scoped them:
# the leak these prevent is a personal default shipped into a client's package,
# not the principal's name appearing in governance or authorship metadata.
PERSONAL_DEFAULT_TOKENS: tuple[str, ...] = (
    "John's", "John ", "/Users/" + "johngreenhow", "root@",
)
ONBOARDING_ROOT = ROOT / "plugins/clickt-reporting"


def _scannable_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIPPED_DIR_PARTS & set(path.parts):
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        files.append(path)
    return files


def scan_for_tokens(text: str, tokens: tuple[str, ...]) -> list[str]:
    """Return every token from `tokens` present in `text`.

    The single matching primitive used by both the tree sweep and the
    known-positive self-test, so the self-test exercises the real scanner.
    """
    return [token for token in tokens if token in text]


# --------------------------------------------------------------------------
# The leak guard
# --------------------------------------------------------------------------


def test_scanner_fires_on_a_known_positive() -> None:
    """Known-positive control: the scanner must detect a planted sample.

    Without this, a scanner whose token list silently emptied (or whose
    matching broke) would report a clean tree and look identical to success.
    The sample is quarantined inside this test and assembled from fragments so
    it is never a literal token anywhere on disk.
    """
    planted = (
        '{"client": {"name": "Pantry' + 'Lot"}, '
        '"google_ads": {"customer_id": "544-' + '317-0313"}, '
        '"deploy": "root@5.161.' + '204.210", '
        '"other_client": "Abes' + ' College"}'
    )
    hits = scan_for_tokens(planted, CLIENT_AND_INFRA_TOKENS)
    assert "Pantry" + "Lot" in hits, "scanner missed the planted client name"
    assert "544-" + "317-0313" in hits, "scanner missed the planted Google Ads CID"
    assert "5.161." + "204.210" in hits, "scanner missed the planted deploy host"
    assert "Abes" + " College" in hits, "scanner missed the planted second client"

    clean = '{"client": {"name": "Example Client"}, "customer_id": "000-000-0000"}'
    assert scan_for_tokens(clean, CLIENT_AND_INFRA_TOKENS) == [], (
        "scanner flagged a synthetic fixture — the guard would be unusable"
    )


def test_no_client_or_infrastructure_identifiers_anywhere_in_tree() -> None:
    failures: list[str] = []
    scanned = 0
    # This file is scanned too: every token here is split across a `+` so no
    # literal appears on disk, and the sweep proves that claim rather than
    # exempting the scanner from its own rule.
    for path in _scannable_files(ROOT):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in scan_for_tokens(text, CLIENT_AND_INFRA_TOKENS):
            failures.append(f"{path.relative_to(ROOT)} contains {token!r}")
    assert scanned > 0, "token sweep scanned nothing — the walker is broken"
    assert not failures, "client/infrastructure identifiers at tip:\n" + "\n".join(failures)


def test_clickt_reporting_onboarding_has_no_personal_or_client_defaults() -> None:
    failures: list[str] = []
    scanned = 0
    for path in _scannable_files(ONBOARDING_ROOT):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in scan_for_tokens(text, PERSONAL_DEFAULT_TOKENS + CLIENT_AND_INFRA_TOKENS):
            failures.append(f"{path.relative_to(ROOT)} contains {token!r}")
    assert scanned > 0, "onboarding sweep scanned nothing — the walker is broken"
    assert not failures, "\n".join(failures)


def test_deploy_script_has_no_default_destination_and_is_fail_closed() -> None:
    deploy_path = ROOT / "plugins/clickt-reporting/templates/report-package/deploy/deploy.sh"
    deploy = deploy_path.read_text(encoding="utf-8")
    assert "REPORTS_HOST" not in deploy, "a defaulted host env var is back in deploy.sh"
    assert "--destination" in deploy
    assert "--confirm" in deploy
    # No host-looking default anywhere: no bare IPv4 literal, no user@host.
    assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", deploy), "deploy.sh contains an IP literal"
    assert not re.search(r"[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+", deploy), "deploy.sh contains a user@host target"
    actual_sync_lines = [line.strip() for line in deploy.splitlines() if line.strip().startswith("rsync ")]
    assert actual_sync_lines == [
        'rsync -azn --itemize-changes "dist/${CLIENT}/" "${NORMALIZED_DESTINATION}/"',
        'rsync -az "dist/${CLIENT}/" "${NORMALIZED_DESTINATION}/"',
    ], actual_sync_lines


# --------------------------------------------------------------------------
# Marketplace structure (restored unchanged from the original contracts file)
# --------------------------------------------------------------------------


def test_marketplace_population_matches_plugin_directories() -> None:
    directories = sorted(
        path.name
        for path in (ROOT / "plugins").iterdir()
        if path.is_dir() and (path / ".claude-plugin/plugin.json").is_file()
    )
    assert PLUGIN_NAMES == directories


def test_plugin_manifest_versions_match_marketplace() -> None:
    for entry in MARKETPLACE["plugins"]:
        manifest = json.loads(
            (ROOT / entry["source"] / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
        )
        assert manifest["name"] == entry["name"]
        assert manifest["version"] == entry["version"]


# NOTE (PYR-50): the original contracts file also carried
# `test_local_markdown_links_resolve`, `test_google_ads_hub_advertises_only_marketplace_plugins`,
# a README private-access test, and a CI-routing test. They are NOT restored here.
# The first two are red against `main` for pre-existing defects this issue does not
# own (four SKILL.md links to `google-ads-foundation/references/benchmarks-2026.md`
# that do not exist, and a hub catalog advertising `mediametrics-google`, which is
# not in this marketplace). The last two assert repo state that `main` deliberately
# no longer has: the repo is public since HM-708 (`2d82f67`), and there is no
# `.github/workflows/verify.yml` or root `verify` script here. Restoring any of them
# would have meant either a red suite or unrelated edits. Reported as new-issue
# candidates in the PYR-50 wrap-up.
