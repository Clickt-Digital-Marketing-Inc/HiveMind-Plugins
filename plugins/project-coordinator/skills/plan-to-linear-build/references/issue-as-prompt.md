# Writing a Linear issue as a standalone execution prompt

The reader of each issue is an agent starting with **zero context** beyond what the issue contains. It cannot see the plan-mode conversation, the other issues, or your reasoning. Everything it needs to execute correctly must be in the issue body.

## Required structure for each issue body

```markdown
## Objective
One sentence: what this task accomplishes and why it matters to the project.

## Context
The minimum background the agent needs — relevant files/paths, documents, or assets,
the piece of the architecture or plan this touches, decisions already made in plan mode
that constrain the work. Link related issues by ID if a dependency exists.

## Task
The concrete work, as imperative steps. Specific enough to execute without guessing.
Name the artifacts exactly — files, endpoints, documents, channels, assets, vendors —
not "the relevant handler" or "the usual hashtags" but the actual name.

## Acceptance criteria
Checkable conditions that prove the task is done. Prefer objective/verifiable ones —
tests pass, endpoint returns X; posts scheduled and visible in the tool; approval recorded
from a named reviewer (see the domain examples below). This is what "verification before done" checks against.

## Notes
Gotchas, constraints, things to avoid. Optional.
```

## What makes an issue standalone (checklist)

Every issue must pass all four checks before it is created in Linear:

- Could a fresh agent execute this reading *only this issue*? If it needs another issue's output, state the dependency and what that output looks like.
- Are all names concrete? No "the config file" — say `config/app.ts`; no "the promo graphics" — name the assets and where they live.
- Are the decisions baked in? Don't defer architectural choices into the issue ("decide whether to use X or Y") — those get resolved in plan mode. An issue that contains an open decision is a planning failure.
- Is "done" objectively checkable? If acceptance is vibes-only, tighten it.

## Domain examples

The same four checks apply to every discipline. What "concrete" and "checkable" look like per domain:

| Domain | Concrete names | Objectively checkable done |
|---|---|---|
| Software | `config/app.ts`, `POST /api/orders`, the `users.email` column | tests pass, endpoint returns 201, build succeeds |
| Content | the outline doc by link, the target keyword, the named reviewer | draft at [link] approved by [reviewer]; piece live at [URL] with title/meta set |
| Social | platform + handle, the approved hashtag set, the asset folder by path | all N posts scheduled in [tool] and visible on the calendar; approval recorded from [name] |
| Event | venue by name, vendor + contact, the run-of-show doc | contract signed and filed at [location]; headcount confirmed in writing; run-of-show approved by [owner] |

## Scope

One issue = one discrete task — small enough to execute in a single focused sitting. If an issue has two unrelated acceptance sections, split it. When the work iterates over a per-item spec (page map rows, calendar slots, vendor list entries), one issue per item, each carrying its item's full spec — batch issues are only for operations that genuinely span items (publish, QA, observation). Assign every issue to a milestone so the integration checkpoints stay meaningful.
