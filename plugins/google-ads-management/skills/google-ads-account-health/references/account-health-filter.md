# Account Health — Five Structural Checks (reduced bundle)

Five heterogeneous red-flag checks across different entity grains, modeled as
**per-check scored rows** in one flat list rather than forced into a single
wide interactive explorer (a table mixing ad-group and campaign grain with
mostly-null columns per row reads poorly as one live-tunable surface — see
"Emitted formats" below). Reuses every `google-ads-foundation` convention
(micros, dates, dedup) — load that first. All formats are rendered by the
shared toolkit (`_shared/render`) from one scoring engine
(`scripts/health_core.py`), so they can never disagree; this file is the
**authoritative** input/output contract (the scripts' docstrings point here
rather than restating it).

## The five checks

| check | grain | fires when | status |
|---|---|---|---|
| `sprawl` | ad_group | enabled keyword count ≥ 20 **AND** ad-group CTR (30d) < 3% | `scored` |
| `no_negatives` | campaign (Search) | campaign-level negative keywords ≤ 0 | `scored` |
| `automation_no_data` | campaign | bidding is automated **AND** conversions(30d) < 30 | `scored` |
| `naming` | campaign | `campaign.name` fails the default convention regex | `config` — the regex is an unconfirmed default; confirm segments/geo with the user before renaming |
| `pmax_cannibalization` | campaign (PMax) | the account also runs an enabled brand Search campaign | `manual` — the read-only API cannot confirm whether an account-level negative-keyword / brand-exclusion list is attached to the PMax campaign; this always needs a human to confirm in the UI |

Every entity in scope gets **one row per applicable check** (a Search
campaign gets 3 rows: `no_negatives`, `automation_no_data`, `naming`; a PMax
campaign gets those 3 **plus** `pmax_cannibalization`; an ad group gets 1
row: `sprawl`). Nothing is ever dropped — every row carries `status` and
`is_flagged`, and `pre_score` is 0 on any row that didn't trip its check's
full condition set.

Default naming regex (confirm/adjust with the user, and in the findings
`params.naming_regex` — **not** tunable from the xlsx Controls tab):
```
^(Brand|NonBrand)_(US|UK|CA|DE|FR)_(Search|Display|PMax|Video|Demand)_[A-Z]{3,6}_\d{4}$
```

Automated bidding strategy types (tunable set — `params.automated_bidding_types`):
`MAXIMIZE_CONVERSIONS`, `MAXIMIZE_CONVERSION_VALUE`, `TARGET_CPA`, `TARGET_ROAS`,
`TARGET_IMPRESSION_SHARE`.

Brand-campaign heuristic: a campaign is "brand" when its name (casefolded)
starts with `params.brand_name_prefix` (default `"brand"`) — a starting
template, confirm with the user like the naming regex.

## Scoring — `_shared/analytics.signals` + `.pre_score`

