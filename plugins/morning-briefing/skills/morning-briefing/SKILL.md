---
name: morning-briefing
description: Use when the user asks for their morning briefing, daily briefing, "start my day", or when a scheduled daily run fires. Reads Gmail to summarize conversations and identify emails needing replies (creating draft responses), reads Linear for project progress, blocked issues, and issues assigned to the user, prioritizes that work, and blocks time on Google Calendar for email review, unblocking teammates, and focused issue work, and looks ahead three weeks for time-off blocks that collide with planned deadlines (bottlenecks). Produces a Morning Briefing markdown file.
---

# Morning Briefing

## Overview

Generate a single daily Morning Briefing markdown file from three sources (Gmail, Linear, Google Calendar), create Gmail drafts for emails needing replies, and block time on the calendar for: reviewing drafts, unblocking teammates (only if needed), and focused Linear issue work.

**Core principle: read freely, write conservatively.** The only writes permitted are Gmail *drafts* (never send), *new* calendar events created by this run, and the briefing file. Never send email, never write to Linear, never touch existing calendar events.

## Critical Guardrails

- **Weekends: skip entirely.** If today is Saturday or Sunday, write nothing, draft nothing, create nothing. Report "Weekend — briefing skipped." and stop.
- **NEVER send an email.** Use only the tool that *creates a draft*. Never call any tool whose action sends (e.g. `send_message`, `send_email`, `send_draft` — a tool with "draft" in its name can still send). If unsure whether a tool sends, do not call it; put the proposed reply text in the briefing instead.
- **Linear is strictly read-only.** No writes of any kind: no issue edits, no comments, no status updates, no reactions, no label changes.
- **Calendar events are create-only.** Prefix every created event title with `[Briefing]`. Never update, delete, or respond/RSVP to any calendar event — not the user's events, and not `[Briefing]` events left over from an earlier or crashed run. Never decline or free up a busy slot to make room.
- **Run once per day.** Before doing anything else, check for today's briefing file and for `[Briefing]`-prefixed events on today's calendar. If either exists, report that today's briefing was already generated (say where the file is) and stop. If the user *explicitly* asks to regenerate anyway, rewrite the briefing file only — still create zero new drafts and zero new calendar events; a direct request never overrides the write guardrails.
- **Never double-book.** Only create events inside free slots computed per the rules below.
- **Slack: self-DM only.** The one permitted Slack write is posting the briefing to the user's own DM. No channels, no DMs to others, no @-mentions — the briefing may name teammates, but it must never notify them.

## Free-Slot Rules

Apply these whenever choosing a time for any block:

- Working hours default to 09:00–17:00 local. Config `calendar.workingHours` overrides **per weekday** (`"mon": "10:00-16:00"`, …); use today's entry, and a `null` entry means create no blocks today. Slots start at `max(current time, start)` and end at today's configured end — never schedule in the past, never past the end.
- Read busy times from **all calendars visible to the account** (primary, shared, team) so no real commitment is invisible; create events on the **configured calendar only** (default: primary). Take the timezone from that calendar's settings; fall back to the system clock if unavailable.
- All-day events marked busy or out-of-office block the entire day; other all-day events (birthdays, FYI holidays) do not block. Events the user declined do not count as busy; tentative events do.
- If a gap is too small for a block (any block — email, unblock, or focus): shrink a focus block to a minimum of 30 minutes; the email and unblock blocks are fixed at 30. If a block won't fit anywhere, defer it and say so in the briefing's Calendar section. Never overlap events or extend beyond working hours.
- Created events go on the configured calendar with **no attendees**.

## Workflow

Execute the steps in order. First inspect the tools available through the host's
connected apps, connectors, and MCP servers. When the host supports tool
discovery or search, use it to locate Gmail capabilities (search threads, get
thread, list drafts, create draft), Linear capabilities (list projects, list
issues, get user, status updates), and Calendar capabilities (list calendars,
list events, create event). Claude Code example: use ToolSearch for deferred
tools. If a required integration is unavailable, note the gap in the briefing
under "Skipped" and continue with the remaining sections. Do not fail the whole
briefing because one source is down.

### Step 1: Establish context

