---
name: plan-to-linear-build
description: Turns a build or project request into a plan-mode planning session that ends by writing the plan into a Linear project, then scaffolds a customized root CLAUDE.md to govern the work. Covers software builds and marketing projects alike (content plans, social media calendars, events, launches). Use whenever the user wants to spec out and hand off a build/feature/campaign/event/project — phrases like "let's plan this build", "spec this out into Linear", "set up a Linear project for this", "turn this into issues", "turn the content calendar into issues", "plan this campaign into Linear", "plan mode then hand off", or when they want a project's CLAUDE.md generated to enforce Linear discipline. Trigger even if they don't name Linear explicitly but are clearly scoping multi-step work for later execution by an agent.
---

# Plan to Linear Build

This skill takes a build or project request — software or marketing (content, social, events, launches) — and produces two handoff artifacts: (1) a **Linear project** whose issues each read as a standalone execution prompt, and (2) a **root `CLAUDE.md`** customized to the project that enforces Linear usage, plan mode, verification, `/reflexion:reflect` at the end of every issue on software projects, and integration checks at milestone boundaries. For repo-backed (software) projects it also governs the per-issue **Branch → Commit → PR → merge-on-approval** git workflow, written to be safe for multiple agents working in parallel.

The point is separation of thinking from doing. Plan mode is where ambiguity gets resolved; Linear is where the resolved plan lives so any future agent (or the same agent in a fresh context) can pick up an issue and execute it cold. The CLAUDE.md keeps that discipline enforced across every session.

## Workflow

Track progress with this checklist:

```
Handoff Progress:
- [ ] Step 0: Verify Linear MCP access
- [ ] Step 1: Plan mode — plan is decision-complete
- [ ] Step 2: Team confirmed, plan approved by user
- [ ] Step 3: Issues validated against standalone checklist, then created in Linear
- [ ] Step 4: CLAUDE.md customized and written (existing file handled)
- [ ] Step 5: Handoff summarized with project URL
```

### 0. Verify Linear MCP access

Before planning, confirm that the Linear tools are reachable through a
connected app, connector, or MCP server — you will need `list_teams`,
`save_project`, `save_milestone`, and `save_issue`. Tool names may carry a
server prefix such as `mcp__linear__` or a plugin namespace. If the host defers
tools, use its discovery or search mechanism before calling (Claude Code
example: ToolSearch).

If the Linear integration is not connected or authenticated: tell the user,
and do not silently degrade. Offer to run the planning session anyway and save
the full plan (overview, milestones, issue bodies) to a local markdown file they
can import once Linear is connected — nothing from the session should be lost.

### 1. Plan Mode

Enter plan mode for the work. Do not write anything to Linear or disk yet. Plan mode exists to finalize the plan and gather everything needed to hand off — structural decisions, tools and channels, unknowns, dependencies, acceptance criteria.

- **Establish the project's domain** — software, content, social, event, or other — from the brief or by asking (a coordinator may pass it in). The domain sets the verification vocabulary used in the issues and the CLAUDE.md.
- **For repo-backed (software) projects, confirm the GitHub repo.** Ask the user to connect an existing repo or create one (`gh repo create`), verify `gh`/git auth is working, and record the repo URL and default branch — these fill the CLAUDE.md git-workflow placeholders. If the project has no code repo (pure content/CMS/Drive work), skip this; offer git only if they want drafts versioned through PRs. Don't create a repo without approval — it's an outward-facing action.
- If the request is non-trivial (3+ steps or any structural decision), stay in plan mode until the plan is concrete enough that each future task could be executed without you present to clarify.
- Ask targeted questions to close ambiguity. Prefer resolving an unknown now over encoding "figure out X" into an issue later.
- Identify the natural **milestones** (logical checkpoints where an integration check makes sense — e.g., "scaffolding complete", "auth working end-to-end" for software; "all pillar content drafted and approved", "venue and vendors locked" for marketing work).
- Within each milestone, decompose into **discrete, single-task issues** — one issue = one focused unit of work, small enough to execute in one sitting.
- **When the work decomposes over a per-item spec** (a page map, a content calendar, an event vendor list), default to **one issue per item**, each embedding that item's full spec row — a "write 6 pages" batch issue is not a standalone prompt for any of the 6. Reserve batch issues for operations that genuinely span items: publishing, QA sweeps, observation checkpoints.

The outcome of plan mode is a written plan structured as: project overview → milestones → discrete issues per milestone, each issue with enough context to stand alone.

### 2. Confirm the Linear team, then get approval

Before writing anything to Linear:

- **Ask the user which Linear team/context** the project should live under. Do not guess — list available teams via the Linear MCP's `list_teams` tool and let them pick.
- **Present the full plan** (milestones + the list of issues with their titles) and wait for explicit approval. Nothing goes into Linear until the user says go. This is a hard gate — the whole value of the handoff is that the user vetted it.

### 3. Create the Linear project and issues

Once approved:

