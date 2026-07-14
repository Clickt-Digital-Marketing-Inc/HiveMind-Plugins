"""wPPC command-line entry point.

    wppc report --platform google --input <csv> --mapping <yaml> --outdir <dir>

Each run produces one report bundle for exactly one platform, written into
``--outdir`` under a tool-owned filename stem (``wppc_{platform}_{slug}_{date}``).
``--output <xlsx>`` remains as a back-compat alias: it writes ONLY the .xlsx to
the exact path given. wPPC is never compared or combined across platforms.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import click

from . import io as wio
from .model import (
    build_decay,
    build_decay_meta,
    build_incrementality_meta,
    build_model,
    build_run_meta,
    build_weights_snapshot,
    compare_weights_snapshot,
    load_incrementality,
)
from .render_html import render_html
from .render_md import render_md
from .report import write_report
from .score import score
from .weights import FUNNEL_STATES, derive_weights

# Default weight-drift tolerance (relative change). This CLI-layer default is
# the ONLY place the literal lives — score.py/weights.py never carry it.
DEFAULT_DRIFT_TOLERANCE = 0.15

# Default decay trend band, in wPPC+ points. Like the drift tolerance, this
# CLI-layer default is the ONLY place the literal lives — score.py never has it.
DEFAULT_DECAY_BAND = 5.0

# Default output formats for --outdir (tool-owned filenames). The weights.json
# sidecar is NOT part of this list — it is always written regardless of
# --formats (it is the W1 drift baseline source).
DEFAULT_FORMATS = "md,html,xlsx"


def resolve_drift_tolerance(cli_value, currency) -> float:
    """Resolve the drift tolerance as data: CLI flag > mapping > built-in default.

    Order: an explicit ``--drift-tolerance`` wins; else an optional
    ``currency["drift_tolerance"]`` from the mapping; else DEFAULT_DRIFT_TOLERANCE.
    """
    if cli_value is not None:
        return float(cli_value)
    if currency is not None and currency.get("drift_tolerance") is not None:
        return float(currency["drift_tolerance"])
    return DEFAULT_DRIFT_TOLERANCE


def resolve_decay_band(cli_value, currency) -> float:
    """Resolve the decay trend band as data: CLI flag > mapping > built-in default.

    Order: an explicit ``--decay-band`` wins; else an optional
    ``currency["decay_band"]`` from the mapping; else DEFAULT_DECAY_BAND.
    """
    if cli_value is not None:
        return float(cli_value)
    if currency is not None and currency.get("decay_band") is not None:
        return float(currency["decay_band"])
    return DEFAULT_DECAY_BAND


def slugify(value: str, fallback: str = "segments") -> str:
    """Deterministic filename-safe slug: lowercase, any run of non-alphanumeric
    characters collapsed to a single '-', leading/trailing '-' trimmed.

    Falls back to ``fallback`` when the input reduces to nothing (e.g. an
    all-symbol or empty stem) so the tool-owned filename is never malformed.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


@click.group()
def cli() -> None:
    """wPPC — weighted profit-per-click reporting for Google & Meta Ads."""


@cli.command()
@click.option("--platform", required=True, type=click.Choice(["google", "meta"]),
              help="Which platform's export is being scored.")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Path to the segment-export CSV.")
@click.option("--mapping", "mapping_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Path to the column-mapping YAML.")
@click.option("--outdir", "outdir_path", default=None, type=click.Path(file_okay=False),
              help="Directory to write the report bundle into (tool-owned filenames; "
                   "created if missing). Exactly one of --outdir / --output is required.")
@click.option("--output", "output_path", default=None, type=click.Path(dir_okay=False),
              help="Back-compat alias: write ONLY the .xlsx report to this exact path. "
                   "Exactly one of --outdir / --output is required.")
@click.option("--formats", "formats_arg", default=DEFAULT_FORMATS,
              help=f"Comma list of formats to write with --outdir: md,html,xlsx "
                   f"(default: {DEFAULT_FORMATS}). Ignored with --output.")
@click.option("--no-animate", "no_animate", is_flag=True, default=False,
              help="Build the HTML without GSAP motion.")
@click.option("--weights-baseline", "weights_baseline_path", default=None,
              type=click.Path(exists=True, dir_okay=False),
              help="Prior blessed weights snapshot (.weights.json) to detect drift against.")
