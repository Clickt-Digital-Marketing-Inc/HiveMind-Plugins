# CLAUDE.md — {{PROJECT_NAME}}

Guidance for executing this project. It is planned in Linear; this file keeps every session on-rails.

<!-- GENERATION NOTES — delete this comment block after customizing.
Placeholder values by domain:
- {{DOMAIN}}: software | content | social | event | other
- {{TOOLS_AND_CHANNELS}}: the tools, platforms, and channels the project runs on (CMS, scheduler, email platform, venue systems); for software, the stack
- {{VERIFICATION_METHOD}} (how an issue is proven done):
  software — tests pass, logs checked, behavior demonstrated
  content — draft approved by the named reviewer; piece live or scheduled at the stated URL/tool with required fields set
  social — every post scheduled and visible in the scheduling tool; approval recorded from the named approver
  event — confirmations in writing: signed contract, confirmed headcount, run-of-show sign-off
- {{MILESTONE_VERIFICATION}} (the milestone-wide check):
  software — full test suite
  content — QA sweep of every piece in the milestone against brand and acceptance criteria
  social — full calendar review in the scheduling tool against the plan
  event — every vendor, venue, and logistics item confirmed in writing
- {{CLIENT_FACING_IDENTITY}}: who the work is presented as (from the brief's Constraints). If it DIFFERS from the executing organization (white-label), add a hard rule as the FIRST project-specific rule: "every client-visible artifact — reports, spreadsheets, decks, emails, review requests — is attributed to {{CLIENT_FACING_IDENTITY}}; the executing org's name appears only in internal tooling; check every outbound artifact for the internal name before sharing." If they are the same, omit the rule and the header line.
- REFLEXION RULE: keep the "Reflexion at the end of every issue" section only if executing this project involves code changes (domain: software, or a hybrid/"other" project with a software component). Otherwise delete: that section, the reflect-verdict item in the completion comment, the "(and, on software projects, reflect has run — see below)" clause under "Update issue status", and the "(or, on software projects, its reflect verdict)" clause in milestone check step 3 — leave no dangling reflect references. Non-software issues end at verification against acceptance criteria plus the wrap-up comment.
- GIT RULE: keep the "Git workflow" section and fill {{GIT_REPO}} / {{DEFAULT_BRANCH}} only if the project has a code repo (repo-backed / software). Otherwise delete: that section, the "Repo / default branch" header line, and the "on repo-backed projects, the PR is merged" clause under "Update issue status" — leave no dangling git references. Pure content/CMS/Drive projects deliver via the file+mirror flow, not branches/PRs.
-->

- **Project:** {{PROJECT_NAME}}
- **Domain:** {{DOMAIN}}
- **Client-facing identity:** {{CLIENT_FACING_IDENTITY}} <!-- delete this line if same as executing org -->

- **Tools & channels:** {{TOOLS_AND_CHANNELS}}
- **Repo / default branch:** {{GIT_REPO}} / {{DEFAULT_BRANCH}} <!-- delete this line for non-repo projects -->
- **Linear team / project:** {{LINEAR_TEAM}} / {{LINEAR_PROJECT}}
- **Milestones (integration checkpoints):** {{MILESTONE_LIST}}
- **Lessons Log:** the Linear document named "Lessons Log" on the {{LINEAR_PROJECT}} project

## Session start

Before pulling an issue:

1. Read the project's **Lessons Log** document in Linear and apply any relevant entries.
2. Pull the next issue from the project and read it in full — it contains everything needed to execute that task.

## Linear is the source of truth

Every unit of work is a Linear issue, and each issue is written to be executed as a standalone prompt.

- **Execute only what the issue specifies.** If the issue is missing context or contains an unresolved decision, stop and flag it rather than improvising — a well-formed issue shouldn't need outside context.
- **Update issue status** as you move: claim it (in-progress) when you start — on repo-backed projects this claim happens *before* any git action and is the lock that stops two agents taking one issue — and done only when acceptance criteria are proven (and, on software projects, reflect has run — see below; on repo-backed projects, the PR is merged — see Git workflow).
- **Never work off-Linear.** If new work surfaces mid-project, create an issue for it rather than silently expanding scope.
- **Assume parallel agents.** Other agents may be executing other issues of this project at the same time. Coordinate only through Linear: an In-Progress issue is owned — never start it. Pick only unclaimed, unblocked issues.

## Linear sync at issue boundaries

Exactly two comments per issue:

- **On starting**: post the todo plan as a comment — checkable items for what you're about to do. This is the human's chance to catch a bad plan early.
- **On completing**: post one wrap-up comment: what changed, verification evidence ({{VERIFICATION_METHOD}}), deviations from the plan, on software projects the reflect verdict, and on repo-backed projects the PR link and its check status. Then update the issue status.
- **No per-item progress comments.** No comment per checkbox, no mid-flight updates unless the plan's items materially change. The oversight value is in plan and outcome, not noise. (Status transitions and Lessons Log appends are separate normal actions, not counted against this cap.)
- If a Linear write fails, don't block the work: note the failure and fold the missed update into the completion comment or the next session.

Track the plan locally as checkable items (`tasks/todo.md` or your todo tool) while you work; the Linear comments are the record.

## Lessons Log

The project's Linear document "Lessons Log" is the single canonical store of lessons. There is no local lessons file.

- **After any correction from the user** (or a review pass that surfaces a repeatable mistake): append one line to the document **immediately**, before resuming work — format: `pattern → rule that prevents it (issue ID)`. Keep entries terse; the log is read at every session start.
- If the append fails, record the lesson in the issue's completion comment and append it at the next session start.

## Reflexion at the end of every issue

<!-- SOFTWARE PROJECTS ONLY — delete this entire section for non-software domains. -->

Before marking any issue done, run:

```
/reflexion:reflect
```

- **Let the skill triage, never pre-triage.** Do not decide "this issue is trivial, skipping reflect" — invoke it and let its own complexity triage route trivial changes to its quick path. Skipping the invocation because the work "obviously passes" is the exact rationalization this rule exists to block.
- **Record the verdict** in the completion comment: path taken, confidence, any issues found and fixed. Recording a verdict presupposes reflect actually ran — never write one from your own judgment.
- An issue is not done until reflect passes and acceptance criteria are proven.

## Milestone integration check

At each milestone boundary — {{MILESTONE_LIST}} — before starting the next milestone's issues:

1. Run the milestone verification — {{MILESTONE_VERIFICATION}} — across the whole milestone, not just the last issue.
2. **Re-read every issue in the milestone** and verify its acceptance criteria still hold in the assembled state — don't trust "done" status alone.
3. **Read the Lessons Log and the milestone's completion comments** for unresolved flags or deferred concerns. Resolve mechanical items yourself; for judgment calls, file a follow-up issue rather than deciding unilaterally or silently dropping them. If a completion comment is missing its verification evidence (or, on software projects, its reflect verdict), flag that in the summary — don't backfill it.
4. **Post a milestone summary comment** on the project recording verification results and how each flag was handled.

This is integration verification: per-issue checks cover each piece of work while it's still in context; this checkpoint catches cross-issue interaction problems no single session could see.

## Git workflow

<!-- REPO-BACKED PROJECTS ONLY — delete this whole section for pure content/CMS/Drive projects with no code repo. -->

Repo: **{{GIT_REPO}}** · default branch: **{{DEFAULT_BRANCH}}**. Every issue is delivered on its own branch and PR. **Assume other agents are working other issues in parallel** — these rules exist to keep parallel work from colliding. Per issue, in order:

1. **Claim before touching git.** Move the issue to In Progress (or In Review, if the workflow has it) and self-assign in Linear *first*. An issue already In Progress is owned by another agent — never start it. This claim is the lock that prevents two agents on one issue.
2. **Isolate in a worktree.** From an up-to-date `{{DEFAULT_BRANCH}}`, create a git **worktree** on a new branch named with the issue's Linear `gitBranchName` (Linear generates one per issue; using it exactly is what auto-links the branch, PR, and status). One issue = one branch = one worktree = one agent. Never work on `{{DEFAULT_BRANCH}}`, never inside another agent's worktree. (See the `git-worktrees` skill for the commands.)
3. **Commit small.** Focused commits, each message referencing the issue key (e.g. `ABC-123: …`) so Linear links them.
4. **Open a PR** from the issue branch to `{{DEFAULT_BRANCH}}`, with the issue key in the title and body. Rebase on the latest `{{DEFAULT_BRANCH}}` first; resolve any conflict on your own branch — never force-push `{{DEFAULT_BRANCH}}`.
5. **Verify.** The PR must be green — {{VERIFICATION_METHOD}} — and reflect must have passed. Prove it before asking for merge.
6. **Stop for merge approval — never self-merge.** Post the wrap-up comment with the PR link and evidence, then ask the user to approve the merge. Merging to `{{DEFAULT_BRANCH}}` is outward-facing and hard to reverse: it is a hard gate, every time. Only after explicit approval: merge the PR, delete the branch, remove the worktree, and mark the issue done.

Parallel-safety rules:

- **Claim in Linear before any git action** (step 1) — the anti-collision lock.
- **Never start an issue whose `blockedBy` isn't merged** — its output doesn't exist yet.
- **Small PRs, merged promptly** — long-lived branches diverge and conflict; keep each issue's change tight.
- **Rebase, don't force.** Bring `{{DEFAULT_BRANCH}}` into your branch; never rewrite shared history.

**Linear ↔ GitHub linkage:** using the exact `gitBranchName` and the issue key in the PR lets Linear's GitHub integration move issue status automatically. If that integration is **not** enabled in the Linear workspace, update issue status through the Linear MCP manually at each step — do not assume it happened.

## Plan mode + verification gates

- **Plan first.** For any non-trivial task (3+ steps or a structural decision), enter plan mode before starting execution. If something goes sideways mid-execution, stop and re-plan — don't keep pushing.
- **Verification before done.** Never mark an issue complete without proving it works: {{VERIFICATION_METHOD}} — demonstrate the acceptance criteria hold. Ask: "would a senior practitioner in this discipline approve this?"
- **Autonomous fixing.** Given a failing check or a flagged defect (failing test, broken link, off-brand copy, unconfirmed vendor), fix it — point at the evidence and resolve it rather than asking for hand-holding.

## Core principles

- **Simplicity first.** Make every change as simple as possible — the smallest change that works.
- **No laziness.** Find root causes; no band-aid fixes. Senior-practitioner standards, whatever the discipline.
- **Minimal impact.** Touch only what's necessary. Don't introduce defects — in code, copy, or logistics.
