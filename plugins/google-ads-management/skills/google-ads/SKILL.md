---
name: google-ads
description: Use when the user wants to start, browse, or choose among Google Ads tasks without naming a specific one — e.g. "manage Google Ads", "Google Ads menu", "open the Google Ads menu", "what Google Ads tools do I have", "help with my Google Ads account", or "where do I start with Google Ads". Presents an interactive in-Claude menu of every Google Ads skill (management, audit, CM3 profitability), captures the task's inputs, and routes to the chosen skill. When the user already names a specific task (budget pacing, quality score, audit, PMax, CM3, etc.), use that task's own skill directly instead of this hub.
---

# Google Ads — task hub

The single entry point for the Google Ads skill suite. It renders an interactive menu inside
Claude, collects what the chosen task needs (account or input files, date window, output formats,
context), and routes to the right skill. It runs nothing itself and queries nothing beyond listing
accounts — each task skill does its own work.

**This is a router, not a worker.** Never diagnose, never build artifacts here. Present the menu,
then let the routed prompt trigger the task skill.

## When to use vs. not
- **Use** for "manage Google Ads", "Google Ads menu / hub", "open the Google Ads menu", "what can
  you do with Google Ads", or any time the user wants to pick from the suite.
- **Don't use** when the user names a concrete task ("check budget pacing", "run the audit", "PMax
  winners and losers", "CM3 report"). Defer to that task's skill — its description will match.
- **Don't shadow** `google-ads-foundation` (the shared prerequisite that task skills load).

## The 14 tasks (source of truth: [references/catalog.json](references/catalog.json))
The catalog is authoritative — read it, don't hardcode the list here. Groups: **Management** (12
skills), **Audit** (full account audit), **Profitability** (CM3 by product). Each entry carries its `skill` name, `plugin`, input shape (`mcp` = account +
date window; `csv` = file paths), available `formats`, and a route template. Cross-plugin tasks
(audit, cm3-by-product) only run if that plugin is installed; if a routed task
has no matching skill, say so rather than improvising.

## Flow

### Step 1 — Prepare the menu
1. Call `mcp__visualize__read_me({modules:['interactive']})` once before the first `show_widget`.
2. **List accounts** (so the menu's account picker is pre-filled) using the exact workflow in
   `google-ads-foundation` SKILL.md **Step 1**: `customers_list_accessible_customers`, then query the
   `customer` resource for `id, descriptive_name, currency_code, manager`. **Skip manager accounts.**
   Build a JSON array: `[{"id":"1234567890","name":"Acme","currency":"USD"}, …]`.
   - If the MCP errors or returns nothing (e.g. the `login-customer-id` issue described in
     foundation), use an **empty array** `[]` — the menu falls back to a free-text account field —
     and mention the fix (set the MCP server's `login-customer-id` to the manager ID).

### Step 2 — Render the menu
Read [references/menu.html](references/menu.html) and replace the three placeholders, then pass the
result to `mcp__visualize__show_widget` (title: `google_ads_menu`):
- `__CATALOG__` → the full contents of `references/catalog.json`.
- `__ACCOUNTS__` → the accounts JSON array from Step 1 (or `[]`).
- `__PRESELECT__` → `""` normally; when the user said "re-open the menu for the X task", put that
  task's `id` (from the catalog) so the menu opens on it.

Keep your own response text short (one line, e.g. "Pick a task below"). All UI lives in the widget.

### Step 3 — The user picks and runs
The widget's **Run** button calls `sendPrompt(...)` with a fully-formed instruction (skill name,
account or files, window, formats, context, plus a trailing instruction to render the results card).
That arrives as a normal user turn and triggers the chosen task skill by its description. You don't
need to do anything between Step 2 and that turn.

### Step 4 — Run the task and show results
When the routed prompt fires, run the task's **analysis** (management skills load
`google-ads-foundation` first) and **keep the findings JSON** — you reuse it for every output. Outputs
are produced on demand from the results surface, not pre-built, so don't write files except where a
mode says to. Show the surface by **three modes** (from the catalog entry):

**CSV-or-MCP input (advisory skills).** The five advisory skills — bidding-strategy, competitive-analysis,
conversions-tracking, account-health, audience-targeting — are dual-input: they analyze either a **live MCP
account** (the menu default, `routeTemplates.mcp`) or an **operator-supplied CSV export**
(`routeTemplates.csv`). If the operator pasted a CSV/report path in context, take the skill's CSV path;
otherwise use MCP. Either way the **advisor routing is the same**: analyze only → show the results surface
(the tuner for the three tunable advisors, the export card for the two reduced-bundle ones) → lead with the
hero report and recommendations grounded in the model numbers → export the deliverables on demand at Step 5.

**A. Tunable skill** (`tunable: true`) — render the **in-Claude tuner**; build no files yet.
- **Bundle skills** (the 10 google-ads-management tuners) emit a widget JSON, then assemble it:
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/build_<prefix>_report.py" \
      --input <findings>.json --formats "" --brand "{brand}" --emit-widget <tmp>/widget.json
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/google-ads/references/build_widget.py" \
      --data <tmp>/widget.json --out <tmp>/widget.html
  ```
- **cm3-by-product** is bespoke (its explorer is `cm3_html.py`, not `_shared`): its builder emits the
  **assembled fragment directly** — no `build_widget.py` step:
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/../cm3-profitability/skills/cm3-by-product-report/cm3_by_product.py" \
      --csv <shopping.csv> [--cogs-csv <shopify.csv>] --brand "{brand}" --emit-widget <tmp>/widget.html
  ```
