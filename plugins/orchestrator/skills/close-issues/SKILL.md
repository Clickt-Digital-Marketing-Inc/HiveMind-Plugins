---
name: close-issues
description: Use when the user wants to work the In Review queue interactively - "close out the review queue", "walk me through In Review", "let's clear the board", "review the issues", "work the decision queue". Coordinator-run structured-verdict workflow - per issue, pull the full record, synthesize an evidence-honest summary, surface embedded decisions, present batched choices with a conversational fallback, then execute explicit rulings immediately with safety rails. Also covers the project's decision queue.
---

# Close Issues

You are the **coordinator** walking the In Review queue with the human reviewer,
one structured verdict prompt at a time. This runs in the main loop only —
never as a subagent, and it never spawns a sub-orchestrator. The user's explicit
answers are the review authority; your job is to make each verdict cheap to
give and expensive to get wrong.

## Project conventions

Read the project's CLAUDE.md files first for: the state file for checkpoints (default `tasks/todo.md`), the standing **decision-queue parent** issue, the reviewer identity, and the team's status flow. If a needed convention is missing, stop and ask rather than improvise.

## Queue order

- **In Review issues, oldest first.** `$ARGUMENTS`-style scoping (a single issue id, "decision queue only") narrows the queue but never reorders it.
- The **decision queue** — open-question sub-issues under the decision-queue parent — is in scope with the same structured-choice pattern: each question presented with its context, options, a recommendation, and the blast radius of each option.

## Per-issue procedure

1. **Pull the full record**: the issue body plus BOTH lane comments — the plan and the wrap-up. Dump long bodies to a file and extract; never pull them raw into context.
2. **Cross-reference the state file** for post-merge history: later rounds' QC often re-verified this issue's deliverable — when it did, say so in the summary. Check the file's git history for checkpoints this session didn't write.
3. **Synthesize a summary the user can judge from alone**: what shipped, the verification evidence, every disclosed deviation, and current live status. Honesty rules are hard rules:
   - Partial delivery (descoped/deferred) → say exactly what's missing.
   - Superseded by a later ruling or later work → say that too.
   - Verification evidence absent from the wrap-up → flag it; never paper over it.
4. **Surface embedded decisions as their own questions**, never buried in a verdict: judgment calls the wrap-up flagged, open items the issue's closure would silently bury, and scope-splits (close on what was delivered + file a successor issue for the remainder).

## The structured verdict prompt

Use the host's structured-choice UI when one is available. Otherwise present
the same labeled options as a numbered list in chat and wait for an explicit
reply. Include the full summary with the question so the user can judge the
verdict without reconstructing context from earlier messages.

- Verdict options per issue: **"Move to Done (Recommended)"** with a one-line rationale (only when the record earns it), **"Keep In Review"**, **"Needs rework"**.
- Decision questions get options + a recommendation, and **always a "decide later" option** that files the question as a sub-issue under the decision-queue parent rather than dropping it.

## Batching

- Up to **4 questions per choice batch**.
- Low-controversy issues (clean record, no embedded decisions) batch 4-at-a-time, each with a short per-issue preamble in chat. Batch only **consecutive** low-controversy issues — batching never reorders the queue.
- Any issue carrying a decision gets its **own prompt**.
- **A closed or dismissed choice UI, or no explicit chat reply, means stop and wait.** Never proceed on silence, never re-ask on a loop, never treat dismissal as approval.

## Executing verdicts

Execute each verdict **immediately** after the user's explicit answer:

- State moves per the verdict.
- A ruling comment on the issue — with the user's reasoning **verbatim** where they gave it.
- Spawned successor issues carry full standalone context plus `blockedBy` links.
- Decide-laters are filed under the decision-queue parent with the same full context. When the question already lives as a decision-queue sub-issue, "decide later" simply leaves it filed — nothing new is created.
- More than ~5 Linear writes in one verdict wave (one choice batch's worth of rulings) → batch them through a subagent so echoes stay out of context.
- When the walk ends or stops, checkpoint the state file (see `/checkpoint`) — rulings are state changes.

## Safety rails

Each of these was learned the hard way; none is optional.

- **Never revert or reinterpret a board state** without first checking the issue for a wrap-up comment and the state file's git history for foreign checkpoints. In Review + wrap-up = delivered work, possibly by a parallel session — treat "anomalous" state as evidence of a sibling session before treating it as an error.
- **"Needs rework" spawns a feedback cycle on the original issue** — the rework ask as a comment, the issue's state back to Todo (unclaimed, or the project's named rework state) so an executor can pick it up — never a silent re-open. Multi-cycle rework on one issue is normal; losing the thread is not.
- **Rulings that change live claims** (content pulls, restores, corrections) execute with verification: source-check via live fetch where the user supplies a citation, readbacks on database writes, snapshot re-export where the project keeps one, and a committed evidence ledger entry.
- **Decision-queue answers execute like verdicts**: immediately — the ruling recorded on the sub-issue, the ruled sub-issue closed, and any resulting work filed as new issues — never carried as chat-only agreements.

## Token discipline

Long issue bodies and comment threads go to files and get extracted — never raw into the coordinator's context. Linear write batches run through a subagent. The structured-choice prompt carries the synthesis, not the raw record.