Every row's `flags` come from ONE declarative rule set run across the whole
mixed-grain row list (`_shared/analytics.signals`); fields that don't apply
to a check are `None` on that row, and a missing operand means the rule
simply never fires for that row — so one rule set safely spans all five
checks without special-casing. A check's `is_flagged` is an AND of its
required flag ids (composite logic — `signals()` only expresses single-field
threshold rules, exactly like every other skill's own `classify_row`).
`pre_score` (`_shared/analytics.pre_score`) sums the fired flags' weights —
0 when not flagged, otherwise the fixed sum for that check (used to rank the
"top structural fixes" list across checks and to drive the xlsx Pre-score
column). See `scripts/health_core.py`'s module docstring + `WEIGHTS` /
`CHECK_FLAG_SETS` for the exact rule/weight table (single source of truth;
not duplicated here).

Severity is a **fixed per-check tier** (not derived from pre_score magnitude
— these are structural/binary facts across incomparable entity grains, so a
cross-check magnitude comparison would be arbitrary): `automation_no_data` =
Critical, `sprawl` / `no_negatives` / `pmax_cannibalization` = High,
`naming` = Medium.

## The four GAQL pulls (`mcp__google-ads-mcp__search_search`)

**1 — Enabled keywords per ad group** (for the sprawl count):
```
resource:   "ad_group_criterion"
fields:     ["campaign.id","ad_group.id"]
conditions: ["ad_group_criterion.type = 'KEYWORD'",
             "ad_group_criterion.negative = false",
             "ad_group_criterion.status = 'ENABLED'"]
```
Count rows per `(campaign.id, ad_group.id)` — the pull is intentionally
narrow (no names) since names come from pull 2.

**2 — Ad-group performance, last 30 days** (for sprawl's CTR bar):
```
resource:   "ad_group"
fields:     ["campaign.id","campaign.name","ad_group.id","ad_group.name",
             "metrics.clicks","metrics.impressions"]
conditions: ["segments.date BETWEEN '<30d-start>' AND '<yesterday>'",
             "ad_group.status = 'ENABLED'"]
```

**3 — Campaign structure + bidding + conversions, last 30 days**:
```
resource:   "campaign"
fields:     ["campaign.id","campaign.name","campaign.status",
             "campaign.advertising_channel_type","campaign.bidding_strategy_type",
             "metrics.conversions","metrics.cost_micros"]
conditions: ["segments.date BETWEEN '<30d-start>' AND '<yesterday>'",
             "campaign.status != 'REMOVED'"]
```
Use `metrics.conversions` (the account's primary, attribution-modeled,
possibly-fractional goal) — never `metrics.all_conversions`. `metrics.cost_micros`
is the 30-day window spend that drives **campaign liveness** (`_shared/analytics.segment_liveness`,
HM-603): a campaign is `live` (ENABLED + spend > 0), `recently_active` (paused-mid-window, or
enabled-but-idle), or `dormant` (not ENABLED + zero 30-day spend). This is a **two-band-honest**
adoption — the skill has a single 30-day window, so there is no prior-window signal; the
"spent only in the prior window" liveness path is not derivable here. Dormant campaigns (and
their ad groups) are kept and tagged but **excluded from every check's scored universe** — this
is what stops long-dead campaigns from manufacturing zombie findings (e.g. an automated-bidding
"revert to Manual CPC" flag on a campaign that stopped spending months ago).

**4 — Campaign-level negative keywords** (for `no_negatives`):
```
resource:   "campaign_criterion"
fields:     ["campaign.id"]
conditions: ["campaign_criterion.type = 'KEYWORD'",
             "campaign_criterion.negative = true"]
```
Count rows per `campaign.id`.

> **Gotcha — negatives on campaigns outside pull 3's scope.** Pull 3 filters
> `campaign.status != 'REMOVED'`; pull 4 (negatives) has no such filter, so a
> negative can reference a campaign id that never appears in pull 3 (most
> often a REMOVED campaign). `assemble_findings.py` counts these separately
> as `orphan_negatives` — see "The findings JSON" below — rather than
> silently losing them; the reconciliation total covers the ENTIRE raw
> negatives pull, not just the ids that joined to a pulled campaign.

> **Gotcha:** `LAST_30_DAYS` **is** a valid GAQL literal (unlike `LAST_90_DAYS`),
> but this skill uses an explicit `BETWEEN` for a stable, reproducible window
> label — end the window **yesterday** (today's data is partial).

**Transcription firewall (mandatory).** Save each pull's raw result to a file
before anything else happens, then build the findings JSON with
`scripts/assemble_findings.py` — never assemble it by hand:

```
python3 scripts/assemble_findings.py \
  --keywords <raw-1> --adgroup-perf <raw-2> --campaigns <raw-3> --negatives <raw-4> \
  --client-name "{Client Name}" --account-id {account} --currency {CUR} \
  --window-30d "<30d-start> to <yesterday>" \
  -o findings.json
```

## The findings JSON

```json
{
  "meta":   {"client_name","account_id","currency","window_30d","generated","source"},
  "params": {                                        // all optional; defaults in health_core.py
     "sprawl_min_keywords": 20, "sprawl_max_ctr": 0.03,
     "negatives_max_count": 0, "automation_min_conversions": 30,
     "naming_regex": "^(Brand|NonBrand)_...$",
     "automated_bidding_types": ["MAXIMIZE_CONVERSIONS", "..."],
     "brand_name_prefix": "brand"
  },
  "ad_groups": [{"campaign_id","campaign","ad_group_id","ad_group",
                "keyword_count","clicks","impressions"}],
  "campaigns": [{"campaign_id","campaign","status","channel_type",
                "bidding_strategy_type","conversions_30d","negative_count"}],
  "orphan_negatives": {"count", "campaign_ids", "status"}   // MCP path only, see below
}
```
`keyword_count` / `negative_count` are raw counts (not micros). `conversions_30d`
uses the primary conversion metric (may be fractional).

`orphan_negatives` is the no-row-loss home for negatives whose `campaign.id`
never appears in the campaigns pull (e.g. REMOVED campaigns): `count` is the
number of such negative rows, `campaign_ids` the distinct ids they reference,
`status` is always `"out_of_scope"` (never scored — there is no campaign row
to attach a check to). `health_core.load_findings` reconciles
`sum(campaigns[].negative_count) + orphan_negatives.count` against the raw
negatives-pull total embedded in `meta.reconciliation.raw_totals.negatives`
at assembly time — a findings JSON that drops or edits either side without
the other fails to load. The CSV path (below) joins `negative_count` straight
onto each campaign row by name — there is no separate negatives pull to
orphan against — so it never emits `orphan_negatives`; `health_core` treats
an absent field as `{"count": 0, "campaign_ids": [], "status": "out_of_scope"}`.

## Dual input — the CSV path (`_shared/csv_input.py`)

When the MCP is unavailable or the user prefers a UI export, run
`scripts/assemble_from_csv.py` instead — it produces the **identical**
findings shape (`meta.source = "user_csv"`). Two exports, joined by
campaign/ad-group **name** (a CSV export carries no numeric IDs unless added
by the user):

- **Ad groups** report (`--adgroups-csv`) — columns `Campaign`, `Ad group`,
  `Clicks`, `Impr.`, plus a **hand-added** `Ad group keywords (enabled)`
  column (Keywords view, filter to enabled + non-negative, group by ad
  group, count rows, paste into the export). This count is not a native UI
  export column — the skill is honest about that rather than pretending
  otherwise.
- **Campaigns** report (`--campaigns-csv`) — columns `Campaign`,
  `Campaign state`, `Campaign type`, `Bid strategy type`, `Conversions`,
  plus a **hand-added** `Campaign negative keywords` column (Negative
  keywords view, filter by campaign, count rows).

Both are UNVERIFIED honesty callouts, not fabricated data: if a column is
missing, `assemble_from_csv.py` raises `CsvInputError` naming exactly what's
absent, and the CSV path never claims to be an API pull (`meta.source`
surfaces in the report provenance).

## Build the deliverable bundle

```bash
python3 scripts/build_health_report.py \
  --input findings.json --outdir artifacts --brand "{Client Name}" \
  --formats md,xlsx
```
Files land in `artifacts/` as `account-health_{account}_{date}.{ext}` (`.md`,
`.xlsx`) plus the skill-specific `_action_plan.md`, `_renaming.md`, and
`_pause_list.csv`.

## Emitted formats (for M3.1 / HM-547)

**`["md", "xlsx"]` — no HTML explorer.** Five heterogeneous checks across two
entity grains (ad_group, campaign) with mostly-null columns per row do not
read well as one wide interactive table — the catalog entry for this skill
must declare `formats: ["md", "xlsx"]` (`html: false`), per the reduced-
bundle sanction in HM-545. The tunable xlsx (`Controls` sheet, 4 numeric
thresholds — sprawl min keywords, sprawl max CTR, negatives max count,
automation min conversions) is this skill's interactive surface; naming and
PMax-cannibalization are not numerically tunable (regex / manual
confirmation) and are called out as such in the Controls sheet's logic text.

**Why `negative_keywords.csv` is not emitted.** The pre-advisor SKILL.md
promised a `negative_keywords` Editor CSV, but this skill's `no_negatives`
check only knows a campaign has too few negatives — never which specific
terms are junk (that needs term-level search-query data this skill doesn't
pull). Fabricating placeholder terms would be actively harmful if imported.
The action plan instead hands that check to `google-ads-keywords-search-terms`
for term-level candidates; this skill instead retains `pause_list.csv`
(ad-group segmentation worklist, from flagged `sprawl` rows), `renaming.md`
(campaigns failing `naming`, confirm-with-user), and `action_plan.md`
(everything flagged, ranked by severity then pre_score).

## What each format is for

- `*.md` — provenance header, per-check thresholds, per-check sections
  (flagged rows only, with the check's own columns), the **"top structural
  fixes"** ranked-by-pre_score list, and a **full no-row-loss table** (every
  checked entity, every check, `status` + `Flagged?` + `pre_score`).
- `*.xlsx` — `Controls` (4 tunable thresholds + self-rewriting logic text +
  live `COUNTIFS` results), `Live checks` (every row, `Flagged?`/`Pre-score`
  formula columns that branch on the `Check` column), `Checks snapshot`
  (static per-check tables + top fixes, same content as the md sections).
- `*_action_plan.md` / `*_renaming.md` / `*_pause_list.csv` — see above.

**Excel-open honesty.** Same as every skill in this plugin: `soffice`
normalizes the xlsx so it opens reliably in Excel; the build **fails (exit
2)** if `soffice` is missing rather than shipping a file that may not open.
