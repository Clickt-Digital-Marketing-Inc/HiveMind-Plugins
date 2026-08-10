# CM3 remote connection and safe recovery

This reference applies only to CM3 protected-compute contract `1.0`, frozen at
`hivemind-compute-mcp@d32ba711b146ea73a801b806e950eeee94549051`.

## Connection and credential configuration

Configure the deployment-provided CM3 MCP server URL and service-issued bearer
credential in the MCP client's private connection/secret store. Deployment
operators may choose different environment-variable names; this plugin does not
invent, require, or read a credential variable of its own. Follow the deployed
server registration exactly.

- Never commit credentials or signed URLs to this repository, a dotfile, a
  fixture, a command argument, a prompt, or a transcript.
- Never ask a user to paste a credential into chat. A missing, revoked, or
  expired credential must be replaced through the service administrator.
- The client needs outbound access to the MCP endpoint and to the HTTPS hosts in
  the returned presigned PUT and artifact URLs. Do not bypass TLS verification.
- No Python package install is needed for the thin helper; it uses the standard
  library only.
- Store prepare/generate responses only when mechanical handoff requires it.
  Use a private mode-0600 temporary file, never print it, and remove it after the
  upload or presentation. These response files contain signed URLs but never CSV
  bytes.

The service returns `contract_version` in every success and public error. Stop
before upload when it is not exactly `1.0`.

## Safe progress language

Allowed progress messages describe stages, not business data:

1. “Validated local metadata for the required Google Ads file” (and optionally
   “and the optional Shopify file”).
2. “Upload session prepared; direct uploads are starting.”
3. “Uploads completed; report generation is starting.”
4. “Report generated; the links below expire one hour after generation.”

Never mention CSV rows, headers, snippets, file contents, absolute paths,
signed upload URLs, object keys, credentials, or request dumps.

## Stable error guidance

Use the stable code, not remote error prose. A public request ID matching
`req_[A-Za-z0-9_-]{20,64}` is the only diagnostic identifier safe to share.

| Code / class | Safe action |
|---|---|
| `AUTH_MISSING` | Configure the service-issued credential in the MCP client's private secret store, then reconnect. |
| `AUTH_INVALID` | Replace it with a valid service-issued credential; never paste the old or new value into chat or logs. |
| `AUTH_REVOKED` | Ask the service administrator for a replacement credential, update the private secret store, and reconnect. |
| `AUTH_EXPIRED` | Rotate the credential through the service administrator, update the private secret store, and reconnect. |
| `SCOPE_DENIED` | Ask the administrator to grant CM3 prepare-and-generate scope. |
| Network / MCP unavailable | Check MCP connectivity and outbound HTTPS access. Do not reveal credentials, signed URLs, or raw exceptions. Do not fall back locally. |
| Direct PUT failure | Check outbound HTTPS access and begin a new job; do not reuse a possibly partial upload session. |
| `UPLOAD_URL_INVALID` | Do not upload. Start a new job; if repeated, share only the safe request ID because the response-derived HTTPS URL was rejected locally. |
| `UPLOAD_HEADERS_INVALID` | Do not upload. Start a new job; if repeated, share only the safe request ID because response-derived headers were rejected locally. |
| `UPLOAD_SESSION_EXPIRED` | Start again at prepare. The 15-minute session, URLs, and job ID are not reusable. |
| `FILE_SIZE_LIMIT_EXCEEDED` | Each CSV must be at most 25 MiB. Export a narrower period or reduce it outside the model, then retry. |
| `FILE_SIZE_MISMATCH` | The local file changed after metadata preparation. Start a new job from the current file. |
| `FILE_HASH_MISMATCH` | The file changed or transfer was corrupted. Start a new job and upload the original local file again. |
| `UPLOAD_INCOMPLETE` | Complete every returned PUT, or start a new job when any URL has expired. |
| `TENANT_MISMATCH` | Reconnect with the intended partner credential and start a new job. |
| `JOB_REPLAYED` | Start a new prepare/upload/generate sequence; do not change assumptions on an existing job. |
| `INVALID_REQUEST` | Update the plugin or correct selected file metadata, then start a new job. |
| `INVALID_ASSUMPTIONS` | Correct percentage ranges, non-negative fixed costs, and strictly descending band thresholds. |
| `MALFORMED_CSV` | Export a fresh supported Google Ads Shopping CSV and optional Shopify Gross profit by product CSV. Do not inspect rows in the model. |
| `EXECUTION_TIMEOUT` | Start a new job. If repeated, give support only the safe request ID. |
| `QUOTA_EXCEEDED` | Wait for the rolling completed-job quota window to reopen, then start a new job. |
| `CONCURRENCY_LIMIT` | Wait for the active job to finish, then start a new job. |
| `INTERNAL_ERROR` | Retry with a new job. If repeated, give support only the safe request ID. |
| `ARTIFACT_EXPIRED` | Generate a new report; an expired one-hour link cannot be refreshed. |
| `ARTIFACT_INTEGRITY_FAILED` | Do not use the artifact. Generate again and share only the safe request ID if repeated. |
| Contract version mismatch | Stop before upload and align the plugin and service on contract `1.0`. |
| `REMOTE_ERROR_INVALID` (unknown code / malformed error) | Stop with the fixed local generic error and share only the safe request ID. Never repeat the server-controlled code or message. |

No recovery path invokes the retained local CM3 implementation.
