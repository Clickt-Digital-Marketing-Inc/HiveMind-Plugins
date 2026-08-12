---
description: Walk the In Review queue (and decision queue) with structured verdict choices - evidence-honest summaries with each question, explicit rulings executed immediately
argument-hint: [optional scope, e.g. "decision queue only" or an issue id]
---

Work the review queue interactively with the user. Load the `close-issues` skill from this plugin first if you haven't — it carries the full protocol: per-issue procedure, structured-choice format with conversational fallback, batching rules, verdict execution, and the safety rails.

## Before starting

1. Read the project's CLAUDE.md files for the conventions the skill needs: state file (default `tasks/todo.md`), decision-queue parent, reviewer identity, status flow. Missing conventions → stop and ask.
2. `$ARGUMENTS` may narrow the scope (a single issue id, "decision queue only"); default scope is the full In Review queue, oldest first, plus the decision queue.

## Run

Follow the skill: pull each issue's full record, synthesize the evidence-honest summary, surface embedded decisions as their own questions, present structured choices (≤4 questions, decision-carrying issues solo) through the host UI or as numbered chat options, stop and wait on dismissal or silence, and execute every explicit verdict immediately with the skill's safety rails. Batch Linear writes >~5 through a subagent.
