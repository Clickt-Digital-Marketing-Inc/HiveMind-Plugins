---
name: google-ads-products
description: Use when auditing Google Ads Shopping/Performance Max PRODUCT performance — finding zombie products (spending with zero conversions), surging products (conversions accelerating) and declining products (conversions collapsing), account-aggregated per product across Shopping + PMax. Pulls product-level data via the Google Ads MCP (shopping_performance_view) — or three Google Ads UI "Products" CSV exports when the MCP is unavailable — over a 30-day and two 14-day windows, and emits a three-format analytical bundle (markdown report with Critical/High/Medium recommendations + self-contained interactive HTML explorer + tunable formula-driven .xlsx) plus three per-segment action worklists.
---

# Google Ads — Products (Shopping/PMax segments)

## Bundled path resolution

Before running bundled scripts, set `PLUGIN_ROOT` to the absolute path of this plugin directory: the nearest ancestor of this `SKILL.md` that contains either `.claude-plugin/plugin.json` or `.codex-plugin/plugin.json`. Resolve it from the loaded skill path; do not assume a host-specific environment variable or the current working directory. Then run commands that reference `${PLUGIN_ROOT}` unchanged.

Turn product-level performance into action: stop the bleed on products that spend without converting,
double down on the ones accelerating, and investigate the ones falling off — all benchmarked against
each product's **own** recent trend, account-aggregated across Shopping and Performance Max.

**Cadence:** product segments **bi-weekly** (the windows are 14-day); zombie sweep **monthly** at minimum.

**REQUIRED BACKGROUND:** load `google-ads-foundation` first.

## When to use
- "Which products are wasting spend?", "what's surging / declining?", "audit my Shopping products".
- Shopping or Performance Max campaigns with a product feed where spend isn't converting evenly.
- Before a budget reallocation across products, or a feed/exclusion cleanup.

