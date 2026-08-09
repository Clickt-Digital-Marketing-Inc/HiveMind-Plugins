#!/usr/bin/env python3
"""HM-892 mirror-sync verifier.

This is intentionally a mirror-only check. It verifies that the CM3 remote
workflow files copied into HiveMind-Plugins are byte-identical to the landed
HiveMind-Marketing-Skills source revision, while root mirror metadata stays
unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path


EXPECTED_UPSTREAM_SHA = "a4ae33dc91d7a36a4e32e6f4792f51f9c82bd96e"
UPSTREAM_BASE_SHA = "5ef00605394d2a7e7ecc4bc82230224f6b0e8c6a"
MIRROR_BASE_REF = "origin/main"

PLUGIN_SYNCED_PATHS = (
    "plugins/cm3-profitability/.claude-plugin/plugin.json",
    "plugins/cm3-profitability/commands/cm3-report.md",
    "plugins/cm3-profitability/skills/cm3-by-product-report/SKILL.md",
    "plugins/cm3-profitability/skills/cm3-by-product-report/references/remote-workflow.md",
    "plugins/cm3-profitability/skills/cm3-by-product-report/remote_workflow.py",
    "plugins/cm3-profitability/skills/cm3-by-product-report/tests/fixtures/cm3-remote-contract-v1.json",
    "plugins/cm3-profitability/skills/cm3-by-product-report/tests/test_remote_workflow.py",
)

CM3_METADATA_PATHS = (
    ".claude-plugin/marketplace.json",
    "README.md",
)

UPSTREAM_CHANGED_PATHS = (*CM3_METADATA_PATHS, *PLUGIN_SYNCED_PATHS)
SYNCED_PATHS = PLUGIN_SYNCED_PATHS

MIRROR_ONLY_CHECK_PATH = (
    "plugins/cm3-profitability/skills/cm3-by-product-report/tests/verify_mirror_sync_hm892.py"
)

PROTECTED_UNCHANGED_PATHS = (
    "LICENSE",
)

FORBIDDEN_SYNC_PATH_FRAGMENTS = (
    "/_charts/",
    "/templates/",
    "/vendor/",
    "/cm3_by_product.py",
    "/cm3_html.py",
)

MARKETPLACE_OLD_DESCRIPTION = (
    "Per-product CM3 contribution-margin report from a Google Ads 'Shopping products' CSV "
    "(optionally enriched with a Shopify 'Gross profit by product' CSV). One compute pass emits "
    "the locked 3-format bundle: an Obsidian-ready markdown report with static SVG charts, a "
    "self-contained interactive HTML explorer (tune cost assumptions and band cutoffs; every KPI, "
    "band, chart, rollup and product row re-computes live \u2014 it carries every workbook tab: "
    "By Campaign / Vendor / Category L1-L5 / Product Type L1-L5, plus by-band, summary KPIs and "
    "methodology, a live Pivot cross-tab of any two dimensions, and a dark mode), and a detailed "
    "multi-tab xlsx; a 7-slide executive pptx is opt-in. Segments products into 5 CM3 bands and "
    "rolls up by campaign, category, product type, and vendor. Requires openpyxl, python-pptx, and "
    "vl-convert-python."
)

MARKETPLACE_NEW_DESCRIPTION = (
    "Protected remote per-product CM3 contribution-margin report from a Google Ads Shopping CSV, "
    "optionally enriched with a Shopify Gross profit by product CSV. Uses CM3 contract 1.0 with "
    "metadata-only MCP calls, direct presigned uploads, and expiring Markdown, HTML, and XLSX "
    "artifacts; no local compute fallback."
)

README_REPLACEMENTS = (
    (
        "| **cm3-profitability** | Per-product CM3 contribution-margin report; CM3 bands + rollups by campaign, category (L1\u2013L5), product type (L1\u2013L5), and vendor, with a live HTML explorer that re-bands every table as you tune assumptions. | Google Ads Shopping-products CSV (+ optional Shopify Gross-profit CSV) |",
        "| **cm3-profitability** | Protected remote per-product CM3 report from a required Google Ads Shopping CSV (+ optional Shopify Gross profit by product CSV) -> expiring Markdown, HTML, and XLSX artifacts. CSV bytes bypass prompts and MCP JSON through direct presigned uploads. | CM3 protected-compute MCP contract 1.0 + service-issued credential; outbound HTTPS |",
    ),
    (
        "     `cm3-profitability` needs `pip install python-pptx vl-convert-python==1.7.0`.",
        "     `cm3-profitability` needs the CM3 protected-compute MCP, a service-issued\n     credential in the MCP client's private secret store, and outbound HTTPS.",
    ),
    (
        "  chart SVGs; `cm3-profitability` additionally needs `python-pptx` and the same\n  `vl-convert-python==1.7.0` pin. **LibreOffice** (optional) normalizes xlsx output.",
        "  chart SVGs; `cm3-profitability`'s thin remote helper uses only the Python\n  standard library. **LibreOffice** (optional) normalizes xlsx output.",
    ),
    (
        "  CSV exports; `google-ads-management` takes either, `cm3-profitability` is CSV-only.",
        "  CSV exports; `google-ads-management` takes either, and `cm3-profitability`\n  uses direct presigned uploads through the CM3 protected-compute MCP.",
    ),
)


class VerificationError(RuntimeError):
    pass


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationError(f"git {' '.join(args)} failed in {repo}: {detail}")
    return completed.stdout


def repo_root(path: Path) -> Path:
    return Path(run_git(path, "rev-parse", "--show-toplevel").strip())


def read_blob(repo: Path, ref: str, path: str) -> bytes:
    completed = subprocess.run(
        ("git", "-C", str(repo), "show", f"{ref}:{path}"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise VerificationError(f"missing upstream blob {ref}:{path}")
    return completed.stdout


def read_blob_text(repo: Path, ref: str, path: str) -> str:
    return read_blob(repo, ref, path).decode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def names_from_output(output: str) -> list[str]:
    return sorted(line for line in output.splitlines() if line)


def untracked_plugin_paths(mirror_repo: Path) -> list[str]:
    return names_from_output(
        run_git(
            mirror_repo,
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "plugins/cm3-profitability",
        )
    )


def verify(args: argparse.Namespace) -> list[str]:
    mirror_repo = repo_root(Path(args.mirror_repo).resolve())
    upstream_repo = repo_root(Path(args.upstream_repo).resolve())
    upstream_sha = args.upstream_sha
    mirror_base = args.mirror_base

    if upstream_sha != EXPECTED_UPSTREAM_SHA:
        raise VerificationError(
            f"source SHA mismatch: expected {EXPECTED_UPSTREAM_SHA}, got {upstream_sha}"
        )

    resolved_upstream = run_git(upstream_repo, "rev-parse", f"{upstream_sha}^{{commit}}").strip()
    if resolved_upstream != EXPECTED_UPSTREAM_SHA:
        raise VerificationError(
            f"resolved source SHA mismatch: expected {EXPECTED_UPSTREAM_SHA}, got {resolved_upstream}"
        )

    upstream_changed = names_from_output(
        run_git(
            upstream_repo,
            "diff",
            "--name-only",
            UPSTREAM_BASE_SHA,
            upstream_sha,
            "--",
            ".claude-plugin/marketplace.json",
            "README.md",
            "plugins/cm3-profitability",
        )
    )
    expected = sorted(UPSTREAM_CHANGED_PATHS)
    if upstream_changed != expected:
        raise VerificationError(
            "upstream HM-881 CM3 inventory changed:\n"
            f"expected={expected}\nactual={upstream_changed}"
        )

    allowed_mirror_plugin_changes = sorted((*PLUGIN_SYNCED_PATHS, MIRROR_ONLY_CHECK_PATH))
    mirror_changed = names_from_output(
        run_git(
            mirror_repo,
            "diff",
            "--name-only",
            mirror_base,
            "--",
            "plugins/cm3-profitability",
        )
    )
    extra_untracked = untracked_plugin_paths(mirror_repo)
    actual_mirror_changes = sorted(set(mirror_changed + extra_untracked))
    if actual_mirror_changes != allowed_mirror_plugin_changes:
        raise VerificationError(
            "mirror CM3 plugin-path change inventory mismatch:\n"
            f"expected={allowed_mirror_plugin_changes}\nactual={actual_mirror_changes}"
        )

    metadata_changed = names_from_output(
        run_git(
            mirror_repo,
            "diff",
            "--name-only",
            mirror_base,
            "--",
            ".claude-plugin/marketplace.json",
            "README.md",
        )
    )
    if metadata_changed != sorted(CM3_METADATA_PATHS):
        raise VerificationError(
            "mirror CM3 metadata change inventory mismatch:\n"
            f"expected={sorted(CM3_METADATA_PATHS)}\nactual={metadata_changed}"
        )
    expected_marketplace = read_blob_text(mirror_repo, mirror_base, ".claude-plugin/marketplace.json")
    if MARKETPLACE_OLD_DESCRIPTION not in expected_marketplace:
        raise VerificationError("base marketplace CM3 description was not found for exact replacement")
    expected_marketplace = expected_marketplace.replace(
        MARKETPLACE_OLD_DESCRIPTION,
        MARKETPLACE_NEW_DESCRIPTION,
        1,
    )
    if (mirror_repo / ".claude-plugin/marketplace.json").read_text() != expected_marketplace:
        raise VerificationError("marketplace metadata differs outside the expected CM3 description")

    expected_readme = read_blob_text(mirror_repo, mirror_base, "README.md")
    for old, new in README_REPLACEMENTS:
        if old not in expected_readme:
            raise VerificationError("base README CM3 metadata text was not found for exact replacement")
        expected_readme = expected_readme.replace(old, new, 1)
    if (mirror_repo / "README.md").read_text() != expected_readme:
        raise VerificationError("README metadata differs outside the expected CM3 replacements")

    forbidden = [
        path
        for path in PLUGIN_SYNCED_PATHS
        if any(fragment in f"/{path}" for fragment in FORBIDDEN_SYNC_PATH_FRAGMENTS)
    ]
    if forbidden:
        raise VerificationError(f"protected implementation paths entered sync inventory: {forbidden}")

    records: list[str] = []
    for path in SYNCED_PATHS:
        upstream_bytes = read_blob(upstream_repo, upstream_sha, path)
        mirror_bytes = (mirror_repo / path).read_bytes()
        if upstream_bytes != mirror_bytes:
            raise VerificationError(f"byte parity failed for {path}")
        records.append(f"{sha256(mirror_bytes)}  {path}")

    protected_diff = run_git(
        mirror_repo,
        "diff",
        "--name-only",
        mirror_base,
        "--",
        *PROTECTED_UNCHANGED_PATHS,
    )
    if protected_diff.strip():
        raise VerificationError(f"protected mirror metadata changed: {names_from_output(protected_diff)}")

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify HM-892 CM3 mirror sync byte parity.")
    parser.add_argument("--mirror-repo", default=".", help="HiveMind-Plugins checkout to verify.")
    parser.add_argument("--mirror-base", default=MIRROR_BASE_REF, help="Mirror base ref to protect metadata against.")
    parser.add_argument("--upstream-repo", required=True, help="HiveMind-Marketing-Skills checkout containing source objects.")
    parser.add_argument("--upstream-sha", default=EXPECTED_UPSTREAM_SHA, help="Immutable landed HM-881 upstream source SHA.")
    args = parser.parse_args()

    try:
        records = verify(args)
    except VerificationError as exc:
        print(f"HM-892 mirror sync verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"HM-892 upstream_sha={EXPECTED_UPSTREAM_SHA}")
    print(f"HM-892 synced_file_count={len(SYNCED_PATHS)}")
    for record in records:
        print(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
