# Linear Issue Template

One Linear issue per post, created with `Linear:save_issue`. Create only — never modify existing issues.

## Title convention

`[<Platform>] <Format> — <Topic, 8 words max> — <YYYY-MM-DD>`

Examples:
- `[LinkedIn] Text post — Chatbots failing small business support — 2026-07-08`
- `[Instagram] Reel — Bakery ditched its chatbot — 2026-07-10`

## Description template

Fill every placeholder. The two prompts go in fenced blocks so they can be copied whole into a future agent session.

````markdown
## Scheduling
- Platform: {platform}
- Format: {format}
- Publish date: {YYYY-MM-DD} ({Weekday})
- Cadence slot: {n} of {total} ({pattern, e.g. Mon/Wed/Fri over 2 weeks})
- Batch: {run date}

## Source idea
- {URL} — {one-line summary of the trending discussion}

## Writing prompt
```text
{full writing prompt}
```

## Media prompt
```text
{full media prompt}
```

## Quality check
Passed prompt quality checklist on {run date}.
````

## save_issue field mapping

| Field | Value |
|---|---|
| `title` | per the title convention above |
| `description` | per the template above |
| `team` | the team the user picked in Phase 5 |
| `project` | the project the user picked (omit if they chose "no project") |
| `dueDate` | the publish date |
| labels | apply a `social-post` label ONLY if it already exists in the team (`Linear:list_issue_labels`); never create labels |

After each `Linear:save_issue`, record the returned issue identifier/URL for the Phase 6 summary table.