## Step 0 — choose the input path (MCP or CSV)
This skill's data is **not** API-blind — `shopping_performance_view` is queryable — so default to
the **MCP path** below when it's reachable. Use the **CSV path** when the user already supplies the
three exports, or the MCP is unreachable/misconfigured (e.g. `login-customer-id` not set): ask for
three Google Ads UI **Products** report exports (same three date ranges as the pulls below) per
[references/product-segments-filter.md#csv-manual-input-path](references/product-segments-filter.md#csv-manual-input-path)
(exact columns, the `CSV_COLUMN_MAP`, and the assembler's `--csv-30d/-14d/-prev14d` flags). Both
paths run through the same transcription firewall and the same
`product_filter_core.merge_product_windows` join, so they yield an identical model — the report's
"Data source" line surfaces which one ran (never presented as an API pull when it wasn't). See the
`google-ads-foundation` dual-input contract for the full decision order.

## Pull the data (MCP path)
Product reporting is **not** used elsewhere in this plugin — **probe first**, then pull three windows.
Full spec, field list, date math, and the PMax-coverage caveat are in
[references/product-segments-filter.md](references/product-segments-filter.md).

1. **Probe** — `mcp__google-ads-mcp__metadata_get_resource_metadata` for `shopping_performance_view`
   to confirm the selectable product segments/metrics on the live API version.
2. **Products, last 30 days** — `shopping_performance_view` with `segments.product_item_id`,
   `segments.product_title`, `segments.product_merchant_id`, `campaign.advertising_channel_type`,
   `metrics.conversions/cost_micros/impressions` (the zombie window + master product list).
3. **Products, last 14 days** and **previous 14 days** — the same resource, `product_item_id` +
   `metrics.conversions/impressions` (the surge/decline comparison; the 14-day pull also confirms
   merchant presence).

Use `metrics.conversions` (primary, attribution-modeled, often fractional) — never
`metrics.all_conversions`. The assembler script aggregates per `product_item_id` (sums across
campaigns/channels, `cost_micros/1e6`, unions channels) and writes the findings JSON (schema in the
reference).

> **Numbers never pass through the model.** Save every pull's raw result to a file (auto-saved
> `tool-results/*.txt` for big pulls; verbatim copy of the whole `{"result": [...]}` JSON for
> inline ones) and build the findings JSON with
> [scripts/assemble_findings.py](scripts/assemble_findings.py) — never type metrics into a JSON by
> hand. The assembler embeds reconciliation control totals that the core re-verifies on every
> build; hand-assembled or edited findings hard-fail. See the reference doc's "Transcription
> firewall" section for the exact command.

> **Channel coverage.** `shopping_performance_view` returns per-product metrics across **both Shopping
> and PMax** campaigns (verified live) — attribute channel by joining `campaign.advertising_channel_type`
> (or filtering PMax-vs-Shopping campaign ids). Coverage needs a Merchant Center feed: lead-gen accounts
> with no feed return 0 product rows — report that honestly ("0 products is still a valid result").

## Diagnose — three product segments
Account-aggregated per product. Defaults match the rule "as written" (surge 1.50, decline 0.50,
zombie cost floor 0, zombie max conv 0):

| Segment | Trigger | Action |
|---|---|---|
| **Zombie** (wasted spend) | `conv(30d) ≤ 0` AND `cost(30d) > 0` AND `merchant id present (14d)` | exclude / pause the product |
| **Surging** | `conv(14d) > 1.50 × conv(prev-14d)` AND `conv(prev-14d) > 0` | scale budget / priority |
| **Declining** | `conv(14d) < 0.50 × conv(prev-14d)` | investigate feed / price / stock |

Segments are mutually exclusive; precedence **Zombie > Surging > Declining**. Products with no spend
**and** no impressions in any window are held out as **inactive** (kept, never scored, never dropped).
Conservative by design: a healthy account often flags **few or zero** products — present that honestly
and use the explorer's sliders + sensitivity strips to surface near-misses rather than forcing hits.

## Advisor loop: emit → report → recommend → offer-apply
This skill is a shoulder-to-shoulder advisor, not a report generator (the
`google-ads-foundation` advisor output contract). After `build_product_report.py` runs:

1. **Emit the bundle** (below) — md + the self-contained HTML explorer + xlsx + the three worklists.
2. **Open with the hero HTML report** — present the `*_explorer.html` first (file path + what it
   shows: sliders + live sensitivity), before any narration.
3. **Present the recommendations** — the builder prints them (and they're in the md's
   Recommendations table): **Critical** — exclude/pause the **Zombie** products, citing the model's
   zombie count and 30-day wasted cost; **High** — scale budget/priority for **Surging** products
   before the spike passes, citing the surge count and multiple; **Medium** — investigate
   **Declining** products (feed errors, price changes, out-of-stock, increased competition), citing
   the decline count and multiple; re-check after the next 14-day window. Every number quoted comes
   from the model (the builder's printed summary or the md/HTML), never from memory. An empty tier
   is an honest clean result — say so.
4. **Offer the worklist CSVs** — the three per-segment worklists are already built (not gated behind
   acceptance, since they're analytical/manual worklists, not Editor imports); point at them and the
   apply path (Shopping/PMax listing groups) — done-with-you, not fire-and-forget.

## Generate artifacts (in `artifacts/`)
The standard three-format analytical bundle, from one findings JSON via
[scripts/build_product_report.py](scripts/build_product_report.py) (`--formats md,html,xlsx`), all
rendered by the shared `_shared/render` toolkit from one model:
- `*.md` — narrative: provenance (incl. data source), headline counts, the clean-result framing,
  the **Recommendations (Critical → High → Medium)** table, surge/decline sensitivity, inactive
  list, **and a full per-product table** (status + segment; no row loss).
- `*_explorer.html` — **interactive primary**: self-contained sliders + live sensitivity strips,
  opens in any browser (no install/Excel/cloud); embedded JS matches the Python model exactly.
- `*.xlsx` — tunable Controls + Live-products + Sensitivity workbook with a Status column (no row
  loss); needs `openpyxl`, LibreOffice-normalized so it opens in Excel.
- `*_charts/*.svg` — deterministic Vega-Lite charts (30-day spend-by-segment bar, cost-vs-conversions
  scatter with segments colored) rendered at build time and referenced from the md; the explorer
  renders the same charts live from the sliders. `--no-charts` skips them.

> **Charts are generated, never authored.** Every chart is produced by `build_product_report.py`
> through the shared chart module from the spec's `SPEC["charts"]` declaration. Never hand-write
> or edit SVG, Vega-Lite JSON, chart HTML, or the vendored JS; never "fix" a chart in the output
> file. If a chart is wrong, the spec or the model is wrong — change it there and re-run the
> builder. Same run, same chart, byte for byte.

The interactive **tuner** (`--emit-widget`) embeds only the scored products (inactive ones — zero
cost and impressions in every window — can never be segmented) so it stays lean on large catalogs;
headline counts come from the embedded full-model summary. Live-preview only — the md/html/xlsx
above always carry the full universe.

Plus three **action worklists** (`_zombie_worklist.csv`, `_surging_worklist.csv`,
`_declining_worklist.csv`). These are **analytical/worklist** deliverables: product-level exclusions
are **not** cleanly Google Ads Editor-importable — apply them manually in the Shopping/PMax listing
groups. (Editor-importable apply files like negatives/keywords come from other skills via
`${PLUGIN_ROOT}/skills/google-ads-foundation/scripts/make_editor_csv.py`.)

```bash
python3 "${PLUGIN_ROOT}/skills/google-ads-products/scripts/build_product_report.py" \
  --input findings.json --outdir artifacts --brand "{Client Name}" --formats md,html,xlsx
```

## Resources
- [references/product-segments-filter.md](references/product-segments-filter.md) — **authoritative**
  segment spec, the three GAQL pulls + metadata probe, date math, conversion-metric + PMax-coverage
  honesty, findings-JSON schema, output bundle, and the Excel-open honesty.
- [scripts/product_filter_core.py](scripts/product_filter_core.py) — single-source classification
  engine / model (stdlib only); its math is mirrored in the spec's `js_kernel` and the xlsx formulas.
  Also owns `merge_product_windows` (the MCP/CSV-shared window join) and `recommendations` (the
  Critical/High/Medium advisor output, presentation-only over the model — no kernel-parity mirror).
- [scripts/assemble_findings.py](scripts/assemble_findings.py) — the transcription-firewall
  assembler for BOTH input paths: `assemble()` (saved raw GAQL pulls) and `assemble_csv()` (three
  Google Ads UI CSV exports, `CSV_COLUMN_MAP`); see
  [references/product-segments-filter.md#csv-manual-input-path](references/product-segments-filter.md#csv-manual-input-path).
- [scripts/product_filter_spec.py](scripts/product_filter_spec.py) — md/html render spec (KPIs,
  sections, full row table, controls, columns, JS kernel) consumed by the shared toolkit.
- [scripts/product_filter_xlsx_spec.py](scripts/product_filter_xlsx_spec.py) — the xlsx workbook
  layout (Controls / Live products / Sensitivity), pure data, no openpyxl.
- [scripts/build_product_report.py](scripts/build_product_report.py) — thin CLI: builds the
  md/html/xlsx bundle + the three worklists via `_shared/render`.
- [scripts/build_product_report_workbook.py](scripts/build_product_report_workbook.py) — thin xlsx CLI
  wrapper (`--check`, `--normalize/--no-normalize`).
- [tests/test_filter.py](tests/test_filter.py) + [tests/product-sample-findings.json](tests/product-sample-findings.json)
  — unit tests (fixture, no-row-loss, dedupe, empty, fractional-conv, merchant-empty edge, bundle
  parity + lazy import) and the synthetic fixture.

## Common mistakes / red flags
- **Don't claim PMax coverage you didn't get** — label channels from the actual pulls; many accounts
  only return Shopping item rows.
- A product with spend but an **empty merchant id** is not a Zombie (it may have left the feed) — it's
  shown, scored, and can still Surge/Decline, but never flagged Zombie.
- Don't act on a single 14-day spike/dip in isolation for low-volume products — fractional, attribution
  -modeled conversions are noisy at small N; confirm against the next window.
- Product exclusions are **manual** (read-only MCP, and not cleanly Editor-importable) — deliver the
  worklists and apply in the listing groups.
- A clean account legitimately returns few/zero flags — present it honestly; use the sliders to show
  where products would qualify if the multipliers were relaxed.
