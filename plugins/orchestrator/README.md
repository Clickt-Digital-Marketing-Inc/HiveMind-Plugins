# Orchestrator

A Claude Code plugin that **runs** projects. It is the execution-side counterpart to [`project-coordinator`](https://github.com/performance-clickt/project-coordinator) — the coordinator sets up a project (brief → Linear project → governing CLAUDE.md); the orchestrator executes it as rounds of parallel, tiered agents with a hard pre-merge review gate.

The method was battle-tested on a live multi-week website-rebuild sprint (9+ rounds, 5-lane concurrency, dozens of merges, zero base-branch accidents) and packaged so it works in **any repo with a Linear team**.

## What one install gives you

| Component | What it does |
|---|---|
| `orchestrator` skill | The entry point: the round lifecycle (scout → lanes → tiered executors in worktrees → integration branch → merge gate → reflect → QC → merge → prune → checkpoint), model-tiering rules, token-protection tactics, the usage-window rule, Linear discipline, and the learnings loop. |
| `merge-gate` skill | Documents the pre-merge review protocol: 4 Opus correctness + 4 Sonnet convention finder angles → one batched Opus verifier → optional Opus fix-applier, with resume and context-argument conventions. |
| `workflows/merge-gate.js` | The workflow script that runs the gate. Launch by `scriptPath`. Projects may carry their own canonical copy at `.claude/workflows/merge-gate.js` (that copy wins). |
| `/merge-gate` command | Gathers worktree/branch/base/context and launches the workflow, recording the run id for resumability. |
| `/checkpoint` command | Writes the HALT-STATE resume map into the project state file (default `tasks/todo.md`), commits, and pushes. |
| `close-issues` skill | The interactive review-queue workflow: per-issue evidence-honest summaries, embedded decisions surfaced as their own questions, AskUserQuestion verdicts (batched ≤4, dismissed popup = stop), immediate ruling execution with safety rails, decision-queue coverage. |
| `/close-issues` command | Entry point for the review queue: loads the `close-issues` skill, reads project conventions, walks In Review oldest-first (scope narrowable via arguments). |
| `lessons-review` skill | The interactive learnings loop: collects lessons from reflect findings, recurring gate-finding classes, user corrections, and executor-flagged gaps; presents diff-shaped proposals via popup (diff in the question text); applies approved edits with commits; checkpoints rejections. |
| `/lessons-review` command | Entry point for the learnings loop: loads the `lessons-review` skill and runs it against the session's checkpoints. |
| `executor-opus` agent | Lane executor for judgment-heavy work (defined by task properties, not domain): ambiguous specs, cross-system invariants, data integrity/migrations, architecture, investigations, published/user-facing claims. |
| `executor-sonnet` agent | Lane executor for mechanical, spec-driven work — with a tier-escape hatch when complexity shows up. |
| `scout` agent | Sonnet, read-only board/repo reconnaissance; compact reports, bodies dumped to files not context. |
| `reflect` agent | Opus, read-only per-issue MERGE/HOLD verdicts against acceptance criteria, with criteria tables and a deferred-to-QC list. |
| checkout-guard hook | PreToolUse hook that blocks `git checkout`/`git switch` in the project root (the live tree stays on the base branch) while allowing them in worktrees and other repos. |

## Requirements

- A git repo whose primary checkout stays on the base branch (the worktree rule).
- A Linear team + the Linear MCP server connected (issue = lock, In Review ceiling).
- `python3` on PATH (for the checkout-guard hook; the hook fails open without it).
- Recommended: the `project-coordinator` plugin to set projects up, and `claude-md-management` for applying learnings-loop proposals to CLAUDE.md.

## Install

This repo doubles as a Claude Code plugin **marketplace** (`clickt-orchestrator`). In Claude Code:

```
/plugin marketplace add performance-clickt/orchestrator
/plugin install orchestrator@clickt-orchestrator
```

(The repo is private — you need read access and an authenticated `gh`/git. For local testing: `claude --plugin-dir /path/to/this/repo`.)

The plugin is also published in the org's `hivemind-plugins` marketplace as `orchestrator@hivemind-plugins`. **Install from one marketplace only** — two installs of the same plugin name collide on `/orchestrator:*` commands and skill names.

## Getting started

In a repo set up with a Linear-governed CLAUDE.md, say: **"orchestrate the next round"** (or invoke the `orchestrator` skill). Run the gate directly with `/merge-gate <worktree> <branch> [base]`, and checkpoint any time with `/checkpoint`.

## Method vs project facts (the CLAUDE.md contract)

The plugin carries **only the portable method**. Everything project-specific rides in via two channels:

1. **The project's own CLAUDE.md files** (root + nested). These are the authority executors, finders, and the fix-applier read for: environment facts, verification commands, named helpers and design-system utilities, content-integrity/sourced-claims rules (e.g. E-E-A-T for marketing sites), canonical-serialization rules, performance budgets, concurrency-cap and state-file overrides, reviewer identity.
2. **The merge gate's `context` argument.** Per-round facts: lane summaries and accepted deviations, so finders don't re-litigate settled calls.

Rule of thumb: if a rule would be true in your next project too, it belongs in this plugin (file an issue/PR). If it names a path, port, command, CMS, or person — it belongs in the project's CLAUDE.md.

### Worked example: project CLAUDE.md snippet

The kind of block a project adds to its root CLAUDE.md to configure the orchestrator (this example is a WordPress rebuild; yours will differ):

```markdown
## Orchestration config

- Linear team **ACME Web (AW)**, project **Relaunch Sprint**. Status flow: Todo → In Progress → In Review → Done. Only Dana (reviewer) moves Done.
- Concurrency cap: 4 lanes. Checkpoint state file: `tasks/todo.md`.
- Live environment: local dev at `https://acme.local` (this directory). The DB is the content
  source of truth; page content changes ONLY via `scripts/export-page.sh` / `scripts/import-page.sh`
  snapshot round-trips committed under `content/`.
- Verification standard: rendered URL checked at 375px + desktop; one H1; php -l on touched PHP
  (`docker exec app php -l < FILE`); no new axe violations; no LCP/CLS regression (budget: docs/perf.md).
- Repo conventions the gate should enforce: shared helpers `acme_money()`, `acme_external_link()`;
  per-component CSS head-enqueued via `acme_enqueue_style()`; snapshots export-canonical
  (sort_keys + trailing newline); no fabricated numbers — sourceless stats render nothing.
- CRLF files (edit lines, never rewrite): functions.php, inc/legacy-*.php.
- Escalations reserved for Dana: go-live calls, deleting content, spending money, scope/date changes.
```

Everything in that block is consumed by the plugin's skills and agents without any plugin change.

## The learnings loop (and CLAUDE.md safety)

After each reflect pass and at session close, the orchestrator distills lessons (reflect findings, recurring gate-finding classes, user corrections, executor-flagged process gaps) into diff-shaped proposals routed to the project CLAUDE.md and/or the project's Lessons Log (`pattern → rule (ISSUE-##)`). **It always asks before applying — it never auto-edits CLAUDE.md.** `/lessons-review` is the interactive mechanism: proposals arrive as popups with the diff in the question text, and the popup answer is the approval. With the `claude-md-management` plugin installed it applies accepted changes via `revise-claude-md`; otherwise it shows the diff inline and asks.

## Releasing

Releasing vX.Y.Z: bump the version in **both** `.claude-plugin/plugin.json` and the plugin entry in `.claude-plugin/marketplace.json`, add a changelog entry, commit, `git tag vX.Y.Z`, push main + tag — then sync `plugins/orchestrator/` in the `HiveMind-Plugins` repo and bump its marketplace entry version to match.

## Changelog

- **0.3.0** — interactive `close-issues` and `lessons-review` workflows (skills + commands); orchestrator skill gains the multi-session coordination rules (wrap-up/foreign-checkpoint check before reinterpreting board state, one orchestrator per shared live tree/DB, `git ls-remote` before reusing integration branch names) and the concurrent-verification rule (no live mutation tests on records a sibling lane may read; sentinel values carry lane attribution).
- **0.2.0** — tier definitions by task properties, not domain: cross-domain examples in executor descriptions, skill tiering rules, README; E-E-A-T becomes a project-CLAUDE.md example.
- **0.1.0** — initial plugin: orchestrator + merge-gate skills, merge-gate workflow, /merge-gate and /checkpoint commands, four agents (executor-opus, executor-sonnet, scout, reflect), checkout-guard hook.
