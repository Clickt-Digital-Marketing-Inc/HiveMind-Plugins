---
name: setup
description: Use when installing or reconfiguring the Morning Briefing plugin - first-time setup, "set up my morning briefing", changing which email account or calendar it uses, or changing how the briefing is delivered (Slack DM, local file). Detects connected Gmail, Calendar, Slack, and Linear MCPs, walks the user through the choices, and writes ~/.morning-briefing/config.json which the morning-briefing skill reads on every run.
---

# Morning Briefing — Setup

## Overview

Interactive configuration for the morning-briefing skill. Detect what's connected, ask the user three decisions (email account, calendar, delivery method), and persist them to `~/.morning-briefing/config.json`. Re-running setup overwrites the config — it is safe to run any time preferences change.

## Critical Guardrails

- **Ask, don't guess.** Each decision below belongs to the user. Present what was detected and let them choose; never silently pick when there are multiple options.
- **Read-only discovery.** Setup only reads (list calendars, detect tools). The only writes are the config file and, if the user opts in, one test message to the delivery target they chose.
- Never store credentials or tokens in the config — only identifiers (email address, calendar ID, delivery choice).

## Workflow

### Step 1: Detect connected sources

Use ToolSearch to check availability of: Gmail tools (search threads, create draft), Calendar tools (list calendars, list events, create event), Slack tools (send message), and Linear tools (list issues, list projects). Build a detection summary:

- **Email**: identify the connected account address (visible in calendar/list results, tool descriptions, or the user's known email). Multiple email MCPs → each is an option.
- **Calendar**: call the list-calendars tool and collect the user's calendars (id, name, primary flag, access role). Only offer calendars with write access.
- **Delivery options available**: Slack self-DM (if a Slack send tool exists), local markdown file (always available on local runs), both.
- **Linear**: note whether it's connected (no choice needed — used if present).

Report anything missing with how to fix it (authorize the connector in claude.ai settings, or `claude mcp add` / `/mcp` in an interactive session).

### Step 2: Ask the user

Ask these decisions (use the question tool when available; otherwise ask in chat). Present detected values as the defaults:

1. **Which email account** should be summarized and drafted from? (Options: each detected account.)
2. **Which calendar** should be read for availability and receive `[Briefing]` blocks? (Options: detected writable calendars; default the primary.)
3. **How should the briefing be delivered?** Options: Slack DM to self, local markdown file, or both (recommended when both are available).
4. **Working hours** (optional, default 09:00–17:00) — the window blocks are scheduled in.

### Step 3: Write the config

Create `~/.morning-briefing/` if missing and write `config.json`:

```json
{
  "email": { "account": "user@example.com" },
  "calendar": {
    "id": "primary",
    "workingHours": {
      "mon": "09:00-17:00",
      "tue": "09:00-17:00",
      "wed": "09:00-17:00",
      "thu": "09:00-17:00",
      "fri": "09:00-17:00"
    }
  },
  "delivery": { "slackSelfDm": true, "localFile": true, "briefingDir": "~/Documents/Morning Briefings" },
  "lookAheadDays": 21
}
```

Working hours are per weekday (`"HH:MM-HH:MM"`) — users often keep different hours on different days; when they answer with a single range, write it to all five days. A weekday key set to `null` means no blocks that day. Only these keys; omit nothing — the main skill treats a missing key as "use default", but setup always writes the full file so the user can hand-edit it later.

### Step 4: Verify

1. Read the file back and show the user a plain-language summary of what was configured.
2. Offer (don't force) a delivery test: if Slack was chosen, send one short "Morning Briefing is configured ✅" message to the user's own DM; if file delivery, confirm the briefing directory is writable.
3. Remind the user of the two usage paths: run `/morning-briefing:morning-briefing` manually, or schedule it weekday mornings. Note that cloud-scheduled runs don't share the local filesystem — if they rely on config, the schedule prompt should restate the choices (e.g. "deliver to Slack DM, calendar X"), and Slack delivery is the reliable channel there.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Guessing the calendar when several exist | List them and ask — shared/team calendars often have write access too. |
| Writing config before the user answered | Config reflects answers, not detection. |
| Testing delivery without asking | The test message is opt-in. |
| Telling the user setup failed because one source is missing | Configure what exists; record the gap; the briefing degrades gracefully. |
