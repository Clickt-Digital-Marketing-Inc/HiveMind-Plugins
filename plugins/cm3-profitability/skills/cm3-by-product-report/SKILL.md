---
name: cm3-by-product-report
description: Generate a protected CM3 profitability report remotely from a required Google Ads Shopping CSV and optional Shopify Gross profit by product CSV. Use when the user wants product-level contribution-margin metrics and expiring Markdown, HTML, and XLSX artifacts without exposing CSV rows or proprietary compute to the agent.
---

# CM3 by Product — protected remote workflow

Guide the user through the frozen CM3 remote contract. The agent selects files
and assumptions; the protected service performs every parse, calculation,
finding, and render. The only distributed executable used by this workflow is
[`remote_workflow.py`](remote_workflow.py), a stdlib-only metadata, validation,
and direct-upload helper.

Contract: `HiveMind CM3 Protected Compute Remote Contract` version `1.0`, frozen
at `hivemind-compute-mcp@d32ba711b146ea73a801b806e950eeee94549051`.

## Non-negotiable boundary

- Never open, preview, parse, sample, summarize, attach, paste, base64-encode, or
  put either CSV into a prompt, MCP argument, transcript, log, or model output.
- Never call a local CM3 parser, compute module, findings engine, renderer,
  template, workbook builder, chart bundle, or legacy report command. There is
  no local fallback. If the remote service is unavailable, stop with the safe
  guidance in [`references/remote-workflow.md`](references/remote-workflow.md).
- CSV bytes travel only from the local file handle to the presigned HTTPS PUT.
  MCP JSON contains filename, byte size, SHA-256, role, job ID, and assumptions.
- Do not print signed upload URLs, credential values, raw service exceptions,
  object keys, request dumps, filesystem paths, or response files. Artifact
  download URLs may be shown only in the final result and expire after one hour.

Legacy local implementation files remain in this repository temporarily for
the HM-888 cutover. Their presence is not permission to execute or describe
them, and this skill does not reference them as an alternate path.

## 1. Preflight

Confirm both MCP tools are available:

- `cm3_prepare_uploads`
- `cm3_generate_report`

Confirm the MCP client has the service URL and service-issued credential in its
private connection/secret configuration. Never ask the user to paste a key.
See [`references/remote-workflow.md`](references/remote-workflow.md) for the
credential, network, and temporary-file rules.

If either tool is absent or authentication fails, stop. Do not attempt local
generation.

## 2. Locate inputs without reading rows

Look only at filenames and paths in the current workspace.

Required Google Ads Shopping CSV filename candidates:

- `*shopping*products*.csv`
- `*google*ads*.csv`

Optional Shopify Gross profit by product CSV candidates:

- `*gross*profit*product*.csv`
- `*shopify*gross*.csv`

If more than one candidate matches a role, list filenames only and ask the user
which file to use. If the required Google Ads file is missing, say:

> I need your Google Ads Shopping products CSV. Export it from Google Ads →
> Reports → Predefined reports → Shopping → Shopping products, choose the date
> range, download CSV, and provide its local path.

Always offer the optional input:

> Optional: a Shopify “Gross profit by product” CSV supplies product-level gross
> profit data. Export it from Shopify admin → Analytics → Reports → Gross profit
> by product. If omitted, the remote report uses the COGS fallback assumption.

Do not validate inputs by reading headers or rows. The service owns CSV
validation and returns `MALFORMED_CSV` safely when unsupported.

## 3. Gather assumptions

Confirm these values with the user. The public contract examples use the shown
defaults; band thresholds are decimal ratios and must be strictly descending.

| Assumption | Contract key | Default | Allowed |
|---|---|---:|---:|
| Fallback COGS percent | `cogs_pct` | 65 | 0–100 |
| Shipping percent | `ship_pct` | 20 | 0–100 |
| Processing percent | `proc_pct` | 2.9 | 0–100 |
| Fixed costs | `fixed_costs` | 0 | 0 or greater |
| Excellent lower threshold | `band_exc` | 0.10 | -10–10 |
| High lower threshold | `band_high` | 0.05 | -10–10 |
| Average lower threshold | `band_avg` | 0 | -10–10 |
| Low lower threshold | `band_low` | -0.25 | -10–10 |

Optionally collect a human-readable `period` of at most 128 characters. Do not
infer a period by opening the CSV.

## 4. Derive metadata locally

Run the helper from this skill directory. It reads files in binary chunks only
to derive byte size and SHA-256; its stdout is contract-safe metadata JSON.

```bash
python3 remote_workflow.py metadata \
  --google-ads "/absolute/path/google-ads-shopping.csv" \
  --shopify "/absolute/path/shopify-gross-profit.csv"
```

Omit `--shopify` when absent. Do not print the input paths in the user-facing
reply. Each file must be a non-empty, safely named `.csv` no larger than 25 MiB.

Report safe progress only: “Validated local metadata for the required Google
Ads file” and, when applicable, “and the optional Shopify file.” Do not report
row counts or file contents.

## 5. Prepare, check version, then upload

Call `cm3_prepare_uploads` with the exact metadata JSON from step 4. Do not add
path, content, rows, headers, snippets, bytes, or base64 fields.

Before any PUT, require `contract_version == "1.0"`. Save the exact successful
tool response mechanically to a mode-0600 temporary JSON file without printing
it. Then run:

```bash
python3 remote_workflow.py upload \
  --google-ads "/absolute/path/google-ads-shopping.csv" \
  --shopify "/absolute/path/shopify-gross-profit.csv" \
  --prepare-response "/private/temp/cm3-prepare-response.json"
```

Omit `--shopify` when absent. The helper rejects version mismatch, role drift,
filename drift, and expired 15-minute sessions before opening an upload. It
streams each file as the raw PUT body and propagates every returned required
header exactly. It never prints a signed URL or body.

After both required uploads complete, report only: “Uploads completed; report
generation is starting.” Do not reuse a job or upload session after a mismatch,
expiry, or failed PUT.

## 6. Generate remotely

Call `cm3_generate_report` with exactly:

```json
{
  "contract_version": "1.0",
  "job_id": "<job_id from prepare>",
  "cogs_pct": 65,
  "ship_pct": 20,
  "proc_pct": 2.9,
  "fixed_costs": 0,
  "band_exc": 0.1,
  "band_high": 0.05,
  "band_avg": 0,
  "band_low": -0.25,
  "period": "<optional user-confirmed period>"
}
```

Replace defaults with the confirmed assumptions and omit `period` when absent.
No other field is allowed. Never retry the same job with changed assumptions;
start again at prepare.

## 7. Present the safe result

Require response `contract_version == "1.0"`, exactly three artifacts in this
order (Markdown, HTML, XLSX), `expiry_seconds == 3600` for each, and future
`expires_at` timestamps. If any artifact is already expired or malformed, show
no links and use the artifact-expiry guidance.

Present only:

- currency, product count, revenue, ad spend, CM3, CM3 percent, ROAS,
  excellent-product count, and poor-product count;
- artifact filename, download link, and expiry for Markdown, HTML, and XLSX;
- “Download promptly; links expire one hour after generation. Do not paste
  signed links into support tickets or logs.”

Do not claim the service changed Google Ads or Shopify. Do not describe hidden
formulas, findings logic, templates, or rendering implementation.

## Errors

Ignore server-provided prose and translate only stable public error codes into
the static, redacted action in
[`references/remote-workflow.md`](references/remote-workflow.md). A safe request
ID may be shared with support; credentials, signed URLs, request dumps, paths,
CSV data, object identifiers, and stack traces may not.

For any unknown code or malformed response, stop with a generic contract error.
There is no local fallback.
