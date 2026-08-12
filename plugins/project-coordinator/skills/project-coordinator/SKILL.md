---
name: project-coordinator
description: Coordinates a project end-to-end as a project coordinator — assesses project state, routes between idea refinement and Linear planning, structures the project root folder, generates the guidance markdown that keeps coding agents on-rails, and enforces Linear as the source of truth with every issue executable as a standalone prompt. Covers software and marketing projects alike — content planning, social media calendars, events, launches. Use when the user says "act as my project coordinator", "coordinate this project", "set up this project", "kick off this project", "plan this campaign", "set up the content calendar", "coordinate this event", "what should I work on next", "audit my Linear issues", "groom the backlog", "is this project set up right", or "get this repo/project folder ready for an agent".
---

# Project Coordinator

Orchestrate a project's lifecycle — software builds and marketing projects alike (content plans, social calendars, events, launches). This skill does not re-interview the user about their idea and does not re-plan the work — those jobs belong to two sibling skills that it invokes:

- **`idea-refinement`** — turns a raw idea into a decision-complete project brief.
- **`plan-to-linear-build`** — turns a brief into a Linear project (milestones + issues as standalone prompts) plus a root `CLAUDE.md`.

Invoke the registered skills `project-coordinator:idea-refinement` and
`project-coordinator:plan-to-linear-build` through the current host's skill
selection mechanism. If a plugin-namespaced name is not found, fall back to the
registered skill with the same base name (plain or another namespace) — they
are the same skill.

## Operating principles

- **Linear is the single source of truth.** Work is never tracked outside Linear. New work discovered mid-flight becomes a new issue, not a side note in a file. When repo files and Linear disagree, Linear wins.
- **Every issue is a standalone prompt.** A fresh agent with zero conversation context must be able to execute it. The test is the four-point checklist in [../plan-to-linear-build/references/issue-as-prompt.md](../plan-to-linear-build/references/issue-as-prompt.md).
- **Hard gate on writes.** Nothing is written to Linear, and no existing file is overwritten, without explicit user approval. Read existing files first, propose a merge, never overwrite silently.
- **Never guess the phase.** If the project's state is ambiguous, ask the user one focused question.
- **Assume parallel agents.** Multiple agents may work different issues of the same project at once. Coordination runs through Linear: an issue's status is its lock (In Progress = owned). Recommend only unclaimed, unblocked issues. Repo-backed work is isolated per issue via its own branch and worktree, and merges are gated on the user's approval — never self-merged. Detail in [references/parallel-git-workflow.md](references/parallel-git-workflow.md).

## Step 0: Assess state, then route

Inspect the working directory (brief? `CLAUDE.md`? `docs/`? `tasks/`?) and, if the user references one, the Linear project. While assessing, establish the project's **domain** — software, content, social, event, or other — from the brief or by asking; it is recorded in `docs/PROJECT.md`, passed to `plan-to-linear-build`, and sets the verification vocabulary throughout. For repo-backed (software) projects, also check whether a **GitHub repo is connected** (`git remote`); if not, prompt the user to connect or create one during setup — the per-issue git workflow depends on it. Then route:

| Observed state | Route |
|---|---|
| Raw idea, no brief | Invoke `idea-refinement`. Do not start planning or structuring yet. |
| Brief exists (or user supplies one), no Linear project | Run the new-project pipeline below. |
| Brief exists but is soft — unresolved decisions leaking outside Risks & Open Questions, a goal a third party couldn't verify | Send it back through `idea-refinement`, naming the specific gaps. Do not plan on a soft brief. |
| Linear project exists | Ongoing operations below. |
| Ambiguous | Ask one focused question. |

## New-project pipeline

Copy this checklist into your response as soon as this pipeline begins — including when step 1 routes to `idea-refinement` — and check items off as you complete them:

```
Coordination Progress:
- [ ] 1. Brief is decision-complete (idea-refinement done or brief validated)
- [ ] 2. Project root structured (docs/, tasks/, brief in place)
- [ ] 3. plan-to-linear-build run (Linear project + root CLAUDE.md exist)
- [ ] 4. Handoff verified (issues pass standalone checklist, placeholders filled)
```

**1. Secure the brief.** If none exists, invoke `idea-refinement` and let it run to a delivered brief. If one exists, validate it: decisions and open questions separated, verifiable definition of done, nothing invented. Soft brief → back to `idea-refinement` with the gaps named.

