# Artifact Formats

Because the MCP is read-only, each skill's deliverable is a file the user applies manually —
usually via **Google Ads Editor** (Account → "Make multiple changes" / paste, or CSV import) or
the UI bulk-upload. Write artifacts to an `artifacts/` folder in the working directory, named
`{skill}_{account}_{YYYY-MM-DD}_{type}.csv|md`.

Generate CSVs with [../scripts/make_editor_csv.py](../scripts/make_editor_csv.py) so headers stay
correct and consistent. The script takes a JSON list of rows + a `--type` and emits the right
columns.

## CSV types and columns

### negative_keywords
Add negatives at campaign or ad-group level (leave `Ad Group` blank for campaign-level).
```
Campaign,Ad Group,Negative Keyword,Match Type
NonBrand_US_Search_CRM_2026,,free crm,Phrase
NonBrand_US_Search_CRM_2026,,crm jobs,Phrase
```
Match Type ∈ {Broad, Phrase, Exact}. Default new negatives to **Phrase** unless the term is a
single junk token (then Exact is fine). Never default to Broad negatives — they can silently block
valid traffic; only use Broad with explicit justification.

### add_keywords
Promote high-converting search terms to exact-match keywords in a themed ad group.
```
Campaign,Ad Group,Keyword,Match Type,Max CPC
NonBrand_US_Search_CRM_2026,CRM - Demos,crm software demo,Exact,
```
Leave Max CPC blank under Smart Bidding.

### bid_adjustments
Device/audience/keyword bid modifiers, or keyword max CPC under manual bidding.
```
Campaign,Ad Group,Keyword,Match Type,Max CPC,Bid Adjustment,Level
Brand_US_Search_CRM_2026,Core,,,,-40%,Device: Mobile
```
Express `Bid Adjustment` as a signed percent; put the target in `Level` (e.g. "Device: Mobile",
"Audience: Past converters").

### budget_changes
Daily budget proposals (apply manually; ≤ +20% per change).
```
Campaign,Current Daily Budget,Proposed Daily Budget,Change %,Reason
NonBrand_US_Search_CRM_2026,80.00,96.00,+20%,Lost IS (budget) 28% with target CPA met
```

### pause_list
Entities to pause (3× kill rule, low-CTR keywords, fatigued ads).
```
Campaign,Ad Group,Entity Type,Entity,Reason
NonBrand_US_Search_CRM_2026,Generic,Keyword,"crm tool [Broad]",Spent 3.4x tCPA, 0 conv (30d)
```

### product_actions
Per-segment product worklists from the `google-ads-products` skill (Zombie / Surging / Declining).
```
Segment,Product Item ID,Product Title,Merchant ID,30d Cost,Conv 14d,Conv Prev 14d,Action,Reason
Zombie,SKU-1001,"Blue Widget, Large",1234567,184.20,0,0,Exclude / pause,Spending with zero conversions over 30 days while still in the merchant feed.
```
**Not a Google Ads Editor import.** Unlike negatives/keywords, product-level exclusions are managed
in the Shopping/PMax **listing groups** (or product-group edits) in the UI, not via a generic Editor
CSV. Treat this file as a **prioritized manual worklist**: Zombie → exclude/pause the product;
Surging → ensure budget/priority; Declining → investigate feed/price/stock. The
`google-ads-products` skill writes one CSV per segment alongside its md/html/xlsx report bundle.

## Markdown deliverables

### Report (`*_report.md`)
- Header: account name + ID, date range, skill, currency.
- Diagnosis section with the numbers vs thresholds.
- Prioritized recommendations (Critical → High → Medium).
- "Artifacts generated" list (filenames).
- "Manual / out-of-MCP" callouts.

### Action plan (`*_action_plan.md`)
Ordered checklist the user works through, each line: action · where to apply (Editor/UI) · expected
effect · linked artifact file. Quick wins (< 15 min, high impact) first.

## Apply path (tell the user)
1. Open Google Ads Editor → Account → download latest.
2. Import the CSV (or paste under the matching entity type) → review the proposed changes.
3. Post changes. Editor shows a diff before pushing — nothing goes live until the user posts.

## Dual input (MCP or CSV)

Every bundle/advisory skill accepts its data from **either** the Google Ads MCP **or** a
user-supplied CSV (a Google Ads UI export). Both paths run the same transcription-firewall +
reconciliation discipline and must yield an **identical findings/model shape** — the skill's
core cannot tell them apart, except by the honest `meta.source` label. Never build a skill that
works only when the MCP is connected.

### Step 0 — select the input path (before any pull)

Do this up front, before querying anything:

1. **User already gave a CSV** (a file path or an attached export) → CSV path. Don't also pull
   the MCP for the same data.
2. **The data is API-blind** — the Google Ads API simply does not return it — → CSV/manual path,
   always. Known API-blind datasets: **Auction Insights competitor rows**, **Customer Match
   match rates / list sizes**, **Enhanced-Conversions and Consent-Mode configuration
   confirmation**. Never imply the MCP returned these.
