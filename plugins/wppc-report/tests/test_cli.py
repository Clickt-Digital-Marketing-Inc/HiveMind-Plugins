"""CLI-404 — --outdir orchestration + machine-readable stdout.

Covers the reworked `report` command: --outdir writes the tool-owned bundle
(md/html/xlsx + always the weights.json sidecar) with a machine-readable final
JSON line; --output remains a back-compat alias that writes ONLY the xlsx (with
md/html null in that line); exactly one of --outdir/--output is required; and
--formats selects a subset of the bundle without touching the sidecar.
"""

import json
from pathlib import Path

from click.testing import CliRunner

from wppc.cli import cli

_REPO = Path(__file__).resolve().parents[1]
_GOOGLE_CSV = _REPO / "sample_data" / "google_segments.sample.csv"
_GOOGLE_MAPPING = _REPO / "config" / "mapping.google.sample.yaml"

_JSON_LINE_KEYS = {"md", "html", "xlsx", "weights", "baseline", "k", "k_source", "outdir"}


def _last_line(output: str) -> str:
    return output.rstrip("\n").splitlines()[-1]


def test_outdir_writes_full_bundle_and_final_json_line(tmp_path):
    runner = CliRunner()
    outdir = tmp_path / "out"
    result = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
        "--outdir", str(outdir),
    ])
    assert result.exit_code == 0, result.output

    line = _last_line(result.output)
    payload = json.loads(line)  # last line must parse as JSON
    assert set(payload.keys()) == _JSON_LINE_KEYS

    for key in ("md", "html", "xlsx", "weights"):
        assert payload[key] is not None, key
        p = Path(payload[key])
        assert p.is_absolute()
        assert p.exists(), f"{key} -> {p} does not exist"

    assert isinstance(payload["baseline"], (int, float))  # scored baseline wPPC
    assert isinstance(payload["k"], (int, float))
    assert isinstance(payload["k_source"], str)
    assert Path(payload["outdir"]).is_absolute()
    assert Path(payload["outdir"]) == outdir.resolve()

    # Tool-owned stem: wppc_{platform}_{slug}_{date}, slug from the input CSV
    # filename stem ("google_segments.sample" -> "google-segments-sample").
    stem = Path(payload["xlsx"]).stem
    assert stem.startswith("wppc_google_google-segments-sample_")

    # Exactly the four files landed in outdir, all sharing the stem.
    produced = sorted(p.name for p in outdir.iterdir())
    assert produced == sorted([
        f"{stem}.html", f"{stem}.md", f"{stem}.weights.json", f"{stem}.xlsx",
    ])


def test_output_alias_writes_only_xlsx_with_md_html_null(tmp_path):
    runner = CliRunner()
    out = tmp_path / "legacy_report.xlsx"
    result = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
        "--output", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert out.exists()

    sidecar = tmp_path / "legacy_report.weights.json"
    assert sidecar.exists()

    payload = json.loads(_last_line(result.output))
    assert payload["xlsx"] == str(out.resolve())
    assert payload["md"] is None
    assert payload["html"] is None
    assert payload["weights"] == str(sidecar.resolve())
    assert isinstance(payload["baseline"], (int, float))  # scored baseline wPPC
    assert Path(payload["outdir"]) == out.resolve().parent

    # Only the xlsx + sidecar exist next to --output — no bundle stem files.
    produced = sorted(p.name for p in tmp_path.iterdir())
    assert produced == sorted(["legacy_report.xlsx", "legacy_report.weights.json"])


def test_both_outdir_and_output_is_a_clean_error(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
        "--outdir", str(tmp_path / "out"),
        "--output", str(tmp_path / "report.xlsx"),
    ])
    assert result.exit_code != 0
    assert "--outdir" in result.output
    assert "--output" in result.output
    assert not isinstance(result.exception, AssertionError)


def test_neither_outdir_nor_output_is_a_clean_error(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
    ])
    assert result.exit_code != 0
    assert "--outdir" in result.output
    assert "--output" in result.output
    assert not isinstance(result.exception, AssertionError)


def test_formats_md_writes_only_md_and_weights_sidecar(tmp_path):
    runner = CliRunner()
    outdir = tmp_path / "out"
    result = runner.invoke(cli, [
        "report", "--platform", "google",
        "--input", str(_GOOGLE_CSV),
        "--mapping", str(_GOOGLE_MAPPING),
        "--outdir", str(outdir),
        "--formats", "md",
    ])
    assert result.exit_code == 0, result.output

    payload = json.loads(_last_line(result.output))
    assert payload["md"] is not None
    assert payload["html"] is None
    assert payload["xlsx"] is None
    assert payload["weights"] is not None  # sidecar always written

    produced = sorted(p.name for p in outdir.iterdir())
    stem = Path(payload["md"]).stem
    assert produced == sorted([f"{stem}.md", f"{stem}.weights.json"])
    assert not any(name.endswith(".html") or name.endswith(".xlsx") for name in produced)
