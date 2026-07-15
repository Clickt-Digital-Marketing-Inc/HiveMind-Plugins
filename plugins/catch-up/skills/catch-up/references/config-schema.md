# Configuration and state files

The plugin stores everything in the folder `~/.catch-up/`.

## config.json

Written by the `catch-up-setup` skill. Read by every run.

```json
{
  "version": 1,
  "call_tool": "granola",
  "email_tool": "gmail",
  "email_inbox": "you@example.com",
  "project_tool": "linear",
  "project_target": {
    "team": "",
    "project": "",
    "list": "",
    "default_assignee": ""
  },
  "first_run_lookback_days": 7,
  "issue_mode": "review",
  "draft_mode": "both",
  "timezone": "America/Toronto"
}
```

Field notes:

- `call_tool`, `email_tool`, `project_tool` — a short lowercase name of the
  chosen provider in each category. Free-form so any tool can be named. Examples:
  `granola`, `teams`, `google-meet`, `zoom`, `otter`, `fireflies`; `gmail`,
  `outlook`; `linear`, `clickup`, `asana`, `jira`, `monday`, `notion`.
- `email_inbox` — the address to scan.
- `project_target` — where new issues go inside the tracker. Fill whichever
  fields the tracker uses (Linear: team + project; ClickUp: list; Asana:
  project). Leave the rest blank. `default_assignee` is optional.
- `first_run_lookback_days` — how far back the first run reaches when there is no
  saved `last_run`. Default 7.
- `issue_mode` — `review`, `auto`, or `ask`.
- `draft_mode` — `both`, `replies`, `followups`, or `off`.
- `timezone` — used to describe windows to the user; default to the user's
  timezone.

## state.json

Written at the end of each run. Do not create it during setup.

```json
{
  "last_run": "2026-07-12T14:03:00Z",
  "last_run_summary": "3 calls, 11 emails -> 6 issues, 2 drafts"
}
```

- `last_run` — ISO 8601 timestamp of the last successful run. Its absence means
  the next run is a first run and uses `first_run_lookback_days`.
- Update `last_run` only after issues and drafts are handled, never before.
