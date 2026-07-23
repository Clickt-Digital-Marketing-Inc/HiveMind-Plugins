---
description: Write/update the session's HALT-STATE checkpoint in the project state file, then commit and push it
argument-hint: [optional note, e.g. "halting before gate - window rule"]
---

Write or update the orchestration checkpoint so a cold-start successor session (or you, after an interruption) can resume with zero reconstruction. Then commit and push it.

## State file

Default `tasks/todo.md` at the project root; the project CLAUDE.md may override the location — check it. Create the file (and directory) if missing, with a header noting: "Linear is the record; this file is the resume map for the next session."

## Checkpoint pattern (HALT-STATE)

Prepend a new dated entry at the top (newest first). When a new entry supersedes an older one covering the same round, mark the old entry `(superseded)` — never delete history. The entry must contain:

1. **Current phase** — where in the round lifecycle this session is (e.g. "round N: all lanes In Review → gate running", "HALT STATE: halted before the gate on the window rule"). If this is a deliberate halt, label it `⛔ HALT STATE` and include `$ARGUMENTS` as the reason.
2. **Running background work** — every live run id with exact resume instructions, e.g. `GATE RUNNING: run wf_xxxx (scriptPath launch, applyFixes true). If session dies: resume Workflow { scriptPath: <abs path>, resumeFromRunId: "wf_xxxx" }`.
3. **Per-lane status** — per issue: id, executor state (running / done → In Review / stop-and-flagged), branch @ latest commit hash, worktree path, and any lane-specific hazards (live-DB state a lane left behind, shared-file contention notes, accepted deviations).
4. **Open decisions** — everything blocked on the human lead, each as a one-liner with blast radius.
5. **Next step for a cold-start successor** — an imperative, numbered "step 1 is X" instruction precise enough to execute without reading the transcript (include absolute paths; note that session-scoped scratchpad worktrees die with the session and must be re-added at absolute paths).

Keep entries dense and factual — commit hashes, run ids, absolute paths, issue ids. The checkpoint is cheap insurance: it should be updated at **every state change**, not only at halts.

## Commit and push

Commit only the state file (never sweep unrelated dirty files into the commit): `git add <state-file> && git commit -m "Session checkpoint: <one-line summary>"` — imperative, scoped, referencing the round/issues, ending with the project's standard co-author line if one is in use. Then push the current branch. If the state file lives in a repo where you are not on the base branch, stop and flag instead of committing to the wrong branch.