**2. Structure the project root.** Create the layout defined in [references/project-structure.md](references/project-structure.md): `docs/` holding the brief and a `PROJECT.md` generated from [assets/PROJECT.template.md](assets/PROJECT.template.md), and `tasks/` with `todo.md` (local plan scratchpad — lessons live in the project's Linear "Lessons Log" document, not in a local file). Fill what is known now; `PROJECT.md` placeholders that depend on Linear (project URL, milestones) get filled in step 4.

**3. Hand off to planning.** Invoke `plan-to-linear-build` with the brief as input. It runs plan mode, gets approval, connects the GitHub repo (repo-backed projects), creates the Linear project, and writes the root `CLAUDE.md` including the parallel-safe git workflow. Do not duplicate any of that here.

**4. Verify the handoff and backfill.** Confirm: the Linear project, milestones, issues, and the "Lessons Log" project document exist; every issue passes the standalone checklist; root `CLAUDE.md` exists with no `{{PLACEHOLDER}}` left unfilled. Then backfill the Linear-dependent placeholders in `docs/PROJECT.md` (project URL, milestone list). Report the result with the Linear URL and point the user at the first issue. Never summarize a partial handoff as complete.

## Ongoing operations

For an existing Linear project. Detailed procedures live in [references/issue-audit.md](references/issue-audit.md).

**Issue audit** — "audit my issues", "are these ready for Claude": resolve the project (`list_projects` / `get_project`), pull its issues (`list_issues`, `get_issue`), validate each body against the four-point standalone checklist plus the structural checks in the reference (required body structure, one-task scope, milestone assigned), and report pass/fail per issue with the specific defect. An audit ends at the report with proposed rewrites — run the grooming loop only when the user asks for fixes or approves them.

**Grooming loop** — "clean up the backlog", "fix these issues": for each failing issue, rewrite the body to the required structure (Objective, Context, Task, Acceptance criteria, Notes), re-validate against the checklist, present the before/after to the user, and only on approval write back with `save_issue`. Repeat until every issue passes.

**What's next** — "what should I work on": read the Linear project state, recommend the next **unclaimed** (not In Progress — another agent owns those) and **unblocked** issue, respecting milestone order and the priority ladder. On repo-backed projects, first surface any **PRs awaiting merge approval** — clearing the merge queue unblocks dependents and is the user's gate. If a milestone boundary was just crossed, remind the user to run the milestone integration check (the domain's milestone-wide verification — full test suite for software, QA sweep of assembled content or the calendar, written vendor confirmations for events — plus acceptance criteria re-verified across the milestone, flag review, summary comment) before starting the next milestone's issues — per-issue verification (with `/reflexion:reflect` on software projects) happens inside each issue, not at this boundary.

**Status check** — "where are we": summarize milestone and issue progress from Linear. On repo-backed projects, include who is holding what (In-Progress issues = agents mid-flight) and the open-PR / merge-approval queue. Flag drift between the repo (`tasks/todo.md`, `CLAUDE.md`, `docs/PROJECT.md`) and Linear — completed work not marked done, work in files that has no issue, a merged PR whose issue is still open. Linear wins; propose the corrections, then apply on approval.

## Linear MCP access

Before any operation that reads or writes Linear, confirm that the Linear tools
are reachable through a connected app, connector, or MCP server —
`list_teams`, `list_projects`, `get_project`, `list_issues`, `get_issue`,
`save_issue`, plus what `plan-to-linear-build` needs. Tool names may carry a
server prefix such as `mcp__linear__` or a plugin namespace. If the host defers
tools, use its discovery or search mechanism before calling; deferred is not
unavailable (Claude Code example: ToolSearch).

If the Linear integration is not connected or authenticated: say so plainly
and do not silently degrade. Refinement and folder structuring still work; for
the rest, save the outputs (plan, audits, rewritten issue bodies) to
`docs/linear-handoff-pending.md` so the user can apply them once Linear is
connected — nothing from the session should be lost. In the fallback path,
defer the root `CLAUDE.md` and the Linear-dependent `PROJECT.md` fields rather
than writing unfilled placeholders, and report the handoff as **pending**,
never complete. When a later session finds `docs/linear-handoff-pending.md` and
Linear is available, resume by importing that plan (approval gate still
applies) instead of re-planning.