3. **MCP reachable and the dataset is queryable** → MCP path (the default for live pulls).
4. **MCP missing, erroring (e.g. `login-customer-id` not set), or the user prefers an export** →
   ask for the CSV export and use the CSV path. Tell the user exactly what to export (below).
5. **Ambiguous** (both available, neither implied) → ask which the user wants; don't guess.

### The MCP path (recap)

`search_search` results land in files (`tool-results/*.txt` or verbatim inline copies); the
skill's `assemble_findings.py` parses them into the findings JSON with `meta.reconciliation`
control totals. See the transcription-firewall convention in [../SKILL.md](../SKILL.md).

### The CSV path — `_shared/csv_input.py`

The shared module `_shared/csv_input.py` (documented with runnable examples in
[`_shared/README.md`](../../../_shared/README.md)) is the CSV twin of `assemble_findings.py`.
The skill calls it — the model never transcribes the file's numbers:

```python
import sys; sys.path.insert(0, "<plugin-root>/_shared")
from csv_input import assemble_from_csv, load_csv_rows, CsvInputError

rows, findings = assemble_from_csv(
    csv_path,
    column_map=COLUMN_MAP,                 # the skill's own map — see below
    required_fields=(...),                 # logical fields that anchor the header scan
    reconcile_spec={"array": "<findings array>", "sums": [<numeric fields>]},
    meta={"client_name": ..., "account_id": ..., "currency": ..., ...})
```

Multi-CSV skills call `load_csv_rows` per file and run `reconcile.build` over the merged arrays
themselves, exactly like an MCP-path assembler.

**The per-skill `column_map` convention.** Each skill owns one `COLUMN_MAP` — a dict with one
entry per **logical field** its findings rows carry:

```python
COLUMN_MAP = {
    "term": {"aliases": ["Search term", "Search terms"], "type": "str"},
    "cost": {"aliases": ["Cost"], "type": "num"},   # "Cost (CAD)" matches too
    "ctr":  {"aliases": ["CTR", "Interaction rate"], "type": "pct"},
}
```

- `aliases` — every header spelling the Google Ads UI may export (locale/version variance);
  matching is case-insensitive, whitespace-collapsed, BOM/quote-stripped, and tolerates a
  parenthesised suffix (`Cost (CAD)` matches `Cost`).
- `type` — `str` (default) · `num` (float; locale-tolerant — group/decimal separators in either
  order (`1,234.56`, `1.234,56`), no-break-space groups, currency symbols either side, `%`, absent
  markers `--`/dashes → 0.0; single-dot `1.234` keeps the en reading, HM-785) · `pct` (percent-scale
  → fraction: `12.3%` → 0.123). Need different absent-cell semantics? Call
  `_shared/csv_input.parse_num(v, default)` — never hand-roll a second number parser.
- Title rows above the real header and `Total: ...` summary rows are handled (localized summary
  labels too — `Total : ...`, `Gesamt: ...`; the colon is required); missing required
  columns and ambiguous mappings raise `CsvInputError` naming the fields and accepted aliases.
- When a real export uses an unmapped header spelling: add the alias **and a fixture test**, and
  append the lesson to the project's Lessons Log.

**Asking the user for the export.** Name the exact UI report (e.g. *Insights & reports → Search
terms*), the **date range the skill's window requires**, the columns the `column_map` needs, then
**Download → .csv** and share the file path.

**Honesty.** `assemble_from_csv` stamps `meta.source = "user_csv"`; the report/artifact
provenance must surface it. Never present CSV-sourced findings as an API pull. Reconciliation
stays mandatory on both paths — findings without control totals warn/fail UNVERIFIED.

### Dual-input checklist (per skill)

- [ ] `COLUMN_MAP` declared in the skill's scripts, one entry per logical findings field, with
      UI-export aliases and types.
- [ ] SKILL.md documents both paths: the GAQL pulls (cookbook refs) **and** the UI export to
      request (report name, window, columns).
