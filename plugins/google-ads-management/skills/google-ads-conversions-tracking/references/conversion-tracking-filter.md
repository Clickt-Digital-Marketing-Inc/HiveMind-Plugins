# Conversions & Tracking Advisor — config health + CVR/CTR trend

A done-with-you advisor over **two datasets**: a conversion-action **config-health checklist**
(deterministic pass/flag rules) and a per-campaign **CVR/CTR trend** (scored via the shared
`_shared/analytics` primitives). Ships the standard three-format analytical bundle: a **markdown
report** (config-health table, manual EC/Consent-Mode checks, sensitivity table, full per-campaign
table), a **self-contained interactive HTML explorer** (sliders over the trend params + live
sensitivity strip + the static config/manual panels), and a **formula-driven xlsx**
(LibreOffice-normalized). Reuses every `google-ads-foundation` convention (micros, dates, dedup) —
load that first.

All three formats are rendered by the shared toolkit (`_shared/render`) from one model
(`scripts/conv_tracking_core.py`), so they can never disagree; this file is the **authoritative**
input/output contract (the scripts' docstrings point here rather than restating it).

## The two datasets

### 1 — Conversion-action config health (`status="config"`, every row kept)

Four deterministic pass/flag rules, each independent (a row can carry several):

- **`dormant_primary`** — an ENABLED, `primary_for_goal = true` action with `0` conversions in the
  pull's window. Automated bidding is optimizing to nothing.
- **`every_counting_lead`** — `counting_type = MANY_PER_CLICK` ("Every" in the UI) on a lead-style
  category (`SUBMIT_LEAD_FORM`, `BOOK_APPOINTMENT`, `REQUEST_QUOTE`, `CONTACT`, `SIGNUP`) — usually
  double-counts a single lead.
- **`legacy_attribution`** — `attribution_model` is a rule-based model
  (`GOOGLE_ADS_LAST_CLICK`, or a `GOOGLE_SEARCH_ATTRIBUTION_{FIRST_CLICK,LINEAR,TIME_DECAY,
  POSITION_BASED}` variant) instead of `GOOGLE_SEARCH_ATTRIBUTION_DATA_DRIVEN`.
- **`duplicate_primary_category`** — two or more ENABLED, `primary_for_goal = true` actions share
  one `category` — ambiguous which one bidding should treat as "the" goal for that category.

Plus one **account-level** check surfaced in `summary.config_no_primary_action`: **no** row is an
ENABLED primary-for-goal action at all — tracking is broken, fix this before touching bids.

### 2 — Per-campaign CVR/CTR trend (`status="scored"`/`"no_benchmark"`)

Two comparable windows (operator-chosen — 7d-vs-prior-7d, `THIS_MONTH`-vs-`LAST_MONTH`, etc., never
literally "90d/30d"). `ctr` and `cvr` are **recomputed** from summed clicks/impressions/conversions
(never trusted from a raw `metrics.ctr`-style field), matching the dedupe-then-recompute convention.
A campaign with **0 clicks in the prior window** has an undefined CVR/CTR baseline → kept as
`status="no_benchmark"`, never scored, never dropped.

Four declarative rules via `_shared/analytics.signals` (see that module's docstring for the
kernel-mirror contract this skill inherits verbatim):

- **`cvr_drop`** — `cvr_curr ≤ cvr_prior × (1 − cvr_drop_pct)` (default **30%** relative drop).
  Requires a scored row (`cvr_prior` is `None`, not `0.0`, for a no-benchmark row — a real zero
  prior CVR must never masquerade as a computed rate — so this rule structurally cannot fire there).
- **`ctr_held_or_up`** — `ctr_curr ≥ ctr_prior × ctr_factor` (default **1.00**) — context, not
  itself a severity flag; combined with `cvr_drop` it becomes:
- **`landing_page_suspect`** (derived, not a `signals` rule) — `cvr_drop` **and** `ctr_held_or_up`
  both fired: CVR fell while CTR held or improved — the ads are working, something after the click
  isn't. Route to the landing page, not the ad copy.
- **`thin_volume`** — `conversions_curr < min_conv_30d` (default **30**). Fires regardless of
  scored status (it needs no prior-window baseline).
- **`below_account_cvr`** — `cvr_curr < account_avg_cvr × cvr_factor` (default **0.50**), where
  `account_avg_cvr` is the click-weighted mean CVR over every **scored** campaign, broadcast onto
  every row (scored or not) the same way the search-term waste filter joins a campaign benchmark
  onto each term. Also fires regardless of scored status.

Severity via `_shared/analytics.pre_score` over the row's unique flags, weights
`{cvr_drop: 4, landing_page_suspect: 6, thin_volume: 1, below_account_cvr: 2}`. Tier (only for
`status="scored"` rows — a no-benchmark row can carry flags but never a tier):
score ≥ 6 → **Critical**, ≥ 3 → **High**, > 0 → **Watch**, else **clean**.

### 3 — Enhanced Conversions / Consent Mode (`status="manual"`, always honest)

**API-blind.** The Google Ads API does not expose EC/Consent-Mode configuration confirmation — this
is not a native UI report either. Every row carries `data_source`:

- `"user_csv"` — the operator filled in a small template (columns `Check, Value, Note`) from the
  account's Conversion Settings / Tag Assistant and handed it over as `--ec-csv`.
- `"not_confirmed"` — no template supplied. Two rows are still emitted
  (`Enhanced Conversions`, `Consent Mode v2`) with `value = "not confirmed via API"` — **never
  silently dropped**, and **never** presented as if the API returned them.

## The three GAQL pulls (`mcp__google-ads-mcp__search_search`)

> **Gotcha:** `LAST_90_DAYS` is **not** a valid GAQL date literal. Use an explicit `BETWEEN`. Keep
> the two windows the same length and end both no later than yesterday.

**1 — Conversion-action config + 30-day conversions:**
```
resource:   "conversion_action"
fields:     ["conversion_action.id","conversion_action.name","conversion_action.status",
             "conversion_action.type","conversion_action.category",
             "conversion_action.primary_for_goal","conversion_action.counting_type",
             "conversion_action.attribution_model_settings.attribution_model",
             "metrics.conversions"]
conditions: ["conversion_action.status = 'ENABLED'",
             "segments.date BETWEEN '<curr-window-start>' AND '<yesterday>'"]
```

**2 — Per-campaign metrics, current window:**
```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","metrics.clicks","metrics.impressions",
             "metrics.cost_micros","metrics.conversions"]
conditions: ["segments.date BETWEEN '<curr-window-start>' AND '<yesterday>'"]
```

**3 — Per-campaign metrics, prior window** (same fields, the comparable prior period):
```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","metrics.clicks","metrics.impressions",
             "metrics.cost_micros","metrics.conversions"]
conditions: ["segments.date BETWEEN '<prior-window-start>' AND '<prior-window-end>'"]
```

**Transcription firewall (mandatory).** Save every pull's raw result to a file — never assemble the
findings JSON by hand:

```bash
python3 scripts/assemble_findings.py \
  --conversion-actions <raw-config-file> \
  --campaign-curr <raw-curr-file> --campaign-prior <raw-prior-file> \
  --ec-csv <optional-manual-export.csv> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-curr "<curr-start> to <yesterday>" --window-prior "<prior-start> to <prior-end>" \
  -o findings.json
```

The assembler dedupes conversion-action rows by id, joins the two campaign pulls by
`campaign_id` (a campaign present in only one window keeps a zero-filled other side — no-row-loss),
embeds control totals as `meta.reconciliation`, and `conv_tracking_core` re-verifies them on every
build. Metric values never pass through the model.

## Dual input — the EC/Consent-Mode CSV

Per `google-ads-foundation`'s dual-input contract, Enhanced Conversions / Consent Mode is **always**
CSV/manual (API-blind — never ask the MCP for it). The template columns:

```
Check,Value,Note
Enhanced Conversions,Enabled (web + leads),Confirmed via Conversion Settings 2026-07-10
Consent Mode v2,Advanced,
```

Assembled via `_shared/csv_input.load_csv_rows` with the skill's `EC_CSV_COLUMN_MAP` (aliases
`Check`/`Setting`, `Value`/`Status`, `Note`/`Notes`). Omitting `--ec-csv` is fine — the two honest
`not_confirmed` rows still ship.

