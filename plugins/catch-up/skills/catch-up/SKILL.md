---
name: catch-up
description: >
  Read all new call transcripts and emails since the last run and turn them into
  tracked issues and draft emails. This skill should be used when the user says
  "run catch-up", "catch me up", "process my calls and emails", "what came out of
  my meetings and inbox", "turn my recent calls and emails into tasks", or asks
  to file follow-ups from recent meetings. On first use with no saved
  configuration, run the catch-up-setup skill first.
---

Turn everything new since the last run into tracked issues and draft emails.
Keep all user-facing output in plain language. Follow these steps in order.

## 1. Load configuration and state

Read `~/.catch-up/config.json`.

- If it does not exist, tell the user catch-up is not set up yet and run the
  `catch-up-setup` skill first. Do not guess tools.

Read `~/.catch-up/state.json` for `last_run` (it may not exist yet).

## 2. Determine the time window

- If `last_run` exists, the window is from `last_run` to now.
- If not (first run), the window is from now minus `first_run_lookback_days`
  (from config) to now.

State the window to the user in plain language ("Catching up on everything since
Tuesday 9am...").

## 3. Gather new call transcripts

Use the configured call tool (`~~call transcripts`). Discover its functions with
ToolSearch if needed. List meetings/transcripts whose date falls in the window,
then fetch each transcript's text. See `references/tool-adapters.md` for
per-tool guidance.

If there are no new calls, say so and continue.

## 4. Gather new emails

Use the configured email tool (`~~email`). Search the configured inbox for
messages in the window. Include received messages, and check sent messages only
to tell whether a thread has already been replied to. See
`references/tool-adapters.md`.

If there are no new emails, say so and continue.

## 5. Extract action items, decisions, and open questions

For every call transcript and email thread, extract discrete items following
`references/extraction-guide.md`. For each item capture:

- **Type** — task / decision / question
- **Title** — short, action-first
- **Detail** — enough context to act without re-reading the source
- **Source** — the call name + date, or the email subject + sender
- **Owner** — you, or someone else, if clear
- **Reply needed** — whether this implies an email you owe or a follow-up you
  must send

Skip small talk, resolved items, and anything already done. When unsure whether
something is worth tracking, keep it and mark it low priority rather than
dropping it.

## 6. De-duplicate against the tracker

Before proposing issues, search the configured `~~project tracker` for existing
issues that match each item (by title and keywords). Merge or skip anything that
already exists so the same task never lands twice. Also collapse items that
appear in both a call and an email into one issue with both sources. Note skipped
duplicates for the final summary.

## 7. Create issues (respect the configured issue-handling mode)

- **review** — present all proposed issues as a table grouped by source (which
  call/email each came from). Let the user approve, edit, or drop each one, then
  create only the approved issues in the tracker.
- **auto** — create every proposed issue, then report what was created.
- **ask** — ask the user which of the above to use this time, then follow it.

When creating each issue, put the source and key context in the description so
it is traceable back to the call or email. File issues into the target location
from config.

## 8. Draft emails (respect the configured draft mode)

If drafts are enabled (`both`, `replies`, or `followups`), identify:

- **Replies owed** — email threads in the window where someone is waiting on the
  user's response and no reply has been sent yet.
- **Follow-ups** — action items where the user needs to email someone (from calls
  or emails).

Write each as a **draft** in the configured email tool. Never send. Follow the
draft-writing guidance in `references/extraction-guide.md`. Present the list of
drafts saved and why each exists.

## 9. Save state and summarize

Write the current time as `last_run` in `~/.catch-up/state.json` (create it if
needed), with a one-line summary of the run.

> Update `last_run` only after issues and drafts are handled, so an interrupted
> run does not cause the next run to skip unprocessed calls and emails.

Give the user a plain-language wrap-up: how many calls and emails were processed,
how many issues were created and where, how many drafts were saved, and anything
skipped as a duplicate or left out.