Read `<tmp>/widget.html` → `show_widget` (title `google_ads_results`). Its **Outputs** row (Save to
HiveMind / Export Excel / Download HTML / Export PowerPoint) routes to Step 5 at the tuned params.

**B. Up-front skill** (`formats_upfront: true` — the audit): the route prompt already named the
formats, so **build them now** via the skill's own builder (the audit →
`${CLAUDE_PLUGIN_ROOT}/../google-ads-audit/skills/google-ads-audit/scripts/generate_workbook.py --input <findings> --output <path>.xlsx`) into `artifacts/`, and render
[results-card.html](references/results-card.html) with `__CARD__` =
`{"title","scope","summary","taskLabel","artifacts":[{"label","fmt","path"}]}` listing the built
files (omit `exports`).

**C. Export-from-results skill** (every other non-tunable — the advisory skills):
build **no files yet**; render the card with `__CARD__` =
`{"title","scope","summary","taskLabel","skill","filename_stem","exports":[<the task's formats>]}`
(omit `artifacts`). Each format becomes a button that routes to Step 5.

Keep your reply short; whenever you actually build a file (mode B, or any Step-5 export) list its path
as a markdown link — widgets can't open local files. The card's `Explain` / `Adjust` / `Run another`
buttons are follow-ups (re-render the menu for adjust/another, `__PRESELECT__` set for adjust).

### Step 5 — Outputs (results-surface actions)
The tuner's **Outputs** buttons and the card's export buttons each fire a `sendPrompt`. Every action
rebuilds **one** format from the run's kept inputs at the supplied params — never re-pull the API. Use
the **right builder for the skill** — the CLIs differ by family, so don't assume a single form:
- **Tunable bundle skills** (quality-score, budget-pacing, keywords-search-terms, performance-reporting,
  pmax-campaigns, pmax-listing-groups, products, bidding-strategy, competitive-analysis, conversions-tracking):
  `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/build_<prefix>_report.py
  --input <findings>.json --outdir artifacts --brand "{brand}" --formats <md|html|xlsx>`. For a tuner Save,
  first set the findings' `params` block to the tuned values from the prompt (the md provenance then records
  them, so it matches the tuner).
- **cm3-by-product** (tunable; own builder): rebuild via
  `${CLAUDE_PLUGIN_ROOT}/../cm3-profitability/skills/cm3-by-product-report/cm3_by_product.py --csv <shopping.csv>
  [--cogs-csv <shopify.csv>]` plus the tuned params the Outputs button passed
  (`--cogs-pct --ship-pct --proc-pct --fixed-costs --band-exc --band-high --band-avg --band-low`) and
  exactly one `--output-md|--output-html|--output-xlsx|--output-pptx <path>`. A tuner **Save** uses
  `--output-md` into the vault `raw/reports/`; the tuned cutoffs + cost assumptions are recorded in the
  md frontmatter (and the xlsx methodology), so the saved report matches the tuner. Exports → `artifacts/`.
- **audit**: invoke that skill's **own** builder per its SKILL.md — bespoke single-output
  flags, **not** `--input/--formats`:
  `${CLAUDE_PLUGIN_ROOT}/../google-ads-audit/skills/google-ads-audit/scripts/generate_workbook.py --input <findings> --output <path>.xlsx`.
  It rebuilds from its original inputs (findings).
- **Reduced-bundle advisory skills** (account-health, audience-targeting — md+xlsx, no html/tuner):
  rebuild via `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/build_<prefix>_report.py --input <findings>.json
  --outdir artifacts --brand "{brand}" --formats <md|xlsx>` (same interface as the tunable bundle skills,
  minus html). Their skill-specific side files (action plan, renaming, pause list, worklists) are written by
  the skill's own artifact step, not re-exported here.

**Save to HiveMind** (md → vault): build the md per the above, then
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/google-ads/references/resolve_vault.py"`
(`$HIVEMIND_VAULT` → app `config.json` `vaultPath`; ask the operator if it exits non-zero),
`mkdir -p "<vault>/raw/reports"`, and write `<vault>/raw/reports/<filename_stem>.md` —
**overwrite = supersede** (one source per account+report+date). **Never call `propose_note`.** Confirm
the path; optionally verify it indexed via the HiveMind MCP (`find_pages` / `search`).

**Export Excel / Download HTML / Export PowerPoint / Export CSVs** (→ `artifacts/`): build the one
requested format per the above and reply with the clickable path.

`raw/reports/` is scanned by `hivemind-catalog`; a re-save overwrites and re-catalogs the same source.

## Fallback — no widget tool available
If `mcp__visualize__read_me` / `show_widget` aren't available, don't fail — degrade gracefully:
1. Use `AskUserQuestion` to ask which area (Management / Audit / Profitability).
2. List that area's tasks (from the catalog) and let the user name one.
3. Capture the inputs conversationally (account + window, or file paths; then formats + context).
4. Run the task skill, then present results as a short text summary plus the markdown artifact links
   (no card).

## Notes
- **Read-only.** Account changes are never made through the MCP; task skills emit apply-files
  (Editor CSVs / change tables) the user applies manually.
- **Don't duplicate** account-selection, micros, or date logic — it lives in `google-ads-foundation`.
- Keep the catalog in sync with the installed skills; [tests/test_catalog.py](tests/test_catalog.py)
  guards against drift.
