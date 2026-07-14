# Layer-5 incrementality contract (locked seam for CLI-408)

This document is the LOCKED contract between wPPC (this plugin) and the
separate **Incrementality** plugin, which is the fast-follow consumer of the
seam shipped in CLI-401. wPPC v1 ships the *seam only*: a documented,
shape-validated insertion point that changes nothing about the scores it
produces. Nothing in this document is implemented as a code constant in
`wppc/score.py` or anywhere else in the scoring kernels — the numbers below
(90 days, illustrative IM ranges, etc.) are contract documentation for the
future consumer, not runtime literals.

## Purpose

Attribution systems (last-click, data-driven, MTA) systematically overcount
certain funnel paths — most visibly brand search and retargeting, which
capture credit for demand that would have converted anyway. wPPC's weights
(`w(S)`) are derived from *attributed* funnel-event value: they measure
"how much CM3 does reaching state S predict," not "how much CM3 does reaching
state S **cause**."

Incrementality Measurement (IM) — geo holdouts, PSA/ghost-ad tests, matched-
market tests, conversion lift studies — corrects this by measuring the true
causal lift of a tier of spend. The **Incrementality plugin** (a separate
product, not part of wPPC) is responsible for running those tests and
producing an IM table. wPPC's job is only to *consume* that table and
attenuate its attributed weights toward their causal value — that consumption
is what this seam prepares for. wPPC v1 does not perform IM testing, does not
compute IM values, and does not apply them to any score.

## IM table serialization

The Incrementality plugin hands wPPC a JSON file shaped:

```json
{
  "tiers": [
    {
      "tier": "brand_search",
      "value": 0.35,
      "ci": [0.22, 0.48],
      "power": 0.82,
      "window": "2026-04-01/2026-06-30",
      "timestamp": "2026-07-01T00:00:00+00:00"
    },
    {
      "tier": "non_brand_search",
      "value": 0.78,
      "ci": [0.65, 0.91],
      "power": 0.90,
      "window": "2026-04-01/2026-06-30",
      "timestamp": "2026-07-01T00:00:00+00:00"
    },
    {
      "tier": "retargeting",
      "value": 0.15,
      "ci": [0.02, 0.30],
      "power": 0.55,
      "window": "2026-04-01/2026-06-30",
      "timestamp": "2026-07-01T00:00:00+00:00"
    },
    {
      "tier": "prospecting_social",
      "value": 0.62,
      "ci": [0.48, 0.76],
      "power": 0.75,
      "window": "2026-04-01/2026-06-30",
      "timestamp": "2026-07-01T00:00:00+00:00"
    }
  ]
}
```

Top level is an object with a single required key, `"tiers"`, a list. Each
tier entry carries exactly these six fields:

| field       | type            | meaning                                                              |
|-------------|-----------------|-----------------------------------------------------------------------|
| `tier`      | string          | tier name (see "Tier granularity" below)                              |
| `value`     | number          | measured incrementality (0..1-ish; the causal fraction of attributed credit) — illustrative only, no range is enforced by the loader |
| `ci`        | `[lo, hi]`      | confidence interval on `value`, two numbers                           |
| `power`     | number          | statistical power achieved by the test that produced `value`          |
| `window`    | string          | the test window the measurement covers (free-form, e.g. an ISO date range) |
| `timestamp` | string          | when the measurement was produced (ISO-8601 recommended)              |

`wppc.model.load_incrementality(path)` loads and shape-validates this file:
top-level `"tiers"` must be a list; every entry must be an object; every
entry must carry all six fields; `value`, `ci[0]`, `ci[1]`, and `power` must
be numeric; `ci` must be a 2-element list. Any violation raises `ValueError`
naming the missing/malformed field and the offending tier index. No range or
business-logic validation (e.g. `0 <= value <= 1`) is performed — that
judgment belongs to the Incrementality plugin producing the table, not to
this loader.

## Pipeline placement (Stage 1 vs Stage 2)

wPPC scores in two stages (`wppc/score.py:score`):

- **Stage 1 — numerator assembly.** `numerator = Σ reach(S)·w(S) +
  repeats·w(repeat)`, then `wppc = numerator / clicks`.
- **Stage 2 — shrinkage.** `wPPC_shrunk = (clicks·wppc + k·baseline) /
  (clicks + k)`.

