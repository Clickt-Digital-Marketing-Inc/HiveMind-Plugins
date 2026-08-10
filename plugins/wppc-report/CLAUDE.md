# CLAUDE.md — wPPC — Weighted Profit-Per-Click Plugin

Guidance for executing this project. It is planned in Linear; this file keeps every session on-rails.

- **Project:** wPPC — Weighted Profit-Per-Click Plugin
- **Domain:** software
- **Tools & channels:** Python (`pandas`, `click`, `pyyaml`, `openpyxl`, `vl-convert-python`); Claude Code plugin packaging (`.claude-plugin/plugin.json`, root `marketplace.json`); vendored runtimes (GSAP, Vega-Lite); GitHub (`Clickt-Digital-Marketing-Inc`); Polar (product + GitHub Repository Access benefit).
- **Linear team / project:** Clickt / [wPPC — Weighted Profit-Per-Click Plugin](https://linear.app/clickt/project/wppc-weighted-profit-per-click-plugin-41704dc00415)
- **Milestones (integration checkpoints):** M1 Methodology & metadata → M2 HTML-first output & charts → M3 White-label, tests & packaging → M4 Go-to-sale (+ Fast-follows backlog)
- **Lessons Log:** the Linear document named "Lessons Log" on this project
- **Plan of record:** `docs/wppc-plugin-plan.md`; overview + execution order also live in the Linear "Build Plan & Execution Order" document.

## Session start

Before pulling an issue:

1. Read the project's **Lessons Log** document in Linear and apply any relevant entries.
2. Pull the next issue from the project and read it in full — it contains everything needed to execute that task. Respect `blockedBy` and the priority ladder (see the "Build Plan & Execution Order" document).

## Linear is the source of truth

Every unit of work is a Linear issue, and each issue is written to be executed as a standalone prompt.

- **Execute only what the issue specifies.** If the issue is missing context or contains an unresolved decision, stop and flag it rather than improvising.
- **Update issue status** as you move: in-progress when you start, done only when acceptance criteria are proven and `/reflexion:reflect` has run (see below).
- **Never work off-Linear.** New work discovered mid-flight becomes a new issue, not silent scope expansion.

## Linear sync at issue boundaries

Exactly two comments per issue:

- **On starting**: post the todo plan as a comment — checkable items for what you're about to do.
- **On completing**: post one wrap-up comment: what changed, verification evidence (tests pass / CLI run output / self-containment check), deviations from the plan, and the reflect verdict. Then update the issue status.
- **No per-item progress comments.** The oversight value is in plan and outcome, not noise. (Status transitions and Lessons Log appends are separate normal actions.)
- If a Linear write fails, don't block the work: note it and fold the missed update into the completion comment or the next session.

Track the plan locally as checkable items (`tasks/todo.md` or your todo tool) while you work; the Linear comments are the record. Reset `tasks/todo.md` per issue.

## Lessons Log

The project's Linear document "Lessons Log" is the single canonical store of lessons. There is no local lessons file.

- **After any correction from the user** (or a review pass that surfaces a repeatable mistake): append one line to the document **immediately**, before resuming — format: `pattern → rule that prevents it (issue ID)`.
- If the append fails, record the lesson in the issue's completion comment and append it at the next session start.

## Reflexion at the end of every issue

Before marking any issue done, run:

```
/reflexion:reflect
```

- **Let the skill triage, never pre-triage.** Do not decide "this issue is trivial, skipping reflect" — invoke it and let its own complexity triage route trivial changes to its quick path.
- **Record the verdict** in the completion comment: path taken, confidence, any issues found and fixed.
- An issue is not done until reflect passes and acceptance criteria are proven.

## Milestone integration check

At each milestone boundary — M1 → M2 → M3 → M4 — before starting the next milestone's issues:

1. Run the milestone verification — **the full test suite (`pytest -q`)** — across the whole milestone, not just the last issue.
2. **Re-read every issue in the milestone** and verify its acceptance criteria still hold in the assembled state — don't trust "done" status alone.
3. **Read the Lessons Log and the milestone's completion comments** for unresolved flags. Resolve mechanical items yourself; for judgment calls, file a follow-up issue. If a completion comment is missing its verification evidence or reflect verdict, flag it in the summary — don't backfill it.
4. **Post a milestone summary comment** on the project recording verification results and how each flag was handled.

## Plan mode + verification gates

- **Plan first.** For any non-trivial task (3+ steps or a structural decision), enter plan mode before executing. If something goes sideways mid-execution, stop and re-plan.
- **Verification before done.** Never mark an issue complete without proving it works: `pytest -q` green, the CLI run produces the expected artifacts, the HTML is self-contained (no network calls). Ask: "would a senior practitioner approve this?"
- **Autonomous fixing.** Given a failing check, fix it — point at the evidence and resolve it rather than asking for hand-holding.

## Project-specific hard rules

These are load-bearing constraints from the plan; every issue inherits them.

- **Additive & default-off.** New behavior is inert unless explicitly invoked. The existing **19 fixtures must stay green** (`pytest -q`) after every change. Pinned values that must not move: `wPPC_A=4.08`, `wPPC_B=2.59`, `K_FALLBACK=250.0`, `attrs["baseline"|"k"|"replacement"]` semantics, `stabilized == (clicks>=k)`.
- **No hardcoded methodology numbers** in `wppc/score.py` / `wppc/weights.py` logic — tolerances, percentiles, and bands live in config or CLI defaults.
- **Determinism is sacred.** Python computes every number; HTML/md are templates filled from one model (`wppc/model.py`). No LLM in the numeric loop. The `generated` timestamp is injectable so renders are byte-reproducible.
- **Self-contained output.** No `http(s)://`, `<link`, `src=`, or `cdn` in the HTML outside the checksummed vendored blobs.
- **White-label output.** Reports lead with the client's account/segment data — Clickt colors only, no logo, no third-party names in output. `Clickt Digital Marketing Inc.` appears only in `plugin.json` author + `.py` copyright headers, never in an emitted artifact.
- **Incrementality is a separate product.** wPPC ships only the non-functional `--incrementality` seam + the Layer-5 contract doc (CLI-401). Do not implement the multiplier in v1; the consumer (CLI-408) is blocked on the separate Incrementality plugin's locked Read-out contract.

## Core principles

- **Simplicity first.** The smallest change that works.
- **No laziness.** Root causes, not band-aids. Senior-practitioner standards.
- **Minimal impact.** Touch only what's necessary. Don't introduce defects.
