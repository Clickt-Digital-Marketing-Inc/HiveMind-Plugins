---
name: google-ads-foundation
description: Use when running any google-ads-* management skill or querying a Google Ads account through the Google Ads MCP. Provides the shared account-selection workflow, the mandatory metadata-first GAQL query method, money/date/dedup conventions, and the standard Diagnose -> Recommend -> Artifacts output contract that every focus-area skill depends on.
---

# Google Ads Foundation

Shared groundwork for the `google-ads-*` skill suite. Load this before any focus-area skill so
queries are accurate, the right account is selected, and output is consistent.

**Core principle:** the Google Ads MCP is **read-only**. Pull live data and diagnose it, but the
only way to change the account is the **artifact** a skill generates (a Google Ads Editor CSV or a
change table the user applies). Never claim a change was made through the MCP.

## The three MCP tools (the only ones that exist)

| Tool | Use |
|---|---|
| `mcp__google-ads-mcp__customers_list_accessible_customers` | List customer IDs the auth user can reach. Call first. |
| `mcp__google-ads-mcp__metadata_get_resource_metadata` | Return selectable/filterable/sortable fields + compatible metrics/segments for one resource. Call **before building any query**. |
| `mcp__google-ads-mcp__search_search` | Run the query. Args: `customer_id`, `resource`, `fields` (list), `conditions` (list, AND-ed), `orderings` (list), `limit`. |

There are **no** create/update/pause/budget tools. Do not look for them.

## Step 1 — Select the account (always do this first)

1. Call `customers_list_accessible_customers`.
2. For each returned ID, query the `customer` resource for
   `customer.id, customer.descriptive_name, customer.manager, customer.currency_code, customer.time_zone`
   (authoritative constant: `CUSTOMER_FIELDS` in [scripts/account_fields.py](scripts/account_fields.py)).
3. **Skip manager accounts** (`customer.manager = true`) — they hold no campaign metrics. Query
   child (client) accounts directly by their `customer_id`.
4. If more than one client account is reachable and the user has not named one, **ask which
   account** before pulling data. Record the chosen `customer_id`, `currency_code`, and
   `time_zone` — every later query and every money conversion depends on them.

IDs are plain digit strings (no dashes). Pass them to `search_search` as `customer_id`.

### Account access reality (read this)
The accessible-customers list mixes the manager account, directly-queryable client accounts, and
client accounts that **error on a direct query**. If a query returns
`User doesn't have permission to access customer ... the manager's customer id must be set in the
'login-customer-id' header`, that account is only reachable **through its manager (MCC)**, and the
MCP server isn't sending a `login-customer-id`. `search_search` has **no** per-call parameter for
this — it is server configuration. Tell the user to set the MCP server's `login-customer-id` (env,
e.g. `GOOGLE_ADS_LOGIN_CUSTOMER_ID`) to the manager account ID, then retry. Pick a directly
queryable client account when possible; never fabricate data for an account that errors.

## Step 2 — Build queries the safe way (metadata-first)

The MCP requires it and field names differ from the UI. For every new resource:

1. Call `metadata_get_resource_metadata(resource_name)`.
2. Choose only fields that appear in `selectable`; filter only on `filterable`; sort only on
   `sortable`. **Never guess a field name.**
3. Call `search_search` with `resource`, `fields`, `conditions`, `orderings`, `limit`.

Ready-built queries for the resources this suite uses are in
[references/gaql-cookbook.md](references/gaql-cookbook.md) — copy from there, then verify with
metadata if anything errors.

## Conventions (apply to every skill)

- **Money is micros.** All `*_micros` fields are millionths of the account currency. Convert with
  `value / 1_000_000`. **Trap:** `metrics.average_cpc`, `metrics.average_cpm`, and
  `metrics.average_cost` are ALSO in micros despite not ending in `_micros` — divide them by 1e6
  too. Report in the account's `currency_code`, never assume USD.
- **Dates** use `segments.date`. Prefer presets in a condition string:
  `segments.date DURING LAST_30_DAYS` (also `LAST_7_DAYS`, `LAST_14_DAYS`, `TODAY`, `YESTERDAY`,
  `THIS_MONTH`, `LAST_MONTH`), or `segments.date BETWEEN '2026-05-01' AND '2026-05-31'`.
  A query that selects any `metrics.*` field **must** have a date condition or it returns
  lifetime/over-broad data.