1. **Validate every issue body first.** Check each drafted issue against the standalone checklist in [references/issue-as-prompt.md](references/issue-as-prompt.md) — required structure present, all names concrete, no unresolved decisions, acceptance objectively checkable. Fix any failure before creating anything; do not create an issue that fails a check.
2. `save_project` — create the project under the chosen team, with the plan overview as the description.
3. `save_milestone` for each milestone (optional but preferred — it gives the integration checkpoints structure).
4. `save_issue` for each validated task, assigned to its milestone so the milestone → integration-check mapping is explicit.
5. `save_document` — create a project document named **"Lessons Log"**, seeded with one header line explaining the entry format: `pattern → rule that prevents it (issue ID)`. Executing agents read it at every session start and append to it after corrections; the CLAUDE.md template depends on this document existing.
6. **Encode execution order — milestones alone are not enough.** An executor opening the backlog must be able to resolve "what's next" without guessing: (a) create and apply **phase labels** matching the waves/phases (plus an "Ops" label for operational gates); (b) encode within-milestone order as a **priority ladder**, with the rationale stated in the plan (e.g. farm-first, hubs-before-publish); (c) set `blockedBy` **only for true dependencies** (validations → publish, checkpoint → next phase's work) — never chain parallelizable items into a fake sequence; (d) append a **"Recommended execution order"** section to the project description stating the tie-break rules, so humans and agents pick the same next issue.
7. **Verify creation.** Confirm from the tool results (or by reading the project back) that the project, every milestone, every issue, and the Lessons Log document exist. If any write failed, retry or report exactly what is missing — never summarize a partial handoff as complete.

### 4. Generate the root CLAUDE.md

Copy [assets/CLAUDE.template.md](assets/CLAUDE.template.md) and customize it to this specific project. Fill in the placeholders (project name, domain, client-facing identity, tools & channels, Linear team/project, milestone list, verification methods, and — for repo-backed projects — the git repo and default branch — the template's generation notes list per-domain values) and prune sections that don't apply. **For repo-backed projects keep the Git workflow section; delete it for pure content/CMS projects with no code repo** (the generation notes flag it). **If executing the project involves no code changes, delete the reflexion section and every reflect reference — the template's generation notes list them all** (a hybrid/"other" project with a software component keeps reflect); those issues end at verification against acceptance criteria plus the wrap-up comment. The template already encodes the four things that must be enforced:

- **Linear-issue-as-prompt workflow with boundary sync** — every unit of work maps to a Linear issue; the agent pulls the next issue, posts its plan as a comment on start, executes, and posts one wrap-up comment (outcome, verification evidence, and on software projects the reflect verdict) on completion. No per-checkbox noise.
- **`/reflexion:reflect` at the end of every issue (software projects)** — invoked before any software issue is marked done; the skill's own complexity triage sets the depth, and the agent never pre-triages ("trivial, skipping" is the blocked rationalization).
- **Plan mode + verification gates** — plan first, prove it works before marking done, with "proven" defined by the domain (tests pass; draft approved and live; confirmations in writing).
- **Lessons Log + milestone integration checks** — lessons live in the project's Linear "Lessons Log" document (appended immediately after any correction, read at every session start); each milestone boundary triggers the domain's integration verification (full test suite for software; QA sweep of the assembled content or calendar; every vendor/venue item confirmed in writing) plus acceptance criteria across the assembled milestone and flag review.
- **Git workflow, parallel-safe (repo-backed projects)** — each issue is delivered on its own branch (named with the issue's Linear `gitBranchName`) in its own worktree, committed, and opened as a PR; the executing agent claims the issue in Linear before touching git (the anti-collision lock for parallel agents) and **stops for the user's merge approval — it never self-merges**.

Write the customized `CLAUDE.md` to the **project root** (the repo root, or the user's working directory if no repo is specified — confirm the path if ambiguous). **If a CLAUDE.md already exists there, do not overwrite it**: read it, show the user what you'd add, and merge the template's sections into it with their approval.

### 5. Summarize the handoff

Report back concisely: the Linear project URL, the milestones and issue count, and confirmation that `CLAUDE.md` was written and to where. Point the user at the first issue as the entry point.

## Key principles

- **Issues are prompts, not tickets.** A traditional Linear ticket assumes a human with context. Here the reader is an agent starting cold. Over-specify rather than under-specify. Details in [references/issue-as-prompt.md](references/issue-as-prompt.md).
- **Verification happens in context; milestones are integration checkpoints.** Issues are executed by fresh-context agents, so the only moment an agent can genuinely examine a piece of work is right after doing it — hence per-issue verification, with `/reflexion:reflect` on software projects. A milestone boundary instead triggers an integration check (the domain's milestone-wide verification, acceptance criteria across the assembled chunk), which is the one thing per-issue review structurally cannot see. Group issues so each milestone is a coherent, verifiable chunk.
- **Nothing is written until approved.** Plan mode → confirm team → present plan → approval → validate → write. The approval gate is what makes the handoff trustworthy.