- [ ] Input-selection Step 0 runs before any pull; API-blind data is never promised from the MCP.
- [ ] MCP-vs-CSV parity proven: the same data through both paths yields an identical model
      (a fixture test, like `_shared/tests/test_csv_input.py`'s identical-shape assertion).
- [ ] `meta.source` surfaced in the report provenance on the CSV path.

## Advisor output contract

Every bundle/advisory skill is a **shoulder-to-shoulder advisor**, not a report generator. After
computing the model it runs this loop, in order — each step grounded in the model the builder
just wrote, never in re-narrated raw data:

### The loop: emit → report → recommend → offer-apply

1. **Emit the bundle.** Run the skill's builder (`build_*.py --formats md,html,xlsx`) from the
   reconciled findings JSON into `artifacts/`. The bundle is the skill's declared formats — the
   full three-format set (md + self-contained HTML explorer + tunable xlsx + charts) or the
   skill's documented reduced bundle. No-row-loss and `status` per row hold regardless.
2. **Open with the hero HTML report.** The `*_explorer.html` is the **primary deliverable** —
   present it first (file path + one line on what it shows), before any narration. It is
   self-contained (inline CSS/JS, embedded data, zero external references) and opens in any
   browser. Where the skill has a tuner widget (`--emit-widget`), show it alongside. If the
   skill's documented reduced bundle has no HTML explorer, open with the md report instead —
   the loop is unchanged; the hero is whatever the skill's richest declared format is.
3. **Present prioritized recommendations** — grouped **Critical → High → Medium** (taxonomy
   below), each one citing the model's numbers (rule below). Recommendations live in the md
   report *and* are presented conversationally — the advisor talks the user through them.
4. **Offer the apply artifacts.** Ask whether to generate the Google Ads Editor apply-CSVs
   (via `scripts/make_editor_csv.py`, types above) for the recommendations the user accepts —
   done-with-you, not fire-and-forget. Point at the apply path (Editor import steps above) and
   name the manual-only items the CSVs can't cover.

### The numbers rule

Recommendations **cite model numbers — never narrate raw data**:

- Every figure in a recommendation comes from the emitted artifacts or the builder's printed
  summary (the model), not from memory, not recomputed by hand, not read off raw MCP/CSV rows.
- Tie each recommendation to the model fields that justify it (e.g. "blocks $412.30 of
  never-converted spend across 9 terms — Block 1 of the waste filter"), so the user can find the
  same number in the HTML explorer or xlsx.
- If a number isn't in an artifact or builder output, don't quote it (see SKILL.md's honesty
  rules). A findings JSON without reconciliation totals is UNVERIFIED — say so instead of
  advising from it.

### Recommendation severity taxonomy

| Severity | Meaning | Act when |
|---|---|---|
| **Critical** | Active budget bleed or broken measurement: spend flowing to zero-value targets, conversion tracking wrong/missing, a limit throttling converting traffic. Quantified loss already occurring. | Now — first Editor import / UI session. |
| **High** | Clear, quantified gain ready to capture: converting terms to promote, proven reallocation, structural fix with modeled upside. | This week. |
| **Medium** | Hygiene and incremental optimization: routing informational queries, expansion candidates, watch-list items, near-misses surfaced by the sensitivity read. | Next optimization cycle. |

Rules of use:
- Severity is assigned per recommendation from the **model's** magnitude (spend, conversions,
  score), not vibes; state the number that earned the rating.
- Empty tiers are honest results — a clean account may have **no Critical items**; say so
  rather than inflating a Medium. The "0/0 is clean" posture applies to recommendations too.
- Each recommendation carries: severity · the specific action · the model number(s) behind it ·
  expected effect · the artifact that applies it (or a **manual** callout when no CSV can).

### Campaign liveness (severity is gated on it)

Real accounts carry a long tail of paused, long-dead campaigns — often the majority of rows. A
scoring skill that treats every row as fair game manufactures findings on the dead (a paused
campaign flagged "revert to Manual CPC", a zero-traffic campaign flagged for a "CVR drop", a
paused campaign called "under-budget"). The shared primitive
`_shared/analytics.segment_liveness(rows, status_key=, spend_key=, prior_spend_key=)` tags every
row with a **liveness** band so severity is scored only on what's actually running:

| `liveness` | Definition | Severity universe |
|---|---|---|
| **live** | status `ENABLED` **and** spend > 0 in the current window | Scored normally. |
| **recently_active** | any recent signal that isn't live: `PAUSED`/`REMOVED` but spent mid-window · `ENABLED` but idle (zero current spend) · spend only in the prior window | Scored, but every recommendation is phrased **conditionally** ("paused mid-window after spending X — confirm intent before acting", per skill voice). |
| **dormant** | not `ENABLED` **and** zero spend in both windows | **Present-but-tagged, zero recommendations.** Never dropped (no-row-loss); carries `liveness="dormant"` into the model, xlsx column, and HTML. |

Rules of use:
- **Gate the severity/recommendation universe on `live` + `recently_active`.** Dormant rows are
  scored to zero (not flagged), so they can't manufacture Critical/High findings.
- **`liveness` is data, not a tunable.** It depends on status + spend (fixed pulled facts), so it
  is computed once in Python and mirrored verbatim into the browser kernel and xlsx column — the
  live recompute reads the embedded tag rather than re-deriving it.
- **Honest degradation.** A single-window skill (no prior-window spend) calls
  `segment_liveness` with `prior_spend_key=None`: `live`/`recently_active`/`dormant` are still all
  reachable, but the "spent only in the prior window" path can't fire. Document per skill what's
  derivable — never invent a prior window to fake a third band.
- **Surface it.** Every deliverable shows the `liveness` tag (a column in xlsx, a tag/column in
  the HTML explorer) so the reader can see what was and wasn't in the scoring universe.

### Advisor checklist (per skill)

- [ ] Builder emits the skill's declared bundle from the reconciled findings JSON.
- [ ] HTML explorer presented **first**, as the hero deliverable.
- [ ] Recommendations grouped Critical/High/Medium, every figure traceable to the model.
- [ ] Apply-CSVs **offered** (not auto-dumped) via `make_editor_csv.py`, with the Editor apply
      path; manual-only items named.
- [ ] Data source honest: `meta.source` surfaced; API-blind data labelled user-supplied.
- [ ] Severity universe gated on `liveness` (dormant rows tagged, zero recommendations); the
      `liveness` tag surfaced in xlsx and HTML.