1. Read `~/.morning-briefing/config.json` (written by the companion `setup` skill). It selects the email account, target calendar, working hours, delivery method, and briefing directory. If the file is missing, use defaults — connected Gmail account, primary calendar, 09:00–17:00, deliver to both local file and Slack self-DM when available — and mention at the end that `/morning-briefing:setup` customizes these.
2. Determine today's date and local timezone **with a live check** (run `date` or read the calendar response) — never reuse a date remembered from earlier in the conversation; long sessions cross midnight and a stale date triggers the wrong weekday rules. If Saturday or Sunday, apply the weekend guardrail and stop.
3. Run the once-per-day check (briefing file at `<briefingDir>/YYYY-MM-DD.md`, `[Briefing]` events today). Create the briefing directory if it doesn't exist.
4. List today's events on the configured calendar and build the free-slot map per the Free-Slot Rules.

### Step 2: Email

1. Search Gmail with one query: `in:inbox newer_than:2d` — except on Monday, use `in:inbox newer_than:4d` so Friday-afternoon and weekend email isn't lost to the weekend skip. Cap at 25 threads total.
2. Read each thread and classify: **needs my reply** / **FYI only** / **noise**. A thread needs a reply when the last message is from someone else, addresses the user directly, and asks a question, requests action, or awaits a decision. If the last message is the user's own, no reply is needed.
3. List existing Gmail drafts first; skip any thread that already has a draft (count it as "draft ready" in the briefing, noting it predates this run). Match drafts to threads by thread ID; if the drafts listing doesn't expose thread IDs, match by recipient + subject.
4. For each remaining **needs my reply** thread, create a draft reply in the user's voice: direct, brief, concrete, matching the thread's tone. Where a reply hinges on a decision only the user can make, write the draft with a clearly marked placeholder like `[YOUR CALL: option A or B]`.
5. If any drafts exist for review (new or pre-existing), schedule one 30-minute `[Briefing] Review & send email drafts` event in the earliest free slot.
6. Record in the briefing: the needs-reply table (From, Subject, Their ask, Draft summary) and short bullets for FYI threads. Do not list noise threads.

### Step 3: Linear projects

