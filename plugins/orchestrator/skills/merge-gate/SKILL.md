---
name: merge-gate
description: Use when running or explaining the pre-merge review gate on an integration worktree - "run the merge gate", "gate this branch", "review before merge". Documents the mixed-tier finder/verifier/fix protocol behind the merge-gate workflow (workflows/merge-gate.js) and the conventions for launching, resuming, and passing accepted deviations via the context argument.
---

# Merge Gate

The merge gate is the mandatory pre-merge review on an integration worktree. It runs as the **workflow script** at `workflows/merge-gate.js` in this plugin (projects may carry their own canonical copy at `.claude/workflows/merge-gate.js` — if the project has one, that copy wins). The `/merge-gate` command gathers the arguments and launches it.

## Protocol

Three phases, fixed pipeline:

1. **Find** — 8 independent review angles over `git diff <base>...<branch>`, mixed-tier:
   - **4 correctness angles on Opus**: `line-by-line` (hunk-by-hunk bug hunt), `removed-behavior` (every deleted line's invariant must be re-established), `cross-file` (callers/registrations/name-matches/contracts/fallback paths), `altitude` (right-depth check: one deeper fix over several shallow ones).
   - **4 convention angles on Sonnet**: `reuse` (existing helpers over re-implementation), `simplification`, `efficiency` (against the project's stated perf budget), `conventions` (clear CLAUDE.md violations only, rule quoted).
   - Finders run in **chunks of ≤5 concurrent** (pacing rule). Each returns ≤6 candidates, every candidate with a concrete failure scenario. Finders do not self-censor — the verify phase filters.
2. **Verify** — **ONE batched Opus verifier**, not one agent per candidate: dedups near-duplicates, casts exactly one vote per deduped candidate (recall-biased: PLAUSIBLE by default, REFUTED only when constructible from the code), ranks most-severe first, caps at 10, adds a fix hint each.
3. **Fix** (optional, `applyFixes: true` is the norm) — an Opus fix-applier commits fixes to the worktree in one commit. It skips (with recorded reasons) anything that would change intended behavior or need work well outside the diff; preserves line endings; lints touched files per the project CLAUDE.md; never pushes, never merges, never touches the live tree; flags artifacts that need an orchestrator-side import/re-sync.

Finder output never enters the coordinator's context — only the returned findings and fix report do.

## Arguments

```
{ worktree, branch, base?, context, applyFixes?, resumable? }
```

- `worktree` — **absolute path** to the integration worktree (branch checked out there). Don't use a session scratchpad path if the run might outlive the session.
- `branch` / `base` — the integration branch and its merge target (default `main`).
- `context` — the orchestrator's change context: per-lane summaries **plus every accepted deviation** from the executors' wrap-ups. This is the convention that stops finders re-litigating settled calls (an orchestrator-accepted deviation reported in a wrap-up is settled; a finder flagging it wastes a verifier vote). Write deviations explicitly: "ACCEPTED DEVIATION: <what> — <who accepted, why>".
- `applyFixes` — run phase 3.
- `resumable` — accepted for arg-shape compatibility; resumption is harness-level (below).

## Launch and resume conventions

- **Launch by `scriptPath`, not by `name`, whenever the script has been edited this session** — the name registry can serve a stale snapshot captured at session start. Safe habit: always launch by scriptPath.
- Runs are **resumable after limit kills**: relaunch the workflow with the same scriptPath plus `resumeFromRunId: "<wf_...>"`. Record the run id in the project's checkpoint state file the moment the run starts (see `/checkpoint`).
- If the project keeps a canonical repo copy of the script and a user-level copy exists too, the repo copy is canonical — re-sync any secondary copies after editing it.

## After the gate

The gate is step one of landing, not the whole gate-to-merge sequence. The orchestrator still owes: reflect pass (Opus, per-issue MERGE/HOLD vs acceptance criteria), the QC battery, any snapshot import/re-export the fix report flagged, then merge + push + prune. See the `orchestrator` skill.
