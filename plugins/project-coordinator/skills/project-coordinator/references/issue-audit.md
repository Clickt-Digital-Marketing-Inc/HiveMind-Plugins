# Auditing and grooming Linear issues

## Contents
- Audit procedure
- Defect catalog and rewrite guidance
- Grooming loop
- Reporting format

The standard every issue is held to is the four-point standalone checklist in the sibling skill's reference: `../plan-to-linear-build/references/issue-as-prompt.md`. Read it before auditing — the required body structure (Objective, Context, Task, Acceptance criteria, Notes) and the four checks come from there.

## Audit procedure

1. Identify the Linear project — resolve the name with `list_projects` / `get_project` (ask if ambiguous). Pull its issues with `list_issues`; fetch full bodies with `get_issue` — titles are not enough to audit.
2. For each issue, run the four checks:
   - **Standalone** — could a fresh agent execute it reading only this issue? Dependencies on other issues must be stated with what their output looks like.
   - **Concrete names** — files, functions, endpoints, columns named exactly. No "the config file".
   - **Decisions baked in** — no "decide whether X or Y" inside an issue. An open decision in an issue is a planning failure.
   - **Checkable done** — acceptance criteria a third party could verify objectively.
3. Run the structural checks as well — these are audit failures too, even when the four checks pass: required body structure present (Objective / Context / Task / Acceptance criteria / Notes), one-task scope (no two unrelated acceptance sections), and the issue assigned to a milestone.
4. Record pass/fail per issue with the specific failing check and the offending text quoted.

The checklist in `issue-as-prompt.md` is worded for issue *creation*; the audit applies the same standard to issues that already exist. An audit is read-only: it ends at the report and proposed rewrites. Enter the grooming loop only when the user asks for fixes or approves the proposals.

## Defect catalog and rewrite guidance

| Defect | Rewrite |
|---|---|
| Vague names ("the relevant handler", "the usual hashtags", "the promo graphics") | Locate the real name (ask the user or inspect the project folder/repo) and substitute it: `src/handlers/webhook.ts`, the approved hashtag set by name, the asset files and where they live. |
| Missing context (assumes plan-mode conversation) | Add a Context section carrying the decisions and architecture facts the executor needs; link dependency issues by ID and state what their output looks like. |
| Open decision inside the issue | Surface it to the user, get it decided now, and bake the decision into the Task. If the user can't decide yet, the issue is blocked — mark it so, don't paper over it. |
| Vibes-only acceptance ("works well", "feels fast", "looks on-brand") | Convert to objective criteria: tests pass, endpoint returns X; posts scheduled and visible in the tool; approval recorded from a named reviewer; contract signed and filed. |
| Two unrelated acceptance sections | Split into two issues, each assigned to the correct milestone. |
| Batch issue spanning a per-item spec ("write 6 pages") | Split into one issue per item, each embedding its item's full spec row; keep a batch issue only for genuinely cross-item operations (publish, QA sweep, observation). |
| Missing body structure | Restructure into Objective / Context / Task / Acceptance criteria / Notes without inventing content — gaps become questions for the user, not fabricated details. |

Never invent facts during a rewrite. Every concrete name, decision, and criterion must trace to the user, the repo, or an existing Linear artifact.

## Grooming loop

Run the validator loop until every issue passes:

1. Rewrite the failing issue body per the catalog above.
2. Re-validate against the four checks. Fix and re-check until it passes.
3. Present before/after to the user (title, what changed, why).
4. **Only on explicit approval**, write back with `save_issue`. Batch approvals are fine ("apply all") but the user must see the full set first.
5. Re-audit anything that was split or newly created.

## Reporting format

Summarize the audit as a table — issue identifier, title, pass/fail, failing check(s) — followed by the proposed rewrites. Keep quoted defects short. End with the ask: approve rewrites, decide open decisions, or both.
