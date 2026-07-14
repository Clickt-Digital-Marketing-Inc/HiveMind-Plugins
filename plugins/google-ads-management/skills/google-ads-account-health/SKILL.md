---
name: google-ads-account-health
description: Use when auditing a Google Ads account's structural health, running a monthly account sweep, or checking the "5 red flags" (ad-group keyword sprawl, missing campaign negatives, naming inconsistency, automation without conversion data, PMax brand cannibalization). Pulls live data via the Google Ads MCP (or a user-supplied CSV export) and outputs a prioritized remediation plan with ready-to-apply artifacts.
---

# Google Ads — Account Health & Structure

Diagnose the structural foundation before optimizing anything else. Fixing the five red flags
typically recovers 20–35% of wasted budget and is the prerequisite for AI/automation to work.

**Cadence:** monthly (or before scaling spend / enabling automation).

**REQUIRED BACKGROUND:** load `google-ads-foundation` first (account selection, metadata-first
queries, conventions, the advisor + dual-input output contract in
[references/artifact-formats.md](../google-ads-foundation/references/artifact-formats.md)).

## When to use
- "Audit my account", "is my account set up right", "why is budget being wasted".
- Before increasing budget or enabling automation.
- Onboarding a new account.

## Step 0 — select the input path

Before pulling anything, decide MCP vs. CSV (see `google-ads-foundation`'s Step 0 detect/ask
rule): MCP reachable → pull live; MCP unreachable or the user prefers an export → ask for the two
CSVs named below. Never guess when both are plausible — ask.

## Pull the data (MCP path)

Four GAQL pulls (exact fields/conditions in
[references/account-health-filter.md](references/account-health-filter.md)):
1. **Enabled keywords per ad group** (`ad_group_criterion`, type=KEYWORD, negative=false, enabled)
   — for the sprawl count.
2. **Ad-group performance, 30d** (`ad_group`, clicks + impressions) — for sprawl's CTR bar.
3. **Campaign structure + bidding + conversions, 30d** (`campaign`) — status, channel type,
   bidding strategy, conversions.
4. **Campaign-level negatives** (`campaign_criterion`, type=KEYWORD, negative=true) — for the
   `no_negatives` count.

Save every raw result to a file (transcription firewall), then:
```
python3 scripts/assemble_findings.py --keywords <raw-1> --adgroup-perf <raw-2> \
  --campaigns <raw-3> --negatives <raw-4> --client-name "{Client}" --account-id {account} \
  --currency {CUR} --window-30d "<start> to <yesterday>" -o findings.json
```

## Pull the data (CSV path)

Ask for two Google Ads UI exports (report name, columns, and the two **hand-added** count
columns are documented in
[references/account-health-filter.md](references/account-health-filter.md#dual-input--the-csv-path-_sharedcsv_inputpy)):
**Ad groups** report (+ `Ad group keywords (enabled)`) and **Campaigns** report (+
`Campaign negative keywords`). Then:
```
python3 scripts/assemble_from_csv.py --adgroups-csv "Ad groups.csv" \
  --campaigns-csv "Campaigns.csv" --client-name "{Client}" --account-id {account} \
  --currency {CUR} --window-30d "<start> to <yesterday>" -o findings.json
```

## The five checks

| Check | Grain | Flag when | Status |
|---|---|---|---|
| Ad-group sprawl | ad_group | ≥ 20 keywords AND ad-group CTR (30d) < 3% | `scored` |
| No campaign negatives | campaign (Search) | 0 campaign-level negatives | `scored` |
| Automation without data | campaign | automated bidding AND 30d conversions < 30 | `scored` |
| Naming inconsistency | campaign | name fails the naming regex | `config` (unconfirmed default) |
| PMax brand cannibalization | campaign (PMax) | brand Search campaign coexists | `manual` (exclusion confirmation is not API-readable) |

Full rule/weight table and the naming regex: `references/account-health-filter.md`. Every entity
gets one row per applicable check, ranked by `pre_score` — nothing is dropped.

## Build the bundle + run the advisor loop

```
python3 scripts/build_health_report.py --input findings.json --outdir artifacts \
  --brand "{Client}" --formats md,xlsx
```
**Reduced bundle by design — no HTML explorer.** Five heterogeneous checks across two entity
grains read poorly as one wide interactive table; the tunable **xlsx `Controls` tab** (4 numeric
thresholds) is this skill's interactive surface. See
[references/account-health-filter.md](references/account-health-filter.md#emitted-formats-for-m31--hm-547)
for the full "why."

Then follow the standard **advisor loop** (`google-ads-foundation`'s output contract): open with
the richest declared format (the `*.md` report — no HTML hero here), present the "top structural
fixes" section grouped Critical → High → Medium (every figure cited from the model, never
recomputed), then offer the apply artifacts.

## Generate artifacts (in `artifacts/`)

- `*_action_plan.md` — every flagged entity, ordered Critical → High → Medium, each line naming
  the artifact that applies it or **manual**.
- `*_renaming.md` — campaigns failing the naming check: old name → **confirm with the user**
  (never auto-invents a new name).
- `*_pause_list.csv` (Editor-importable) — ad groups flagged for sprawl, to segment.
- `*_report.md` / `*.xlsx` — the bundle above.

**No `negative_keywords.csv`** — see the "why" link above: this skill has no term-level data to
populate one honestly; hand that check to `google-ads-keywords-search-terms`.

## Common mistakes / red flags
- Don't flag a 20-keyword ad group if its CTR is healthy — sprawl is keyword count **and** weak CTR.
- Don't count negatives or paused keywords in the sprawl count (the pull already filters
  `negative = false`, `status = ENABLED`).
- Naming regex and the brand-name heuristic are starting templates — confirm with the user before
  flagging or renaming.
- PMax cannibalization's brand-exclusion field is **always** unconfirmed from the API — never
  imply the MCP verified it; the row's `status` is always `manual`.
- Ad-group segmentation and renaming are **manual** (read-only MCP); deliver the plan + CSVs.
