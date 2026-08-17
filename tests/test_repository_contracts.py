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
SKIPPED_DIR_PARTS = {
    ".git", "node_modules", "__pycache__", ".venv", "dist",
    # PYR-81: the brand sweep walks every file, not just SCANNED_SUFFIXES, so
    # tool caches now fall inside it. They are generated, untracked, and their
    # contents (failed-test node ids, hashes) would make the sweep's file count
    # depend on whether pytest had run before — skip them explicitly.
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
}

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
    """PYR-81 known-positive for the tokens promoted from scoped to tree-wide.

    The controls are written out independently rather than looped over
    HOST_AND_PATH_TOKENS: a sample derived from the subject vanishes along with
    the subject, so deleting an entry would silently delete its own assertion.
    The coverage assertion below is what pins the shipped set to these controls.
    """
    controls = (
        "/Users/" + "johngreenhow",
        "ro" + "ot@",
    )
    assert set(controls) <= set(HOST_AND_PATH_TOKENS), (
        "a token these controls prove is no longer swept tree-wide: "
        f"{sorted(set(controls) - set(HOST_AND_PATH_TOKENS))}"
    )
    for token in controls:
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


def test_readme_documents_every_installable_plugin() -> None:
    """Restored (in part) from `8ecd705` under PYR-81.

    The README documented 11 of 13: `wppc-report` appeared only as a bare
    install line with no description, and `clickt-reporting` appeared nowhere at
    all. Derived from the marketplace rather than hand-listed, so a plugin added
    later is covered by construction.

    The original also asserted this repo was private and access-gated. That half
    is deliberately NOT restored: `main` has been public since HM-708 (`2d82f67`),
    so those assertions now pin the opposite of the truth.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    undescribed = [name for name in PLUGIN_NAMES if f"**{name}**" not in readme]
    uninstallable = [
        name for name in PLUGIN_NAMES
        if f"/plugin install {name}@hivemind-plugins" not in readme
    ]
    assert not undescribed, f"README has no bold entry for: {undescribed}"
    assert not uninstallable, f"README has no install line for: {uninstallable}"


def test_google_ads_hub_advertises_only_marketplace_plugins() -> None:
    """Restored from `8ecd705` under PYR-81.

    The hub catalog advertised a `mediametrics-google` task whose plugin is not
    in this marketplace, which also made the hub's own
    `skills/google-ads/tests/test_catalog.py` fail live. Task removed; guard
    back. The surface check is case-insensitive here (the original was not) so
    the lowercase route references that the original would have missed cannot
    creep back.

    Scoped to the hub's three advertising surfaces on purpose: the name also
    appears across the audit plugins as provenance for mirrored analytics
    ("mirror of the MediaMetrics analytics module"), which is attribution, not
    an advertised install.
    """
    catalog_path = ROOT / "plugins/google-ads-management/skills/google-ads/references/catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    advertised = {task["plugin"] for task in catalog["tasks"]}
    assert advertised <= set(PLUGIN_NAMES), (
        "hub catalog advertises plugins absent from this marketplace: "
        f"{sorted(advertised - set(PLUGIN_NAMES))}"
    )
    # Every group the catalog offers must still be populated by a task.
    assert set(catalog["groups"]) == {task["group"] for task in catalog["tasks"]}, (
        "hub catalog offers a group no task belongs to"
    )
    for surface in (
        ROOT / "plugins/google-ads-management/README.md",
        ROOT / "plugins/google-ads-management/skills/google-ads/SKILL.md",
        catalog_path,
    ):
        assert "mediametrics" not in surface.read_text(encoding="utf-8").lower(), (
            f"{surface.relative_to(ROOT)} advertises a plugin this marketplace does not ship"
        )


def test_local_markdown_links_resolve() -> None:
    """Restored from `8ecd705` under PYR-81.

    PYR-50 left this out because it was red against `main`: four sibling skills
    linked to the foundation skill's benchmarks reference by a path relative to
    the foundation skill rather than to themselves. Those four links are fixed,
    so the guard is back to keep them fixed.
    """
    broken: list[str] = []
    pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    for markdown in sorted(ROOT.rglob("*.md")):
        if SKIPPED_DIR_PARTS & set(markdown.parts) or markdown.name.endswith(".template.md"):
            continue
        for raw in pattern.findall(markdown.read_text(encoding="utf-8", errors="replace")):
            if raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = raw.split("#", 1)[0]
            if target and "{{" not in target and not (markdown.parent / target).exists():
                broken.append(f"{markdown.relative_to(ROOT)} -> {raw}")
    assert not broken, "broken local Markdown links:\n" + "\n".join(broken)


def test_marketplace_population_matches_plugin_directories() -> None:
    directories = sorted(
        path.name
        for path in (ROOT / "plugins").iterdir()
        if path.is_dir() and (path / ".claude-plugin/plugin.json").is_file()
    )
    local_entries = sorted(
        Path(entry["source"]).name
        for entry in MARKETPLACE["plugins"]
        if isinstance(entry.get("source"), str)
        and entry["source"].startswith("./plugins/")
    )
    assert local_entries == sorted(set(directories) - {"clickt-reporting"})
    assert sorted(set(directories) - set(local_entries)) == ["clickt-reporting"], (
        "only the frozen clickt-reporting recovery snapshot may be unreferenced"
    )


def test_plugin_manifest_versions_match_marketplace() -> None:
    for entry in MARKETPLACE["plugins"]:
        if not isinstance(entry.get("source"), str):
            continue
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
