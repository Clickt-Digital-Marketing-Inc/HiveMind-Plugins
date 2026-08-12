---
description: Run the learnings loop interactively - diff-shaped lesson proposals as structured choices, approved edits applied and committed, rejections checkpointed
argument-hint: [optional note, e.g. "session close" or "after round N reflect"]
---

Run the learnings loop interactively with the user. Load the `lessons-review` skill from this plugin first if you haven't — it carries the full protocol: lesson sources, the diff-shaped proposal format, structured options with a conversational fallback, apply semantics, and rejection handling.

## Before starting

1. Read the project's CLAUDE.md files for the state file location (default `tasks/todo.md`) and the Lessons Log convention.
2. Collect lessons from the current session's checkpoints and round records: reflect findings, gate-finding classes appearing ≥2 times, user corrections, and executor-flagged process gaps. `$ARGUMENTS` may note the occasion (session close, post-reflect) but never changes the protocol.

## Run

Follow the skill: distill each lesson into a diff-shaped proposal (exact lines, target file, one-line "why now" with issue ids), present it through the host's structured-choice UI or as numbered chat options with the diff alongside (≤4 per batch; dismissal or silence means stop and wait), apply explicitly approved lessons immediately (free-text amendments win; commit citing the ruling; never batch an unapproved lesson into an approved commit), and record rejections in the checkpoint.
