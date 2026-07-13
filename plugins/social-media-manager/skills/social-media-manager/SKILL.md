---
name: social-media-manager
description: Use when the user wants to plan, batch, or schedule social media posts, or says "plan my social posts", "schedule content", "content calendar", "social media batch", or "run the social media manager". Asks how many posts to schedule, at what cadence, for which platforms and formats; scans Reddit and news sites for trending content ideas in the user's niche; interviews the user to capture their perspective and direct quotes (maintaining a persistent voice profile so posts sound like the user, not AI); authors a writing prompt and a Higgsfield media prompt per post; and saves each post as a Linear issue with scheduling metadata and both prompts.
---

# Social Media Manager

Plans a batch of social posts end-to-end: intake → trend scan → voice interview → dual prompt authoring → one scheduled Linear issue per post. The output is not posts — it is production-ready prompts a future agent executes, each anchored to the user's real words.

**Core principle: no AI slop.** Every post is built around the user's verbatim quotes. A writing prompt without at least 2 direct quotes from the user is invalid and MUST NOT be saved.

## Critical guardrails

1. **Never invent quotes.** Quotes come only from this session's interview or the voice profile, verbatim.
2. **Voice profile lives at `~/.claude/social-media-manager/voice-profile.md`** — user-level state that survives plugin updates. NEVER write files inside the plugin directory (it is replaced on update).
3. **Linear writes are creates only** (`Linear:save_issue` for new issues). Never modify or delete existing issues. Never create labels.
4. **This skill never calls Higgsfield tools.** It authors media prompts *for a future agent* to execute.
5. **Every prompt passes the Quality Checklist** (in [references/prompt-templates.md](references/prompt-templates.md)) before saving. Fail → fix → recheck, maximum 2 loops, then surface remaining gaps to the user.
6. **If the Linear MCP is unavailable**, write the same issue bodies to `~/Documents/Social Posts/<today>-batch.md` and tell the user clearly. Never silently drop posts; never claim issues were created when they were not.
7. **Interviews are plain conversation**, not AskUserQuestion option lists — multiple choice cannot capture verbatim quotes.

## Run checklist

Copy this checklist at the start of every run and check items off as you go:

```
Social Media Manager run:
- [ ] Phase 0: Today's date (Bash `date`); voice profile exists?
- [ ] Phase 1: Intake (count, platforms, cadence, formats, niche)
- [ ] Phase 2: Idea scan -> shortlist -> user picks
- [ ] Phase 3: Interview (deep first-run OR per-topic) -> quotes captured verbatim
- [ ] Phase 3b: Voice profile created/updated
- [ ] Phase 4: Per post: writing prompt + media prompt authored
- [ ] Phase 4b: Every prompt passed the Quality Checklist
- [ ] Phase 5: Team/project chosen -> publish dates computed -> one issue per post
- [ ] Phase 6: Summary table delivered
```

## Reference loading map

Load each reference only when its phase begins:

| Phase | Load |
|---|---|
| 1 Intake | [references/platform-playbook.md](references/platform-playbook.md) |
| 2 Idea scan | (nothing — procedure is inline below) |
| 3 Interview | [references/interview-guide.md](references/interview-guide.md) |
| 4 Prompts | [references/prompt-templates.md](references/prompt-templates.md) (keep playbook context from Phase 1) |
| 5 Linear | [references/linear-issue-template.md](references/linear-issue-template.md) |

## Phase 0 — Context

1. Get the date: `date +%Y-%m-%d` and `date +%A` via Bash.
2. Check whether `~/.claude/social-media-manager/voice-profile.md` exists. This decides Phase 3's mode.
3. If Linear MCP tools are deferred in this session, load `Linear:list_teams`, `Linear:list_projects`, `Linear:save_issue`, and `Linear:list_issue_labels` via ToolSearch now. If the Linear server is absent entirely, note it — guardrail 6 applies at Phase 5.

## Phase 1 — Intake

Read [references/platform-playbook.md](references/platform-playbook.md) first. Then ask via AskUserQuestion. NEVER re-ask anything the user already stated in their request.

