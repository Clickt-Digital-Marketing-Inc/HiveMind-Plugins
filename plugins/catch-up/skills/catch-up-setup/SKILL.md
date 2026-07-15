---
name: catch-up-setup
description: >
  Configure the catch-up plugin before first use. This skill should be used when
  the user asks to "set up catch-up", "configure catch-up", "change my catch-up
  tools", "reconfigure catch-up", or when a catch-up run finds no saved
  configuration. Captures which call-transcript tool, email inbox, and project
  tracker to use, plus how issues and drafts should be handled, and saves them
  for future runs.
---

Configure the catch-up plugin and save the result to `~/.catch-up/config.json`.
Keep the whole conversation in plain language. Do not show the user file paths,
JSON, or tool IDs unless they ask.

## 1. Check for an existing configuration

Read `~/.catch-up/config.json`.

- If it exists, summarize the current settings in plain language (which call
  tool, which inbox, which tracker, how issues are handled, how drafts are
  handled) and ask what they want to change. Re-ask only the parts they choose
  to change; keep the rest.
- If it does not exist, this is first-time setup. Continue.

## 2. Ask which tools to use

Use AskUserQuestion. Cover the three tool categories and the two behavior
settings. Present real options for each category (see `CONNECTORS.md`), and rely
on the free-text box for tools not listed.

1. **Call transcripts** — where meeting recordings/notes live (Granola,
   Microsoft Teams, Google Meet, Zoom, Otter, Fireflies, ...).
2. **Email inbox** — which email tool (Gmail, Outlook, ...) and which address to
   scan.
3. **Project tracker** — where issues should be filed (Linear, ClickUp, Asana,
   Jira, Monday, Notion, ...), and roughly where inside it (which team, project,
   or list, and a default assignee if wanted).
4. **Issue handling** — review each run before creating, create automatically,
   or decide each run.
5. **Email drafts** — draft replies owed and follow-ups, only one of those, or
   none.

Also ask, or pick a sensible default of 7 days, how far back the very first run
should look, since there is no "last run" yet.

## 3. Confirm each chosen tool is actually connected

For each chosen tool, verify it is reachable before saving. Discover the tool's
functions with ToolSearch (e.g. search "granola meetings", "gmail search",
"linear create issue") and make one lightweight read call (list recent meetings,
list recent threads, list teams/projects/lists).

- If a tool responds, it is connected.
- If its functions are not available, tell the user in plain language to connect
  that tool in Cowork's connector settings, then come back. Do not save a broken
  configuration.

## 4. Save the configuration

Create the folder `~/.catch-up/` if needed and write `config.json` following the
schema in `references/config-schema.md`. Do **not** write a `last_run` value —
leaving state unset makes the first catch-up use the first-run lookback window.

## 5. Confirm

Tell the user, in plain language, that setup is done: which tools it will read,
where issues go, how issues and drafts will be handled, and how far back the
first run will look. Tell them they can start any time by saying "run catch-up".
