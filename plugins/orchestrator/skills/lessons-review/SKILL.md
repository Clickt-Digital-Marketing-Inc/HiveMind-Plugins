---
name: lessons-review
description: Use when running the learnings loop interactively - "review the lessons", "run lessons-review", after a reflect pass, or at session close. Collects lessons (reflect findings, gate-finding classes appearing twice or more, user corrections, executor-flagged process gaps), presents diff-shaped proposals via AskUserQuestion with the diff in the question text, applies approved edits with commits, and records rejections in the checkpoint so they are not re-proposed.
---

# Lessons Review

The interactive mechanism for the orchestrator skill's **learnings loop**. You are the coordinator: this runs in the main loop only — never as a subagent, never via a sub-orchestrator. The popup answer is the ask-first approval gate the learnings loop requires; nothing is applied without one.

## Sources

Collect from the current session's checkpoints and round records:

1. **Reflect findings** — anything reflect flagged as a process gap rather than a lane defect.
2. **Recurring gate-finding classes** — a finding class appearing in two or more merge gates is a missing rule, not a coincidence.
3. **User corrections** — any correction from the user this session is a lesson by definition.
4. **Executor-flagged process gaps** — gaps executors surfaced in wrap-ups or stop-and-flag escalations.

## Proposal shape

Every lesson becomes a **diff-shaped proposal** before it reaches a popup:

- The **exact lines** to add or change — not a vibe, not a summary.
- The **target**: project root CLAUDE.md, the nested CLAUDE.md governing the surface, the project's Lessons Log document, or both CLAUDE.md and Log when a project rule has a portable moral.
- A one-line **"why now"** citing the incidents (`ISSUE-##`; when no issue exists, the round or gate id).

## The popup

Present via **AskUserQuestion**, up to **4 lessons per popup**, the **diff in the question text** — the user judges the exact wording from the popup, not the chat scroll. Propose in **checkpoint order** (oldest incident first) and fill popups in that order, so the batching is deterministic.

Options per lesson:

- **"Apply as proposed (Recommended)"**
- **"Apply to Lessons Log only"**
- **"Rewrite it — tell me how"**
- **"Reject"**

**Free-text answers amend the wording: apply what the user actually wrote, not the original proposal.** The amendment replaces the proposed lines; the target file stays the same unless the user names another. A dismissed popup = stop and wait — never proceed on silence, never treat dismissal as approval.

## Applying

The popup answer **is** the approval — apply immediately, one lesson at a time:

- **CLAUDE.md edits**: when the `claude-md-management` plugin is installed, apply via its `revise-claude-md` flow; when it isn't, apply inline (the diff was already shown and approved in the popup). Same edit either way — the plugin is preferred, never required.
- **Lessons Log**: append one line, format `pattern → rule (ISSUE-##)`.
- **Commit** the edit with a message citing the ruling.
- **Never batch an unapproved lesson into an approved commit.** One approval covers exactly the lessons it named.

## Rejections

Record rejected lessons in the checkpoint (state file) as rejected, with a one-line reason where the user gave one — so they are not re-proposed next session — and commit the state-file update (see `/checkpoint`). A rejection is a ruling, not a deferral: deferrals go back into the queue explicitly at the user's request only.
