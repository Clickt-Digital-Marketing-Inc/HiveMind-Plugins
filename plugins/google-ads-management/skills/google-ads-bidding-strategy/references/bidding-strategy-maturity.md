# Bidding Strategy — Data Maturity Score (advisor, dual MCP/CSV)

Scores every campaign's readiness for automated bidding and flags where the strategy actually
running doesn't match what the account's data supports. Ships the standard three-format
analytical bundle: a **markdown report**, a **self-contained interactive HTML explorer**, and a
**formula-driven xlsx** — plus a `--emit-widget` tuner for the in-Claude hub. Reuses every
`google-ads-foundation` convention (micros, dates, dedup, the advisor + dual-input contract in
[`../../google-ads-foundation/references/artifact-formats.md`](../../google-ads-foundation/references/artifact-formats.md)) — load that first.

All formats are rendered by the shared toolkit (`_shared/render`) from one model
(`scripts/bidding_core.py`), so they can never disagree; this file is the **authoritative**
input/output contract (the scripts' docstrings point here rather than restating it).

## The model

**Data Maturity Score** (0-100) per campaign:

```
Score = VolumeScore × volume_weight + ValueVarianceScore × value_weight + TrackingConfidenceScore × tracking_weight
```

| Component | Source | Default weight |
|---|---|---|
| **VolumeScore** | hard-scored from `conv30` vs the tunable `conv_target` — `min(100, 100 × conv30/conv_target)` | 0.40 |
| **ValueVarianceScore** | optional judgment input, 0-100 (higher = more stable order/lead values); the MCP/CSV cannot supply it | 0.30 |
| **TrackingConfidenceScore** | optional judgment input, 0-100 (higher = more complete/confirmed conversion tracking) | 0.30 |

When a campaign's findings row omits a judgment component, the tunable neutral-assumption param
(`assumed_value_score` / `assumed_tracking_score`, default 50) is substituted — **never presented
as a hard-measured score**. Every scored row carries a `confidence` field: `"measured"` (both
judgment inputs supplied), `"partial"` (one supplied), `"assumed"` (neither).

**Maturity bands** (tunable edges, default 30/50/70/85) map the score to a recommended tier:

| Score | Tier | Recommended strategy |
|---|---|---|
| < 30 | 0 | Manual CPC / Maximize Clicks |
| 30 – < 50 | 1 | Enhanced CPC |
| 50 – < 70 | 2 | Target CPA / Maximize Conversions |
| 70 – < 85 | 3 | Target ROAS / Maximize Conversion Value |
| ≥ 85 | 4 | Target ROAS + Smart Bidding Exploration |

Band boundaries are **inclusive of the upper tier** (a score of exactly 30 is tier 1, not tier 0)
— a formalization of the SKILL.md table, now tunable. Keep the four edges in ascending order; the
xlsx workbook's nested-IF formula does not sort them (the Python/JS kernels do, defensively).

**Current tier** comes from a fixed (non-tunable) lookup on `bidding_strategy_type` — the GAQL enum
or the equivalent Google Ads UI "Bid strategy type" export label (both normalize to the same
token): `MANUAL_CPC`/`MANUAL_CPM`/`MANUAL_CPV`/`PERCENT_CPC`/`TARGET_SPEND`/`MAXIMIZE_CLICKS` → 0,
`ENHANCED_CPC` → 1, `TARGET_CPA`/`MAXIMIZE_CONVERSIONS` → 2, `TARGET_ROAS`/`MAXIMIZE_CONVERSION_VALUE`
→ 3 (→ 4 when `TARGET_ROAS` and `ai_max_enabled` — the closest MCP-queryable proxy for Smart
Bidding Exploration; a UI export never sets this true, since it isn't a UI-export column). A
campaign on a strategy not in this table (Commission, Target Impression Share, …) gets
`status="unsupported_strategy"` — held out from classification, never dropped.

**The mismatch signal**, via `_shared/analytics.signals` + `pre_score`:

- `tier_gap = current_tier − recommended_tier`.
- `tier_gap > tier_gap_threshold` (default 1) → **Over-automated**.
- `tier_gap < −tier_gap_threshold` → **Under-automated**.
- **Automation gate** (takes priority over the plain gap check): `conv30 < conv_gate` (default 30 —
  the same "≥ 30 conversions/30 days" gate `SKILL.md` documents) **and** `current_tier ≥ 1`
  (any automated strategy) → **Over-automated (under-data)** — the Critical case.
- Otherwise → aligned (`mismatch == ""`).

A campaign with **zero spend** in the window (`status="no_spend"`) cannot be assessed at all.

## Dual input — MCP or CSV

Per the [foundation contract](../../google-ads-foundation/references/artifact-formats.md#dual-input-mcp-or-csv),
decide the input path **before** pulling anything: a supplied CSV wins outright; otherwise the MCP
is the default live-pull path. The two Data-Maturity judgment components are **always** manual —
neither path can supply them (see "Judgment inputs" below).

### The MCP pull (`mcp__google-ads-mcp__search_search`)

One pull covers structure + 30-day performance:

```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","campaign.bidding_strategy_type",
             "campaign.ai_max_setting.enable_ai_max","metrics.conversions",
             "metrics.cost_micros","metrics.conversions_value"]
conditions: ["segments.date BETWEEN '<30d-start>' AND '<yesterday>'"]
orderings:  ["metrics.cost_micros DESC"]
```

> **Gotcha:** `LAST_30_DAYS` is not a valid GAQL date literal — use an explicit `BETWEEN`, ending
> yesterday (today's data is partial).

**Transcription firewall (mandatory).** Save the raw result to a file (auto-saved by the harness
when large; copy the whole tool result verbatim when small) before anything else happens, then:

```bash
python3 scripts/assemble_findings.py \
  --campaigns <raw-campaigns-file> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-30d "<30d-start> to <yesterday>" \
  -o findings.json
```

### The CSV path (`_shared/csv_input.py`)

Ask the user to export, in the Google Ads UI: **Campaigns → columns**: Campaign, Campaign ID, Bid
strategy type, Conversions, Cost, and (optional) Conv. value, for the 30-day window the report
needs, then **Download → .csv**.

```bash
python3 scripts/assemble_findings.py \
  --csv export.csv \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-30d "<30d-start> to <yesterday>" \
  -o findings.json
```

The CSV path never sets `ai_max_enabled` true (that flag isn't a UI-export column) — a campaign's
tier-4 eligibility is only ever detected via the MCP structure pull. `meta.source` is stamped
`"user_csv"` and surfaced in every report's provenance; never presented as an API pull.

### Judgment inputs (both paths)

`value_variance_score` and `tracking_confidence_score` (0-100 each) are the operator's own
judgment — nothing pulls or exports them. Supply them via `--judgment judgment.json`:

```json
{"1234567890": {"value_variance_score": 70, "tracking_confidence_score": 85}}
```

keyed by `campaign_id` (string). Omitted campaigns fall back to the tunable neutral-assumption
params with `confidence: "assumed"`. This file is still read by `assemble_findings.py` — never
type these numbers directly into `findings.json` (that would bypass the transcription firewall).

## The findings JSON

```json
{
  "meta":   {"client_name","account_id","currency","window_30d","generated","source"},
  "params": {                                    // all optional; defaults = the rule as written
     "conv_target": 30, "conv_gate": 30, "tier_gap_threshold": 1,
     "band_edge_1": 30, "band_edge_2": 50, "band_edge_3": 70, "band_edge_4": 85,
     "volume_weight": 0.40, "value_weight": 0.30, "tracking_weight": 0.30,
     "assumed_value_score": 50, "assumed_tracking_score": 50
  },
  "campaigns": [{"campaign_id","campaign","bidding_strategy_type","ai_max_enabled",
                 "conv30","cost","value","value_score","tracking_score"}]
}
```
`cost`/`value` are in the account currency (already divided by 1e6 on the MCP path). `value_score`
/ `tracking_score` are `null` when the operator supplied no judgment for that campaign.

## Build the deliverable bundle

```bash
# md + html — dependency-free, needs only Python
python3 scripts/build_bidding_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html
# all three (xlsx needs openpyxl; normalizes via LibreOffice) + the in-Claude tuner
python3 scripts/build_bidding_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" \
  --formats md,html,xlsx --emit-widget widget.json
```

Files land in `artifacts/` as `bidding-strategy-maturity_{account}_{date}.{ext}` (`.md`,
`_explorer.html`, `.xlsx`). Run the unit tests with `python3 tests/test_bidding.py`.

**What each format is for** — all rendered by `_shared/render` from one model, so no two can
disagree.
- `*.md` — the narrative / trust layer: provenance header, headline counts, the automation-gate
  sensitivity table, the borderline-campaign ranking, the excluded-campaign lists, and a full
  per-campaign table with each row's `status` and `mismatch` (the no-row-loss layer).
- `*_explorer.html` — the interactive primary: sliders for every tunable param, live counts, a
  gate-sensitivity strip, and the full campaign table with status/mismatch badges + a "qualifying
  only" toggle. The embedded JS computes byte-identical results to the Python model (Node-verified).
- `*.xlsx` — the tunable Controls + Live-filter workbook, with a Snapshot tab and a Status column
  (no row loss). LibreOffice-normalized so it opens in Excel.

## Advisor recommendations (Critical → High → Medium)

Grounded in the model's `mismatch`/`severity` fields — never narrated from raw pulls:

- **Critical** — every `"Over-automated (under-data)"` campaign: revert to Manual CPC / Maximize
  Clicks until `conv_gate` conversions/30d accrue; cite the campaign's `conv30` vs `conv_gate` and
  its `cost` (the spend riding on an under-data automated strategy).
- **High** — every `"Over-automated"` (not under-data) or `"Under-automated"` campaign: move to the
  strategy the `recommended_label` names; cite the `maturity_score` and `tier_gap`.
- **Medium** — `borderline` campaigns (closest to a tier boundary) worth a watch-list entry even
  though not currently flagged; cite `distance_to_edge`.

Strategy changes are applied **manually** (read-only MCP) — the bundle is the plan, not a "done".
