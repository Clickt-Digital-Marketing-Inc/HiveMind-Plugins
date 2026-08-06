# AGENTS.md — HiveMind fleet executor contract

You (Codex, or any non-Claude agent) are an **executor** on this board. The
division of labor is fixed:

- **You execute exactly one Linear issue at a time** and stop at **In Review**.
- **Claude (the coordinator) runs the merge gate, the reflect pass, and issue
  close-out.** You never merge to main, never push main, never land your own
  work, and never move an issue past In Review. Only John moves Done.

Linear is the single source of truth. The issue body is your prompt — but
verify its premises (paths, SHAs, claimed state) against the actual artifacts
before executing; a stale claim in an issue body is disclosed as a deviation,
never inherited. If this repo has a CLAUDE.md, it binds you exactly as this
file does — read it.

## Per-issue protocol (parts of this are MACHINE-CHECKED at the merge gate)

1. **Claim:** move the issue to In Progress in Linear. In Progress = the lock;
   never work an issue someone else has In Progress.
2. **Plan comment BEFORE any edit:** post your implementation plan as a comment
   on the issue. If the issue changes a stage's behavior or expands what a
   component may write, the plan enumerates every caller and policy surface
   with one line each: needs change / unaffected.
3. **First commit is an empty marker,** before any edit:
   `git commit --allow-empty -m "HM-XXX: plan posted <plan-comment-id>"`
   The merge gate asserts the branch's first commit is this marker and that
   the plan comment's createdAt precedes the second commit's author date. A
   branch that edited first cannot manufacture this ordering and will be
   rejected.
4. **Branch:** use the issue's Linear `gitBranchName`, branched off
   `origin/main` at lane start (re-derive the base — SHAs quoted in issue
   bodies go stale). Work only in your branch.
5. **Execute against the issue's acceptance criteria only.** New work
   discovered mid-issue becomes a NEW Linear issue, never silent scope
   expansion. Decision-gated questions are escalations: file options +
   recommendation + blast radius on the issue and stop — never improvise.
6. **Write the CHANGELOG entry yourself** if this repo keeps one.
7. **Push the branch FIRST, then move the issue to In Review** with a wrap-up
   comment: what changed, how each criterion was verified, deviations, and
   lessons. Exactly two comments per issue: the plan and the wrap-up.

## Verification standards (the merge gate enforces these; unmet = findings)

- **Mutation-test every check you write.** Delete the subject → your check must
  go RED. A check that can pass when the behavior it pins is deleted is not a
  check. No OR-ed fallbacks; assert specific refusal text/exit codes, never
  merely non-zero.
- **Boundaries go red AT the boundary.** A check named for a constant or
  threshold moves that constant and shows red at x == y. When the value under
  test is a constant, sentinel-rebind the SOURCE symbol — equality against a
  byte-identical literal at the call site proves nothing.
- **Fixtures must be able to express failure.** Ask what your fixture would
  look like if the feature didn't work; a fixture with no instance of the
  distinguishing data verifies nothing.
- **Derived, never hand-listed.** Coverage parametrizes over the shipped set
  (entry points, registered tools) so new work is covered by construction.
  A locally re-derived copy of another module's predicate is a finding.
- **Quantified claims name their producing command.** Any sentence that counts
  ("N files", "zero", "all", "7 of 7") includes the exact command that
  produced the number, so it is derived, not remembered.
- **Deferrals name a filed Linear issue id or say "unfiled" in the wrap-up.**
  Never write "unfiled" into a repo artifact (source, CHANGELOG, docstring) —
  artifacts reference filed ids only.
- **Mutation-sweep hygiene:** commit a baseline first; revert with
  `git restore --source=HEAD` (never `git checkout --`, which silently no-ops
  on untracked files); run with `PYTHONDONTWRITEBYTECODE=1`.
- A green CI claim names the run id; "green" is scoped to the platform it ran
  on. A CI run that failed at job start with zero steps executed is an ABSENT
  signal — report it as such, never as red or green.

## Never touch

- `main` (any push), other lanes' branches, or Linear issues you don't hold.
- The deployed integrator (`~/Documents/Tools/integrator-plugin`), installed
  `~/.agents` / `~/.claude` skill trees, and the live vault
  (`~/Clickt/vault`) — coordinator-only surfaces, never edited by lanes.
- New third-party dependencies, unless the issue explicitly authorizes them.

## This repo: HiveMind-Plugins (marketplace MIRROR — read this first)

- **Do not develop plugin content here.** This repo is a sync-mirror of
  HiveMind-Marketing-Skills (dev-canonical). Skill/plugin changes are made
  UPSTREAM and sync down. The only issues that legitimately run here are
  repo-metadata issues (LICENSE, README, manifests) that name this repo
  explicitly.
- LICENSE is PolyForm Shield 1.0.0 (ruled 2026-08-05) and is a customer
  contract surface (repo access = the license). Never change licensing
  wording without an explicit John ruling recorded on the issue (see HM-831).
