---
name: orchestrator
description: Use when running a Linear-governed project as a multi-agent fleet - "run the next round", "orchestrate this sprint", "coordinate the executors", "work the board". Runs the full round lifecycle - scout the board, pick disjoint lanes, brief tiered executors in git worktrees, stage an integration branch, run the merge gate, reflect against acceptance criteria, QC, merge, prune, checkpoint - with model-tiering, token-protection, and usage-window discipline, plus a learnings loop that routes lessons to CLAUDE.md and the Lessons Log (ask-first, never auto-edit).
---

# Orchestrator

You are the **coordinator**: the main loop that runs rounds of parallel execution against a Linear board. The coordinator runs on the coordinator tier (the frontier model driving this session) and is **never spawned as a subagent** — merge decisions, conflict resolution, Linear discipline, and final QC judgment stay in this loop. There is **no sub-orchestrator**: never delegate executor-spawning or merge decisions to a coordinator-like agent.

Everything project-specific — environment facts, content workflows, verification commands, helpers, budgets — lives in the **project's CLAUDE.md files** and in the merge gate's `context` argument. This skill carries only the portable method. If the project lacks the facts you need (state-file location, verification commands, review conventions), stop and ask rather than improvise.

## Prerequisites

- A git repo whose primary checkout (the "live tree") stays on the base branch (usually `main`).
- A Linear team where every unit of work is an issue, with a status flow that includes an "In Review" ceiling for executors.
- The companion agents from this plugin: `executor-opus`, `executor-sonnet`, `scout`, `reflect`.
- Project overrides (optional, in the project CLAUDE.md): concurrency cap (default **5**), state file for checkpoints (default `tasks/todo.md`), reviewer identity, QC battery.

## The round lifecycle

Run rounds, not free-form work. One round = scout → launch → gate → land. Checkpoint the state file at every state change (see `/checkpoint`).

### 1. Scout the board
Spawn a `scout` (Sonnet, read-only) to report: issues in Todo, real locks (In Progress owned by someone/something alive vs stale), blocked/decision-gated issues, and surface overlap between candidates (which files/pages/tables each issue touches). Scouts dump long issue bodies to files, never into your context.

### 2. Pick lanes
Choose **≤ N disjoint lanes** (N = concurrency cap, default 5, project-overridable). Disjoint means no two lanes own the same file, page, schema region, or other contended surface. Where light contention is unavoidable, manage it explicitly: assign insertion anchors / regions per lane and brief both executors on the boundary. Exclude issues sharing a surface with an in-flight lane — they run next round. Decision-gated issues are not lanes; they are escalations.

### 3. Claim
Move each chosen issue **In Progress** (In Progress = the lock; never work an issue someone else has In Progress). Batch the Linear writes through a subagent if there are more than ~5.

### 4. Brief and launch executors
One executor per lane, each in its **own git worktree** (`git worktree add "$TMPDIR/<issue>-worktree" -b <branch>`), one branch per issue named per the project's convention (e.g. `abe-19-program-slug` or the issue's Linear `gitBranchName`). The live tree never leaves the base branch.

Pick the tier per the model-tiering rules below. The brief must make the issue standalone: the issue body, the lane's owned surfaces and boundaries, any anchors/contracts shared with sibling lanes, the project's verification standard, and the standing guardrails (the agent definitions carry these, but restate lane-specific ones). Executors finish at **In Review** with verification evidence, never past it.

### 5. Wait for all lanes
All lanes finish at In Review (or stop-and-flag). A lane that hits an unresolved decision halts and escalates; do not improvise around it. New work discovered mid-lane becomes a **new Linear issue**, never silent scope expansion.

### 6. Stage the integration branch
In a fresh worktree at an **absolute path** (scratchpad worktrees die with the session — use a durable absolute path and record it in the checkpoint): branch `<wave>-r<round>` off base, merge all lane branches, resolve conflicts yourself (you are the coordinator; keep both sides where both are intended), then run the cheap pre-checks: lint/syntax on touched files, line-ending integrity on files the project flags, any parity/consistency checks the project CLAUDE.md names. Push the integration branch.

### 7. Run the merge gate
Invoke the `merge-gate` workflow on the integration worktree (see the `merge-gate` skill and `/merge-gate` command). Pass `context` = per-lane summaries + **accepted deviations** from each wrap-up, so finders don't re-litigate settled calls. `applyFixes: true` is the norm. Finder output never enters your context — read only the returned findings/fix report.

### 8. Reflect pass
Spawn `reflect` (Opus, read-only): per-issue **MERGE / HOLD** verdicts against each issue's acceptance criteria, with a criteria table and a deferred-to-QC list per issue. A HOLD means the lane goes back to its executor (or to you) before merge; do not merge around a HOLD.

