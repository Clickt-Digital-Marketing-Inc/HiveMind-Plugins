---
description: Run the pre-merge review gate (mixed-tier finders -> batched verifier -> fix-applier) on an integration worktree
argument-hint: [worktree] [branch] [base]
---

Run the merge-gate workflow on an integration worktree. Load the `merge-gate` skill from this plugin first if you haven't — it documents the protocol, the context-argument convention, and the launch/resume rules.

## Gather the arguments

From `$ARGUMENTS` if provided (order: worktree, branch, base), otherwise determine or ask:

1. **worktree** — absolute path to the integration worktree with the branch checked out. If none exists yet, create one at a durable absolute path (not a session-scoped scratchpad if the run might outlive the session): `git worktree add <path> <branch>`.
2. **branch** — the integration branch under review.
3. **base** — merge target, default `main`.
4. **context** — compose it yourself; do not skip it. It must contain: a one-paragraph summary per lane in the branch (issue id, what it changed, owned surfaces) and **every accepted deviation** from the executors' wrap-ups, each written as `ACCEPTED DEVIATION: <what> — <who accepted, why>`. This is what stops finders re-litigating settled calls.
5. **applyFixes** — default `true` unless the user says review-only.

## Launch

- **Script resolution:** if the project has its own copy at `.claude/workflows/merge-gate.js`, that copy is canonical — use its path. Otherwise use this plugin's copy at `workflows/merge-gate.js` under the plugin root (resolve the installed plugin directory, e.g. `~/.claude/plugins/cache/<marketplace>/orchestrator/<version>/workflows/merge-gate.js`).
- **Launch by `scriptPath`, never by `name`**, if the script has been edited this session (the name registry can serve a stale snapshot). Launching by scriptPath always is the safe habit.
- Invoke the Workflow with `args: { worktree, branch, base, context, applyFixes }`.
- **Record the run id immediately** in the project's checkpoint state file (default `tasks/todo.md`) with resume instructions: `resume via Workflow { scriptPath, resumeFromRunId: "<wf_id>" }`. Runs are resumable after limit kills.
- Usage-window rule: do not start the gate if it can't finish inside the visible window — checkpoint and halt instead.

## After the run

Report findings and the fix report compactly (never pull raw finder output into context). If fixes touched serialized snapshots/exports, note the orchestrator-side import/re-sync step owed. Then continue the landing sequence per the `orchestrator` skill: reflect pass → QC battery → merge → push → prune.