## The findings JSON

```json
{
  "meta":   {"client_name","account_id","currency","window_curr","window_prior","generated",
             "source": "mcp"},
  "params": {"cvr_drop_pct": 0.30, "min_conv_30d": 30, "ctr_factor": 1.00, "cvr_factor": 0.50},
  "conversion_actions": [{"id","name","status","category","type","primary_for_goal",
                          "counting_type","attribution_model","conversions_30d"}],
  "manual_checks":      [{"check","value","data_source","note"}],
  "campaign_trend":     [{"campaign_id","campaign",
                          "clicks_curr","impressions_curr","cost_curr","conversions_curr",
                          "clicks_prior","impressions_prior","cost_prior","conversions_prior"}]
}
```
`cost_*` is in the account currency (already divided by 1e6). `ctr`/`cvr` are **not** stored in the
findings — `conv_tracking_core` recomputes them from clicks/impressions/conversions.

## Build the deliverable bundle

```bash
# md + html — dependency-free, needs only Python
python3 scripts/build_conv_tracking_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html
# all three (xlsx needs openpyxl; normalizes via LibreOffice)
python3 scripts/build_conv_tracking_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html,xlsx
# the in-Claude tuner widget
python3 scripts/build_conv_tracking_report.py \
  --input findings.json --formats "" --emit-widget widget.json
```
Files land in `artifacts/` as `conv-tracking_{account}_{date}.{ext}` (`.md`, `_explorer.html`,
`.xlsx`). Run `python3 tests/test_conv_tracking.py`; check an existing workbook with
`python3 scripts/build_conv_tracking_workbook.py --check --input <file>.xlsx`.

