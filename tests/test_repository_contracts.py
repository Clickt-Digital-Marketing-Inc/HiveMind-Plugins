"""Repository-level contracts for the HiveMind-Plugins marketplace mirror.

Restored and widened under PYR-50. The original of this file was added at
`de3c401` (2026-08-10, "Harden marketplace mirror for internal dogfooding"),
survived to `8ecd705`, and never reached `main` — so its leak guard was removed
rather than satisfied, while every token it banned stayed in the tree. This
version restores the guard, extends the banned list to every identifier named in
the client-data audit (both clients, the agency MCC, and the deploy host), and
scans the whole tree instead of one plugin directory.

Hardened under PYR-81, which closed the two coverage gaps PYR-50 left behind: the
substring list banned the brands only in the exact casings it happened to list,
and only inside an allowlisted set of file suffixes; and the host/path defaults
were swept under `plugins/clickt-reporting/` alone. Both are now word-boundary,
case-insensitive, and tree-wide over every file.

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
    "Ab" + "es College",
    "ab" + "es college",
    "176-" + "892-9875",
    "1768" + "929875",
)

# PYR-81 gap 1: the substring list above bans each brand only in the casings it
# happens to spell. The bare brand word is the leak that actually matters — a
# client name survives casing changes: a title-cased ecomm brand and an
# all-caps college short name would both have walked straight through. These
# patterns are word-boundary and case-insensitive, so they subsume every casing
# and every surrounding context (inside a hostname, inside quotes, before a
# comma) without matching a longer word that merely contains them.
#
# Same no-literal rule as above: each word is assembled from fragments, so the
# scanner carries no bare brand token on disk and does not trip itself. It is
# also why the college entries above are split mid-word rather than at the
# space — a word-boundary match would otherwise fire on the quoted first word.
# Nothing below this line may spell either brand out in prose, for the same
# reason; the sweep enforces that rather than trusting it.
BARE_BRAND_WORDS: tuple[str, ...] = (
    "ab" + "es",
    "pantry" + "lot",
)
BARE_BRAND_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    for word in BARE_BRAND_WORDS
)

# PYR-81 gap 2: these were swept under plugins/clickt-reporting only. A personal
# home path or an `ssh`/`rsync` root target is a leak wherever it appears — a
# doc, a workflow, a helper script — so they are swept tree-wide.
HOST_AND_PATH_TOKENS: tuple[str, ...] = (
    "/Users/" + "johngreenhow",
    "ro" + "ot@",
)

# The principal's name stays scoped to the onboarding scaffold, exactly as the
# original guard scoped it. Tree-wide it would fire on authorship, licence, and
# governance metadata, which is legitimate; the leak it prevents is a personal
# default shipped inside a client's package.
ONBOARDING_ONLY_TOKENS: tuple[str, ...] = ("John's", "John ")
ONBOARDING_ROOT = ROOT / "plugins/clickt-reporting"


def _all_files(root: Path) -> list[Path]:
    """Every file under `root`, with no suffix allowlist.

    PYR-81: the brand sweep must cover "any file type", so it walks this rather
    than `_scannable_files`. Safe to read everything here because the tree
    carries no binaries — the only files outside SCANNED_SUFFIXES are
    `.gitignore`, `LICENSE`, and the vendored `SHA256SUMS` manifests — and the
    reads below are `errors="replace"` regardless.
    """
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and not (SKIPPED_DIR_PARTS & set(path.parts))
    ]


def _scannable_files(root: Path) -> list[Path]:
    return [
        path
        for path in _all_files(root)
        if path.suffix.lower() in SCANNED_SUFFIXES
    ]


def scan_for_tokens(text: str, tokens: tuple[str, ...]) -> list[str]:
    """Return every token from `tokens` present in `text`.

    The single substring primitive used by both the tree sweep and the
    known-positive self-test, so the self-test exercises the real scanner.
    """
    return [token for token in tokens if token in text]


def scan_for_patterns(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    """Return the matched text of every pattern in `patterns` found in `text`.

    The regex sibling of `scan_for_tokens`, and likewise the single primitive
    shared by the tree sweep and the self-tests. Returns the matches rather
    than the patterns so a failure report names what was actually found.
    """
    return [match.group(0) for pattern in patterns for match in pattern.finditer(text)]


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
        '"deploy": "ro' + 'ot@5.161.' + '204.210", '
        '"other_client": "Ab' + 'es College"}'
    )
    hits = scan_for_tokens(planted, CLIENT_AND_INFRA_TOKENS)
    assert "Pantry" + "Lot" in hits, "scanner missed the planted client name"
    assert "544-" + "317-0313" in hits, "scanner missed the planted Google Ads CID"
    assert "5.161." + "204.210" in hits, "scanner missed the planted deploy host"
    assert "Ab" + "es College" in hits, "scanner missed the planted second client"

    clean = '{"client": {"name": "Example Client"}, "customer_id": "000-000-0000"}'
    assert scan_for_tokens(clean, CLIENT_AND_INFRA_TOKENS) == [], (
        "scanner flagged a synthetic fixture — the guard would be unusable"
    )


def test_bare_brand_scanner_fires_on_every_casing_the_substring_list_misses() -> None:
    """PYR-81 known-positive: each bare-brand pattern fires, and only on words.

    Every sample here is a casing the PYR-50 substring list would have let
    through, so this test is red against that list by construction. Samples are
    assembled from fragments, so no bare brand word exists on disk.
    """
    missed_by_the_substring_list = (
        "Pantry" + "lot",                 # third casing; list had two
        "PANTRY" + "LOT",
        "Ab" + "es",                      # bare, without the "College" suffix
        "AB" + "ES",
        "ab" + "es",
    )
    for sample in missed_by_the_substring_list:
        assert scan_for_tokens(sample, CLIENT_AND_INFRA_TOKENS) == [], (
            f"{sample!r} is no longer a gap in the substring list — this test's "
            "premise is stale and its samples need replacing"
        )
        assert scan_for_patterns(sample, BARE_BRAND_PATTERNS), (
            f"bare-brand scanner missed {sample!r}"
        )

    # Each pattern is individually proven, so an emptied or broken entry cannot
    # hide behind its sibling.
    for pattern in BARE_BRAND_PATTERNS:
        planted = "deploy target " + pattern.pattern.replace(r"\b", "") + " here"
        assert scan_for_patterns(planted, (pattern,)), f"{pattern.pattern} never fires"

    # Word boundaries hold: a longer word that merely contains a brand is not a
    # leak, and flagging it would make the guard unusable.
    for benign in ("cab" + "esque", "pantry" + "lots", "t" + "ab" + "es" + "poon"):
        assert scan_for_patterns(benign, BARE_BRAND_PATTERNS) == [], (
            f"bare-brand scanner flagged {benign!r} — \\b is not holding"
        )

    clean = '{"client": {"name": "Example Client"}, "store": "example.com"}'
    assert scan_for_patterns(clean, BARE_BRAND_PATTERNS) == [], (
        "bare-brand scanner flagged a synthetic fixture"
    )


def test_host_and_path_scanner_fires_on_each_tree_wide_token() -> None:
    """PYR-81 known-positive for the tokens promoted from scoped to tree-wide."""
    for token in HOST_AND_PATH_TOKENS:
        planted = "run: rsync -az ./dist/ " + token + "example.internal:/srv/reports/"
        assert scan_for_tokens(planted, HOST_AND_PATH_TOKENS) == [token], (
            f"tree-wide scanner missed a planted {token!r}"
        )

    clean = "run: rsync -az ./dist/ ${DESTINATION}/"
    assert scan_for_tokens(clean, HOST_AND_PATH_TOKENS) == [], (
        "tree-wide scanner flagged a parameterized destination"
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


def test_no_bare_brand_word_in_any_file_type() -> None:
    """PYR-81: the brand words, in any casing, in any file — not just the
    suffix allowlist the substring sweep uses."""
    failures: list[str] = []
    scanned = 0
    for path in _all_files(ROOT):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for hit in scan_for_patterns(text, BARE_BRAND_PATTERNS):
            failures.append(f"{path.relative_to(ROOT)} contains {hit!r}")
    assert scanned > 0, "brand sweep scanned nothing — the walker is broken"
    # The sweep must reach beyond the substring sweep, or the gap it exists to
    # close is still open.
    assert scanned > len(_scannable_files(ROOT)), (
        "brand sweep covered no more files than the suffix allowlist"
    )
    assert not failures, "bare brand identifiers at tip:\n" + "\n".join(failures)


def test_no_personal_path_or_root_host_anywhere_in_tree() -> None:
    """PYR-81: promoted from the clickt-reporting scope to the whole tree."""
    failures: list[str] = []
    scanned = 0
    for path in _all_files(ROOT):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in scan_for_tokens(text, HOST_AND_PATH_TOKENS):
            failures.append(f"{path.relative_to(ROOT)} contains {token!r}")
    assert scanned > 0, "host/path sweep scanned nothing — the walker is broken"
    assert not failures, "personal path / root host at tip:\n" + "\n".join(failures)


def test_clickt_reporting_onboarding_has_no_personal_or_client_defaults() -> None:
    failures: list[str] = []
    scanned = 0
    for path in _scannable_files(ONBOARDING_ROOT):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        banned = ONBOARDING_ONLY_TOKENS + HOST_AND_PATH_TOKENS + CLIENT_AND_INFRA_TOKENS
        for token in scan_for_tokens(text, banned):
            failures.append(f"{path.relative_to(ROOT)} contains {token!r}")
        for hit in scan_for_patterns(text, BARE_BRAND_PATTERNS):
            failures.append(f"{path.relative_to(ROOT)} contains {hit!r}")
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