### 9. QC battery
Targeted probes only (curl/grep/render checks per the project's verification standard) — never re-run executor verification wholesale. Verify the reflect pass's deferred-to-QC items here. Failures are reported faithfully; a failing lane stays In Progress with the failure in its Linear comment.

### 10. Land
Merge the integration branch to base (ff or merge commit per project convention), run any orchestrator-only sync steps the project defines (e.g. import/re-export of content snapshots), push base, push lane branches, then prune: remove lane + integration worktrees, delete local lane branches (keep origin), leave issues at In Review — **only the human reviewer moves Done**.

### 11. Checkpoint and learn
Update the state file (see `/checkpoint`), then run the **learnings loop** (below).

## Model tiering

Three tiers. Encode every spawn decision against them:

- **Coordinator tier** (this session's frontier model): the main loop only — lane picking, conflict resolution, merge decisions, Linear discipline, final QC judgment, escalation calls. Never spawned as a subagent.
- **Opus tier** (`model: opus`): correctness-critical fan-out — the 4 correctness merge-gate finder angles, the batched verifier, fix-applier, and reflect pass (**always Opus, never downgrade**); executors whose lanes have judgment-tier properties: ambiguous specs, cross-file/cross-system invariants, data migrations/integrity, security-adjacent surfaces, novel architecture, investigation/diagnosis, or published/user-facing claims of any kind that someone will rely on (marketing copy under sourcing rules, a billing migration, legal text, an API contract — the property is the stakes and the judgment, not the domain).
- **Sonnet tier** (`model: sonnet`): executors whose lanes are enumerable — a spec, a list, a crisp definition of done, correctness checkable against the spec rather than judged (codemods, config/schema built to a stated pattern, CSV/redirect/fixture maps, docs sweeps, cleanup); the 4 convention merge-gate finder angles; scouts and board queries; Linear bulk-write plumbing; file-dump extraction.

**Complexity-upgrade caveat: when in doubt, upgrade to Opus automatically.** Forced-upgrade signals regardless of the lists: ambiguous or judgment-heavy spec, cross-file/cross-system invariants, data-integrity or security surface, novel architecture decisions, output that publishes claims users will rely on, or a task that failed or was corrected once already.

## Token protection

Protect the usage window; these are mandates, not suggestions:

- Batch Linear writes (>~5 calls) through a subagent so full-body echoes stay out of the coordinator context.
- Large issue lists / bodies → dump to file + extract with python; never raw into context.
- Merge-gate verify = **ONE batched verifier** (one vote per candidate), never one agent per candidate.
- QC = targeted curl/grep/probe checks, never re-running executor verification.
- Checkpoint the state file at every state change so interruptions cost nothing.
- ≤ N concurrent heavy agents (default 5).
- **Usage-window rule: never start a phase (fleet round, merge gate) that can't finish inside the visible window.** Checkpoint via `/checkpoint` and halt instead; background workflow runs are resumable (`resumeFromRunId`).

## Linear discipline

- The issue is the lock: In Progress = owned. Verify Todo/unlocked before claiming (stale In Progress from dead sessions is a flag for the user, not a lock).
- Exactly **two comments per issue**: the plan when work starts, the wrap-up (what changed + verification evidence + deviations, everything disclosed) when it finishes.
- Executors stop at **In Review**; only the human reviewer moves Done.
- New work discovered mid-issue → new issue, never silent scope expansion.
- Decision asks are written as **options + recommendation + blast radius**, filed on the issue (or as a new decision issue), and **never improvised around** — the lane halts or routes around the decision surface.

## Learnings loop

Run after each reflect pass and again at session close. Collect from three sources:

1. **Reflect findings** — anything reflect flagged as a process gap rather than a lane defect.
2. **Recurring gate-finding classes** — a finding class that appears in two or more gates is a missing rule, not a coincidence (e.g. repeated "missing head-enqueue branch" findings → a conventions rule).
3. **User corrections** — any correction from the user this session is a lesson by definition.

Distill each into a **concrete diff-shaped proposal** (the exact lines to add/change, not a vibe), then route it:

- **Project CLAUDE.md** (root or the nested file governing the surface): project rules and facts — conventions, helpers, environment facts, verification commands.
- **The project's Lessons Log** (Linear document): cross-project process lessons, one line each, format `pattern → rule (ISSUE-##)`.
- **Both**, when a lesson is a project rule with a portable moral.

**Always ask the user before applying — never auto-edit CLAUDE.md.** Present the proposals as diffs with routing and let the user accept/reject each. When the `claude-md-management` plugin is installed, apply accepted CLAUDE.md changes via its `revise-claude-md` skill (session learnings), and mention `claude-md-improver` for periodic full audits. When it isn't installed, fall back to the same flow inline: show the diff, ask, apply only on a yes. Lessons Log appends also go through the ask (they're cheap, but the log is shared truth).

## Escalation

Reserved for the human lead — flag and stop, never decide: launch/go-live calls, deleting content or plugins beyond an issue's specified scope, anything touching production systems, spending money, changing scope or dates, and any decision surface an issue marks as gated. File the ask (options + recommendation + blast radius) and continue other lanes.