- **Platforms** (multi-select): LinkedIn / X / Instagram / TikTok / Facebook.
- **Post count**: offer 3 / 5 / 10; recommend whichever fills a 1-2 week queue at the likely cadence.
- **Cadence** per selected platform, with the playbook norm as the labeled default (e.g. "LinkedIn — 3x/week (norm: 3-5x/week)").
- **Formats** (multi-select), filtered to what the chosen platforms support per the playbook's compatibility matrix.
- **Niche / topic focus**: on a first run, ask as a plain question. On repeat runs, default from the voice profile's About section and confirm.

## Phase 2 — Idea scan

Procedure (inline; no reference file):

1. Build 4-6 WebSearch queries from the niche. Patterns:
   - `site:reddit.com <niche> <current month and year>` — trending discussions
   - `site:reddit.com r/<relevant subreddit> "hot take" OR "unpopular opinion" <niche>`
   - `<niche> news this week`
   - `<niche> debate OR controversy`
   - `"why does nobody talk about" <niche>`
2. WebFetch the 3-5 most promising results to confirm the discussion is substantive; capture the URL and the top arguments.
3. Present a shortlist of **2x the post count, capped at 10 ideas**. Each idea: one-line headline, why it is trending, source link, and a suggested angle *for this user* (informed by voice-profile Positions when available).
4. The user picks via AskUserQuestion (multi-select; batch 4 options at a time if needed) until exactly `post count` ideas are chosen. One idea may cover multiple posts/platforms if the user says so — extract separate content atoms per post (see the playbook's strategy rules).

## Phase 3 — Interview

Read [references/interview-guide.md](references/interview-guide.md). Two modes:

- **First run (no profile):** run Part A (deep interview: positions, phrases, stories, tone), then Part B per chosen idea. Create `~/.claude/social-media-manager/` and write `voice-profile.md` using the guide's exact section skeleton.
- **Repeat run:** load the profile and confirm it aloud in one paragraph ("Here's the voice I have on file: ..."). Run only Part B per chosen idea, offering Quote-bank reuse first. Append new quotes/stories per the guide's update rules and add an Interview log row.

Hard rules: plain conversation (guardrail 7); capture answers word-for-word; ask "can I quote you on that?" for the strongest lines; minimum 2 quotes per post (4+ for threads/carousels). If material is thin, ask follow-ups — do not proceed underfed.

## Phase 4 — Prompt authoring

Read [references/prompt-templates.md](references/prompt-templates.md). For each post:

1. Fill the **writing prompt template**: system context from the voice profile, platform spec from the playbook, this run's story and verbatim quotes, output format with banned-phrase list.
2. Fill the **media prompt template**: pick the Higgsfield model from the guidance table, aspect ratio from the playbook's spec sheet for that platform/format, self-contained generation prompt.
3. Run the **Quality Checklist** against both prompts. On failure: fix and recheck (max 2 loops). If a failure needs user input (e.g. not enough quotes for a thread), go back and ask — never pad with invented material.

## Phase 5 — Linear storage

Read [references/linear-issue-template.md](references/linear-issue-template.md).

1. Call `Linear:list_teams`; let the user pick via AskUserQuestion. Then `Linear:list_projects` for that team; let the user pick (offer "no project").
2. **Compute publish dates** from the playbook's cadence-to-weekday pattern table. Start from tomorrow — never today, never the past. Interleave platforms. Date arithmetic via Bash: `date -v+3d +%Y-%m-%d` (macOS) or `date -d "+3 days" +%Y-%m-%d` (GNU/Linux).
3. One `Linear:save_issue` per post: title, description, team, project, and dueDate exactly per the template's field mapping. Record each returned issue identifier/URL.
4. **Fallback:** if Linear is unavailable or errors persist, write all issue bodies (template-conformant) to `~/Documents/Social Posts/<today>-batch.md`, tell the user, and explain how to connect the Linear MCP.

## Phase 6 — Summary

Deliver a markdown table: # | Platform | Format | Topic | Publish date | Issue. Then note where the voice profile lives and what was added to it this run.

## Terminology

Use these terms consistently, never synonyms: **post**, **idea**, **writing prompt**, **media prompt**, **voice profile**, **publish date**, **cadence slot**.