- **Scope to live entities.** Add `campaign.status = 'ENABLED'` (and `ad_group.status = 'ENABLED'`
  where relevant) unless the check is specifically about paused/removed objects.
- **Deduplicate keywords** by `(ad_group_id, keyword.text, keyword.match_type)` before counting or
  flagging — the same text can exist in multiple ad groups legitimately.
- **Only flag wasted spend** when cost (`cost_micros/1e6`) is meaningful (default ≥ the account's
  ~target CPC × 10, or ≥ $10 if unknown) AND `metrics.conversions = 0`. Don't flag noise.
- **Respect statistical reality.** Don't act on < 1 week of data or < ~30 conversions for any
  automation/bidding judgement (see [benchmarks](references/benchmarks-2026.md)).
- **Transcription firewall — numbers never pass through the model.** When a skill builds a
  findings JSON for its analytical bundle, every `search_search` result must land in a file
  first: big results auto-save to `tool-results/*.txt` (use that file as-is); inline results are
  copied **verbatim** — the complete `{"result": [...]}` JSON, unedited — into a file. The
  skill's `assemble_findings.py` (never the model) parses those files into the findings JSON and
  embeds `meta.reconciliation` control totals, which the skill's core re-verifies on every build.
  Hand-typing or editing metric values into a findings JSON is prohibited — it will hard-fail
  reconciliation, and a findings JSON without reconciliation totals is flagged UNVERIFIED by the
  builders. The parsers live in `_shared/gaql_raw.py` + `_shared/reconcile.py`; the CSV twin is
  `_shared/csv_input.py`.
- **Dual input (MCP or CSV).** Every bundle/advisory skill accepts its data from the MCP **or** a
  user-supplied Google Ads UI export, through the same firewall + reconciliation, yielding an
  identical model (honest `meta.source` label). Run the input-selection **Step 0** before any
  pull — see the ["Dual input (MCP or CSV)" section of
  references/artifact-formats.md](references/artifact-formats.md#dual-input-mcp-or-csv) for the
  detect/ask step, the `_shared/csv_input.py` API, and the per-skill `column_map` convention.

## Standard output contract (every focus-area skill returns this)

1. **Diagnosis** — what the live data shows vs. the threshold, with the numbers. State the date
   range and account queried.
2. **Prioritized recommendations** — grouped Critical → High → Medium, each with the specific
   action and expected effect. Plain recommendations, since the MCP cannot apply them.
3. **Artifacts** — the ready-to-apply file(s): Google Ads Editor CSV(s) and/or a markdown change
   table, written to an `artifacts/` folder in the working directory. Formats and the generator
   are in [references/artifact-formats.md](references/artifact-formats.md) and
   [scripts/make_editor_csv.py](scripts/make_editor_csv.py).
4. **Manual-only callouts** — name anything the MCP can't see or do (Auction Insights competitor
   names, landing-page Core Web Vitals, Search Console, and *all* account changes) so the user
   knows to handle it in the UI/Editor.

For every **bundle/advisory skill** (any skill that emits the analytical md/html/xlsx bundle),
this contract is delivered through the **advisor loop** — emit the bundle, open with the hero
HTML report, present Critical/High/Medium recommendations that cite the model's numbers, then
offer the Editor apply-CSVs — as specified in the ["Advisor output contract" section of
references/artifact-formats.md](references/artifact-formats.md#advisor-output-contract). That
section and the ["Dual input (MCP or CSV)"
section](references/artifact-formats.md#dual-input-mcp-or-csv) are the standard every such skill
follows; each ends in a per-skill checklist a skill author implements as written.

## Honesty rules

- Never invent metrics, field names, or competitor data.
- If a query returns no rows, say so and check the date range / status filters before concluding.
- If a framework step needs data the MCP doesn't expose, mark it **manual** and explain where to
  get it — don't fabricate or silently skip it.
- **Numbers quoted in chat come from the artifacts.** When summarizing a run in conversation,
  read the figures from the generated report (the md's provenance + Headline sections or the
  builder's printed summary) — never restate them from memory or recompute them by hand. If a
  number isn't in an artifact or a builder's output, don't quote it. The deterministic artifacts
  are the source of truth; the chat text is commentary on them.