1. Resolve the current Linear user (match the user's email) and find projects in **started** state. Caution: Linear MCP `state` filters can silently return empty for state-*type* values (e.g. `state="started"` matching nothing) — list all projects and filter client-side on `status.type == "started"` instead.
2. For each, pull recent status updates and issue counts by state; write a 1–3 sentence progress note (what moved, what's at risk, target dates). For the health rating, use the latest status update's health field if set; otherwise judge from progress against the target date.
3. Find **blocked** issues across those projects: blocked state, "Blocked" label, or recent comments indicating waiting on someone. Read the comments to determine *who* is waiting and *on whom*.
4. Issues blocked on the **user**: list each in the briefing's decisions table (issue, who's waiting, decision needed). **Only if** this table is non-empty, schedule one 30-minute `[Briefing] Unblock teammates` event — preferably in the next free slot after the email block; if no slot exists after it, use the latest free slot before it; if none fits at all, defer per the Free-Slot Rules. Zero blockers → zero event.
5. Issues blocked on **third parties**: mention in one line under the owning project's progress note; they never appear in the decisions table and never trigger an event.

### Step 4: My issues → focus blocks

1. List Linear issues assigned to the user whose state type is `started` or `unstarted` (exclude `backlog`, `triage`, completed, and canceled states). Query per status **name** (e.g. one call with `state="In Progress"`, one with `state="Todo"`) — an unfiltered assignee query sorts by `updatedAt` and can return only recently-closed issues, burying the workable ones.
2. Prioritize: urgent/high priority first, then due date, then project target dates, then age.
3. Batch the top issues into one or more focus blocks. The user works multiple issues simultaneously, so a block covers a *set* of issues, not one. Size each block by:
   - **A — availability:** the free gaps left after the email/unblock blocks, per the Free-Slot Rules.
   - **B — appropriateness:** issue estimates if set; otherwise assume ~45 min per small issue, ~90 min per meaty one. Target 60–180 minutes per block, shrinking to the 30-minute minimum when that's all that fits.
4. Create the event(s) titled `[Briefing] Focus: <ISSUE-IDs>` (e.g. `[Briefing] Focus: HIV-12, HIV-15, HIV-18`), description listing each issue's identifier, title, and Linear URL.
5. Issues that don't fit today go in the briefing under "Deferred" with a note on why.

### Step 5: Three-week look-ahead (bottleneck check)

Read-only — this step never creates events or modifies anything; bottlenecks are flagged in the briefing only.

1. List calendar events for the next **21 days** and collect **time-off blocks**: out-of-office events, all-day events marked busy, and events whose titles indicate absence (vacation, PTO, OOO, holiday, time off, travel, sick). Also count multi-hour commitments that consume most of a workday (conferences, offsites, all-day client days).
2. Collect the **deadlines** landing in that window (plus 3 working days past it, to catch deadlines just beyond a trip): due dates on the user's open issues, project target dates, and milestone dates mentioned in project descriptions or recent status updates.
3. For each deadline, compute the working days actually available before it: weekdays in the window, minus time-off days. Flag a **bottleneck** when any of these hold:
   - The deadline falls **during** a time-off block or within 2 working days after one ends.
   - Time off removes **a third or more** of the working days remaining before the deadline.
   - The remaining work is plainly larger than the remaining available days (use issue estimates/counts and judgment — e.g. 20 open issues targeted at a date with 4 available days).
4. For each time-off block, find the **meetings that conflict with it**: scheduled events (not the time-off event itself, not `[Briefing]` blocks) overlapping the absence. For each, suggest a move in the briefing: name the meeting, date/time, organizer, and a concrete alternative — a specific free slot before the trip for one-off meetings, "skip this occurrence" for recurring ones, or "delegate/decline" when the user isn't the organizer. Base suggested slots on actual free time in the calendar. **Suggest only** — never move, decline, or RSVP to the meeting; the user actions it.
5. Report in the briefing's Look-ahead section: each time-off block (dates, source event title), each flagged bottleneck (deadline, what it collides with, days actually available) with a one-line suggested adjustment (start earlier, move the date, delegate), and the meetings-to-move table. Do not flag deadlines that remain comfortable — this section is for genuine collisions, not a full calendar recap.

### Step 6: Write and deliver the briefing

1. If file delivery is enabled (config `delivery.localFile`, default true): write `<briefingDir>/YYYY-MM-DD.md` using the structure in [references/briefing-template.md](references/briefing-template.md). Every section is always present; an empty section gets its one-line "none" note from the template.
2. **Slack delivery** (config `delivery.slackSelfDm`, default true when a Slack MCP is available): post a copy as a **DM to the user themselves** (resolve the user via their own email, or the current-user ID if the tool description states it; use that user ID as the channel). Check the send tool's description for format support: some Slack MCPs accept standard markdown including headers and tables; if not, convert to mrkdwn (headers → `*bold*` lines, tables → bullets, links → `<url|text>`). Respect the per-message character limit (commonly ~5,000): post a condensed briefing — TL;DR, bottlenecks, meetings-to-move, today's blocks — and put overflow in a threaded reply rather than truncating silently. Rules: this self-DM is the **only** Slack write permitted; never post to a channel, never DM anyone else, never @-mention anyone. Slack unavailable → note under "Skipped"; the file is still the source of truth.
3. End by telling the user where the file is, whether it was posted to Slack, how many drafts were created, and which calendar blocks were added (with times).

## Common Mistakes

| Mistake | Fix |
|---|---|
| Sending email instead of drafting | Only the draft-creation tool. "Draft" in a tool name does not make it safe — check what the tool *does*. Unsure → don't call it. |
| Duplicating drafts or events on re-run | Step 1 once-per-day check stops the run; Step 2.3 skips threads that already have drafts. |
| Trusting a date remembered from earlier in the session | Check the clock live at run start — a session that crosses midnight will otherwise apply the wrong weekday rules (e.g. weekend-skipping a Monday). |
| Scheduling in the past or over existing events | Follow the Free-Slot Rules: slots start at `max(now, 09:00)`, tentative counts as busy, busy/OOO all-day events block the day. |
| Scheduling an "Unblock" block when nothing is blocked on the user | That event is conditional on the decisions table being non-empty. |
| Writing to Linear "helpfully" (a comment tagging a teammate, a status update) | Read-only means read-only. The unblocking happens in the user's scheduled block, not by the skill. |
| One calendar event per issue | Batch issues into shared focus blocks; the user multi-tasks. |
| Failing entirely because one MCP server is down | Degrade gracefully: skip that section, note it under "Skipped", continue. |
| Look-ahead that recaps the whole calendar | Step 5 reports only time-off blocks and genuine deadline collisions — a comfortable deadline is not a bottleneck. |
| Treating the look-ahead as license to reschedule | Step 5 is read-only. It flags; the user decides. Never move events or change Linear dates. |
| Draft replies that are vague filler | Draft real, sendable replies; use `[YOUR CALL: …]` placeholders only where a genuine decision is the user's. |

## Resources

- [references/briefing-template.md](references/briefing-template.md) — the exact markdown structure for the briefing file.