@click.option("--drift-tolerance", "drift_tolerance", default=None, type=float,
              help="Relative weight-drift tolerance (overrides mapping/default 0.15).")
@click.option("--prior-input", "prior_input_path", default=None,
              type=click.Path(exists=True, dir_okay=False),
              help="Prior-period segment CSV; enables per-segment wPPC+ decay (default off).")
@click.option("--decay-band", "decay_band", default=None, type=float,
              help="Trend band in wPPC+ points (overrides mapping/default 5.0).")
@click.option("--incrementality", "incrementality_path", default=None,
              type=click.Path(exists=True, dir_okay=False),
              help="Layer-5 incrementality (IM) table JSON; recorded but NOT applied (v1 seam). "
                   "See wppc/references/incrementality-seam.md.")
def report(
    platform: str,
    input_path: str,
    mapping_path: str,
    outdir_path: str | None,
    output_path: str | None,
    formats_arg: str,
    no_animate: bool,
    weights_baseline_path: str | None,
    drift_tolerance: float | None,
    prior_input_path: str | None,
    decay_band: float | None,
    incrementality_path: str | None,
) -> None:
    """Score a segment export and write the wPPC report bundle."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if (outdir_path is None) == (output_path is None):
        given = "both --outdir and --output" if outdir_path is not None else "neither --outdir nor --output"
        raise click.ClickException(f"Exactly one of --outdir / --output is required (got {given}).")

    # One wall-clock read for the entire run — threaded into build_run_meta,
    # build_weights_snapshot, and the tool-owned filename date. No other clock
    # reads happen anywhere below.
    generated = datetime.now(timezone.utc).isoformat()

    try:
        mapping = wio.load_mapping(mapping_path, platform)
        df, currency = wio.load_segments(input_path, mapping, platform)

        if len(df) == 0:
            raise click.ClickException(f"No segment rows found in '{input_path}'.")

        reach_totals = {s: float(df[s].sum()) for s in FUNNEL_STATES}
        weights = derive_weights(
            reach_totals,
            purchases_total=float(df["purchase"].sum()),
            cm3_order=float(currency["CM3_order"]),
            repeat_rate=float(currency["repeat_rate"]),
            cm3_repeat=float(currency["CM3_repeat"]),
        )
    except ValueError as exc:
        # Mapping/column errors and the weight self-check surface as clean CLI
        # failures (no traceback), with their precise, named message intact.
        raise click.ClickException(str(exc)) from exc

    # Layer-5 incrementality seam (default off, v1 inert). Loading and
    # shape-validating the table exercises the seam; it is never applied to any
    # score — see wppc/references/incrementality-seam.md.
    incrementality_table = None
    if incrementality_path is not None:
        try:
            incrementality_table = load_incrementality(incrementality_path)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(
            f"Incrementality table provided ({len(incrementality_table['tiers'])} tiers): "
            "recorded, NOT applied (v1 seam)."
        )

    results = score(df, weights, incrementality=incrementality_table)

    # W4 two-period decay (default off). Only when a prior-period CSV is supplied
    # do we score it and compute per-segment wPPC+ movement. Decay is parallel
    # data — never blended into wPPC+/MAR — and rides in as extra report columns.
    decay = None
    band = None
    if prior_input_path is not None:
        band = resolve_decay_band(decay_band, currency)
        prior_df, _prior_currency = wio.load_segments(prior_input_path, mapping, platform)
        if len(prior_df) == 0:
            raise click.ClickException(f"No segment rows found in prior '{prior_input_path}'.")
        prior_results = score(prior_df, weights)
        decay = build_decay(results, prior_results, band)
    decay_meta = build_decay_meta(
        "computed" if decay is not None else "not-run",
        prior_input=prior_input_path,
        band=band,
    )

    # Weight-drift sidecar snapshot (W1). ALWAYS built, on the one threaded
    # timestamp — this is what gets written to <stem>.weights.json below.
    snapshot = build_weights_snapshot(weights, platform, timestamp=generated)

    # Drift detection only when a prior blessed baseline is supplied. The
    # comparison is read-only: it never mutates the baseline, and this run's
    # sidecar does not become the baseline unless the user points at it next run.
    drift = None
    tolerance = None
    if weights_baseline_path is not None:
        tolerance = resolve_drift_tolerance(drift_tolerance, currency)
        with open(weights_baseline_path, "r", encoding="utf-8") as fh:
            baseline_snapshot = json.load(fh)
        drift = compare_weights_snapshot(snapshot, baseline_snapshot, tolerance)
        drift["baseline_path"] = weights_baseline_path

    incr_meta = None
    if incrementality_table is not None:
        incr_meta = build_incrementality_meta(incrementality_path, incrementality_table)

    run_meta = build_run_meta(
        results, weights, platform,
        generated=generated,
        weights_version=snapshot,
        drift=drift,
        decay=decay_meta,
        incrementality=incr_meta,
    )
    model = build_model(results, weights, run_meta, decay=decay)

    # --- Emit ---
    written = {"md": None, "html": None, "xlsx": None}

    if output_path is not None:
        # Back-compat alias: xlsx only, at the exact path given. The sidecar
        # sits next to it, named off ITS stem (not the tool-owned stem).
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(str(out_path), results, weights, platform, decay=decay, run_meta=run_meta)
        written["xlsx"] = str(out_path.resolve())
        outdir = out_path.resolve().parent
        sidecar_path = out_path.with_name(out_path.stem + ".weights.json")
    else:
        outdir = Path(outdir_path)
        outdir.mkdir(parents=True, exist_ok=True)
        formats = [f.strip().lower() for f in formats_arg.split(",") if f.strip()]
        slug = slugify(Path(input_path).stem)
        date = generated[:10]
        stem = f"wppc_{platform}_{slug}_{date}"

        if "md" in formats:
            p = outdir / f"{stem}.md"
            p.write_text(render_md(model), encoding="utf-8")
            written["md"] = str(p.resolve())

        if "html" in formats:
            p = outdir / f"{stem}.html"
            p.write_text(render_html(model, animate=not no_animate), encoding="utf-8")
            written["html"] = str(p.resolve())

        if "xlsx" in formats:
            p = outdir / f"{stem}.xlsx"
            write_report(str(p), results, weights, platform, decay=decay, run_meta=run_meta)
            written["xlsx"] = str(p.resolve())

        outdir = outdir.resolve()
        sidecar_path = outdir / f"{stem}.weights.json"

    # Weight-drift sidecar (W1). Written on EVERY run regardless of --formats —
    # it is the W1 drift baseline source, not an optional report format.
    sidecar_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    written["weights"] = str(sidecar_path.resolve())

    # --- Human-readable summary (before the final machine-readable line) ---
    click.echo(
        f"Scored {len(results)} {platform} segments "
        f"(baseline wPPC ${results.attrs['baseline']:.2f}, "
        f"replacement ${results.attrs['replacement']:.2f}, k={results.attrs['k']:.0f})."
    )
    for fmt_key, label in (("md", "md"), ("html", "html"), ("xlsx", "xlsx")):
        if written.get(fmt_key):
            click.echo(f"  {label:5} {written[fmt_key]}")
    click.echo(f"  weights sidecar {written['weights']}")

    # W4 decay one-line summary (only when computed).
    if decay is not None:
        trend = decay["trend"]
        rising = int((trend == "Rising").sum())
        flat = int((trend == "Flat").sum())
        falling = int((trend == "Falling").sum())
        absent = int(trend.isna().sum())
        click.echo(
            f"Decay vs prior (band {band:.1f} wPPC+ pts): "
            f"{rising} Rising, {flat} Flat, {falling} Falling, "
            f"{absent} absent-from-prior."
        )

    # W1 drift one-line summary (only when a baseline was supplied).
    if drift is not None:
        if drift["flagged"]:
            parts = ", ".join(
                (f"{m['field']} {m['pct'] * 100:+.1f}%"
                 if m["pct"] is not None else f"{m['field']} (from 0)")
                for m in drift["moved"]
            )
            click.echo(f"WEIGHT DRIFT beyond tolerance {tolerance:.0%}: {parts}")
        else:
            click.echo(f"No weight drift beyond tolerance {tolerance:.0%}.")

    # --- Final machine-readable line. MUST be the last line of stdout. ---
    click.echo(json.dumps({
        "md": written["md"],
        "html": written["html"],
        "xlsx": written["xlsx"],
        "weights": written["weights"],
        "baseline": results.attrs["baseline"],
        "k": results.attrs["k"],
        "k_source": results.attrs["k_source"],
        "outdir": str(outdir),
    }, separators=(",", ":")))


if __name__ == "__main__":
    cli()
