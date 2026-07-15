# catch-up

Turn new call transcripts and emails into tracked issues and draft replies.

Each time you run it, catch-up looks at everything since it last ran — your
meeting transcripts and your email inbox — pulls out the tasks, decisions, and
open questions, files them in your project tracker, and drafts the emails you owe.
It remembers when it last ran, so nothing gets processed twice.

## Components

| Skill            | What it does                                                         |
| ---------------- | ------------------------------------------------------------------- |
| `catch-up-setup` | First-run configuration: pick your call, email, and project tools.  |
| `catch-up`       | The main run: read new calls + emails, propose issues, draft emails.|

## Setup

Run setup once before the first catch-up:

> "set up catch-up"

You'll choose:

- **Call transcripts** — Granola, Microsoft Teams, Google Meet, Zoom, Otter, ...
- **Email inbox** — Gmail or Outlook, and which address to scan
- **Project tracker** — Linear, ClickUp, Asana, Jira, Monday, Notion, and where
  issues should go
- **How issues are handled** — review each run, create automatically, or decide
  each run
- **Email drafts** — replies owed, follow-ups, both, or none
- **First-run lookback** — how far back the very first run should reach

Connect each tool in Cowork's connector settings first. See `CONNECTORS.md`.

Your choices are saved to `~/.catch-up/config.json`. Re-run setup any time to
change them.

## Usage

> "run catch-up"  (or "catch me up")

catch-up will:

1. Work out the window since its last run
2. Read new call transcripts and emails
3. Extract tasks, decisions, and open questions
4. De-duplicate against your tracker
5. Create issues (by default, after you review them)
6. Draft replies and follow-ups for you to review and send
7. Report what it did

Drafts are always saved for your review and never sent automatically.

## Configuration and state

- `~/.catch-up/config.json` — your saved tool choices and preferences
- `~/.catch-up/state.json` — the timestamp of the last run

## Customization

This plugin is tool-agnostic. Skills refer to tools by category (`~~call
transcripts`, `~~email`, `~~project tracker`); you bind each category to a real
tool during setup. See `CONNECTORS.md` for the categories and options.
