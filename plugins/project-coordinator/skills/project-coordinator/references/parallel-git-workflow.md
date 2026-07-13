# Parallel agents + git workflow

How the coordinator sets up and supervises repo-backed projects that many agents execute at once. The **per-issue lifecycle** the executing agents follow lives in the generated root `CLAUDE.md` (from `plan-to-linear-build`'s `CLAUDE.template.md`) — this reference covers setup, the coordination mechanics, and the rationale.

## Contents
- The core idea
- Connecting the repo (setup)
- The claim lock (how parallel agents avoid collisions)
- Worktree isolation
- Linear ↔ GitHub linkage
- The merge gate
- Conflict handling
- Non-repo projects

## The core idea

Parallel agents are safe when two things hold: **work is claimed before it starts** (so no two agents take one issue) and **work is isolated while it happens** (so agents don't fight over a working tree or branch). Linear is the claim layer; git worktrees are the isolation layer. Everything else follows from those two.

## Connecting the repo (setup)

For repo-backed (software) projects, `plan-to-linear-build` connects a GitHub repo before writing the CLAUDE.md:

- Confirm `gh auth status` and `git` work.
- Connect an existing repo, or create one with `gh repo create` — **only with the user's approval** (it's outward-facing).
- Record the repo URL and default branch; they fill `{{GIT_REPO}}` / `{{DEFAULT_BRANCH}}` in the CLAUDE.md.
- Confirm (or note the absence of) the **Linear ↔ GitHub integration** in the workspace — it's what auto-links branches/PRs and moves status. If it's off, the CLAUDE.md tells agents to update status via the Linear MCP manually.

## The claim lock

The single rule that makes parallel execution safe: **an agent moves its issue to In Progress and self-assigns in Linear before touching git.** An In-Progress issue is owned; no other agent starts it. Because Linear is the shared source of truth every agent reads, this status *is* the mutex — no extra coordination channel is needed. The coordinator, when asked "what's next," recommends only issues that are **not** In Progress and whose `blockedBy` is merged.

## Worktree isolation

Each issue is executed in its own **git worktree** on its own branch, so parallel agents never share a checked-out branch or working directory:

- Branch off an up-to-date default branch, named with the issue's Linear `gitBranchName` (Linear generates one per issue).
- One issue = one branch = one worktree = one agent.
- The `git-worktrees` skill has the commands; separate clones are a heavier alternative for stronger isolation.
- `tasks/todo.md` is per-worktree scratch, so it never collides. Lessons live in the Linear "Lessons Log" document, not in files — deliberately, so parallel agents don't fight over a lessons file.

## Linear ↔ GitHub linkage

Using the exact `gitBranchName` for the branch and the issue key (e.g. `ABC-123`) in commits and the PR lets Linear's GitHub integration auto-link the branch and PR to the issue and move its status (In Progress on branch/PR open, Done on merge). This is why agents must not invent their own branch names. If the integration is not enabled, the linkage still helps humans navigate, but status must be moved manually through the Linear MCP.

## The merge gate

Merging to the default branch is the **one human gate** in the lifecycle. Agents drive Branch → Commit → PR → verify autonomously and then **stop**: they post the wrap-up comment with the PR link and evidence and ask the user to approve the merge. They never self-merge — merging to the shared branch is outward-facing and hard to reverse, exactly the kind of action the plugin always gates on approval. Only after approval does the agent merge, delete the branch, remove the worktree, and mark the issue done. The coordinator surfaces the **merge-approval queue** in "what's next" and status checks, since clearing it unblocks dependents.

## Conflict handling

- Rebase the default branch into the issue branch before opening the PR and before merge.
- Resolve conflicts on the issue branch; never force-push the default branch or rewrite shared history.
- Keep PRs small and merge promptly — long-lived branches are what cause conflicts in parallel work.
- If two issues genuinely touch the same code, that's a missed dependency: they should have been sequenced with `blockedBy`, not run in parallel. Flag it and re-sequence rather than merging blind.

## Non-repo projects

Pure content / CMS / Drive projects (e.g. a pSEO or social calendar) have no code repo: the Git workflow section is deleted from their CLAUDE.md and they deliver through the file + mirror flow. The **claim lock still applies** — parallel agents on a content project coordinate through Linear status exactly the same way; they just don't branch or PR. Offer git only if the user wants drafts versioned through PRs.