The seam applies **at Stage 1, before shrinkage**:

```
weight_causal(event) = weight_attributed(event) × IM_applied(tier)
```

applied to the terms that make up `numerator`, immediately after numerator
assembly and before `wppc = _safe_div(numerator, clicks)` — the exact line
`wppc/score.py:score` marks with the comment `Layer-5 seam (v1: inert)`.

**Rationale for applying before shrinkage, not after:** shrinkage pulls each
segment's `wppc` toward the account `baseline`. If IM correction were applied
*after* shrinkage, the shrinkage prior itself would still be built from
attribution-inflated (uncorrected) segment values — the parent estimate would
carry the same overcounting the correction is meant to remove, biasing every
segment (including ones that never triggered an IM test) toward an inflated
baseline. Correcting the numerator first means both the segment estimate and
the shrinkage prior are computed on causal (or as-causal-as-measured) weights,
so the empirical-Bayes pull is toward a corrected parent, not a distorted one.

## Confidence banding

A raw IM measurement is not applied at full strength — its reliability
depends on how well-powered the underlying test was. The Incrementality
plugin (not wPPC) is expected to compute:

```
IM_applied = IM_measured × confidence_weight + 1.0 × (1 − confidence_weight)
```

where `confidence_weight` scales with the achieved test `power` (and,
implicitly, CI width — a wide `ci` at nominal power still signals a noisy
estimate). A well-powered, tight-CI measurement uses close to
`confidence_weight = 1.0` (trust the measured value); an underpowered or
wide-CI measurement blends toward `confidence_weight → 0`, i.e. toward
`IM_applied = 1.0` (no correction — behave as if attribution were already
causal). This blend formula is documented here as the intended behavior of
the future consumer; wPPC v1 does not compute `confidence_weight` or
`IM_applied` anywhere.

## Staleness

An IM measurement decays in relevance as market conditions, creative, and
competitive dynamics shift. The intended rule for the future consumer: an IM
value older than **~90 days** (illustrative — a config knob for the
Incrementality plugin, not a wPPC literal) since its `timestamp`/`window` is
treated as stale and falls back to `IM_applied = 1.0` (no correction) until
the tier is re-tested, rather than silently applying an out-of-date
correction. This is why the table stores `value`, `ci`, `power`, `tier`,
`window`, and `timestamp` per measurement — staleness and confidence banding
are both derivable from that stored provenance without wPPC needing to know
the policy.

## Tier granularity

IM is measured **per tier** (e.g. `brand_search`, `non_brand_search`,
`retargeting`, `prospecting_social`), never per individual segment — running
a separate holdout/lift test per keyword or ad segment is not statistically
feasible at most account sizes. Each scored segment maps to exactly one tier
(a mapping the Incrementality plugin or the wPPC mapping YAML would need to
supply in a future issue); the tier's `IM_applied` is what gets multiplied
into that segment's event weights in Stage 1.

## v1 behavior (what this issue actually ships)

- `wppc.model.load_incrementality(path)` loads and shape-validates the table.
- `wppc.model.build_incrementality_meta(path, table)` returns
  `{"status": "provided, not applied (v1)", "path": path, "tiers": [tier
  names...]}` for the run-metadata block.
- `wppc.score.score(df, weights, incrementality=table_or_None)` accepts the
  table as a keyword-only parameter and **does not read it** when computing
  any score — the multiplier described above is not implemented anywhere in
  v1. Every score/column/attribute is identical whether or not a table is
  passed.
- `wppc.model.build_run_meta(..., incrementality=meta_or_None)` passes the
  meta block straight through into the run-metadata dict; omitted, it stays
  `None` (unchanged from the prior stubbed behaviour).
- The CLI's `--incrementality <file>` flag loads and validates the file (a
  malformed file fails the run with a precise `ValueError`-derived message),
  echoes a one-line confirmation, and passes the loaded table into `score()`
  purely to exercise the inert seam — the xlsx output is byte-identical to a
  run without the flag.

Applying the actual multiplier — computing `confidence_weight`, banding
`IM_applied`, mapping segments to tiers, and multiplying it into `numerator`
— is explicitly out of scope for this issue and is the fast-follow work
(CLI-408).