**What each format is for**, all rendered by `_shared/render` from one model:
- `*.md` — provenance header, headline KPIs, the config-health table (every action, pass/flag),
  the manual EC/Consent-Mode table (honestly sourced), the CVR-drop sensitivity table, the
  excluded-campaign (no-benchmark) list, and the full per-campaign trend table with `status`/`tier`
  (the no-row-loss layer). Zero dependencies.
- `*_explorer.html` — the interactive primary: sliders over `cvr_drop_pct`/`min_conv_30d`/
  `ctr_factor`/`cvr_factor`, live KPI tiles, a live sensitivity strip, and static panels for the
  config-health checklist and the manual checks (not tunable — they don't depend on the trend
  params). Self-contained, opens in any browser.
- `*.xlsx` — **Controls** (tunable trend params + self-rewriting tier logic + live `COUNTIF`
  results), **Campaign trend** (every campaign + `Status`; scored rows carry formula columns
  mirroring the kernel exactly — `CVR drop?`, `CTR held/up?`, `Landing page suspect?`,
  `Thin volume?`, `Below account CVR?`, `Score`, `Tier`), **Snapshot** (the config-health checklist,
  the manual checks, and the sensitivity table — a static render of the same sections as the
  markdown report). Normalized through LibreOffice by default; `--no-normalize` overrides at the
  risk of needing "Repair" in Excel-for-Mac.

**Honesty rules (hard).**
- Never imply the API confirms Enhanced Conversions / Consent Mode — every `manual_checks` row
  carries `data_source ∈ {"user_csv","not_confirmed"}`, never anything implying an API pull.
- No-row-loss holds independently for all three arrays: `model["rows"]` (trend, the primary/tunable
  dataset — enforced by the shared render toolkit's `require_model`), `model["config_rows"]`, and
  `model["manual_rows"]` (enforced by this skill's own tests).
- A campaign with no prior-window benchmark keeps its per-row flags that don't need a baseline
  (`thin_volume`, `below_account_cvr`) but **never** a tier — tiering requires `status="scored"`.
