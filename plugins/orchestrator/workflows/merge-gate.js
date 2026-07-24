export const meta = {
  name: 'merge-gate',
  description: 'Merge gate: mixed-tier finders (4 Opus correctness + 4 Sonnet convention angles, chunks of 5) -> one batched Opus verifier -> optional Opus fix-applier. Project conventions and accepted deviations ride in via args.context; the script itself is project-agnostic.',
  whenToUse: 'Run before any merge to the base branch, on an integration worktree. args: { worktree, branch, base?, context, applyFixes?, resumable? }. Launch by scriptPath, not by name, if the script has been edited this session (the name registry can serve a stale snapshot). Resumability is harness-level: relaunch with resumeFromRunId.',
  phases: [
    { title: 'Find', detail: '8 review angles (4 Opus correctness + 4 Sonnet convention), <=5 concurrent (pacing rule)' },
    { title: 'Verify', detail: 'single batched verifier, one vote per deduped candidate', model: 'opus' },
    { title: 'Fix', detail: 'optional fix-applier commits to the worktree', model: 'opus' },
  ],
}

// ── args (defensive: the harness may deliver args as a JSON string) ─────────
let A = args
if (typeof A === 'string') {
  try { A = JSON.parse(A) } catch (e) { A = null }
}
A = A || {}
const wt = A.worktree
const branch = A.branch
const base = A.base || 'main'
const context = A.context || ''
const applyFixes = !!A.applyFixes
// A.resumable is accepted for arg-shape compatibility; resumption itself is a
// harness feature (relaunch the workflow with resumeFromRunId: "<wf_id>").
if (!wt || !branch) throw new Error('merge-gate requires args.worktree and args.branch (object or JSON-string args)')

const SCOPE = `Worktree: ${wt}
Review scope: \`git -C ${wt} diff ${base}...${branch}\`
Change context (from the orchestrator — includes per-lane summaries and ACCEPTED DEVIATIONS; do not re-litigate a deviation this context marks as accepted): ${context}
Repo conventions: read the CLAUDE.md at the worktree root, plus any nested CLAUDE.md governing directories the diff touches (skip missing). Those files are the authority on project-specific rules — helpers to reuse, output-escaping policy, content-integrity/sourced-claims rules (e.g. E-E-A-T), snapshot/serialization canonical forms, performance budgets. Where this prompt and a CLAUDE.md conflict on a project-specific matter, the CLAUDE.md wins.`

const CANDIDATES = {
  type: 'object',
  required: ['candidates'],
  properties: {
    candidates: {
      type: 'array',
      maxItems: 6,
      items: {
        type: 'object',
        required: ['file', 'line', 'summary', 'failure_scenario'],
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
        },
      },
    },
  },
}

const ANGLES = [
  { key: 'line-by-line', model: 'opus', prompt: `FINDER angle A - line-by-line diff scan. Read every hunk, then the enclosing function; bugs on unchanged lines of touched functions are in scope. Hunt: unescaped/unsanitized output on user- or CMS-sourced data, null/undefined/false derefs on optional lookups, falsy-zero mistakes on numeric fields, inverted/wrong conditions, off-by-one, wrong-variable copy-paste, missing subkey/index on nested data, duplicate HTML ids, second H1, aria misuse, CSS selector leaks / z-index / 100vw overflow / contrast of literal hex.` },
  { key: 'removed-behavior', model: 'opus', prompt: `FINDER angle B - removed-behavior auditor. For every line the diff deletes or replaces (including nodes removed/replaced in serialized templates or config), name the invariant it enforced and find where the new code re-establishes it. Orphaned CSS/JS selectors, dropped guards, narrowed validation, and NEW double-render/double-handling overlaps with surviving legacy code are candidates.` },
  { key: 'cross-file', model: 'opus', prompt: `FINDER angle C - cross-file tracer. For each changed function/component: callers, callees, registration lines, exact-match checks between names/handles/keys used across files (component name vs template node name vs asset handle vs config key), field/schema names verified against their source of truth, data-attribute or API contracts (who consumes them), and fallback paths (no-JS, reduced-motion, feature-disabled, empty-data).` },
  { key: 'reuse', model: 'sonnet', prompt: `FINDER angle - reuse. Flag new code re-implementing what the repo already has: shared helpers, design-system utilities, established normalization/formatting routines, near-identical logic across the new files themselves. Read the governing CLAUDE.md files for the repo's named helpers. Name the existing helper/utility to use instead.` },
  { key: 'simplification', model: 'sonnet', prompt: `FINDER angle - simplification. Flag unnecessary complexity: dead options never read, styles for markup the code cannot emit, over-clever conditionals/regexes with simpler robust forms, copy-paste blocks that should loop, redundant derivable state, settings duplicating defaults, leftover debug code. Name the simpler form.` },
  { key: 'efficiency', model: 'sonnet', prompt: `FINDER angle - efficiency. Flag wasted work: repeated identical lookups per render/request, per-row work hoistable from loops, redundant IO/parse calls, render-blocking additions, asset payload duplication, global loading of page-specific assets. Weigh against any performance budget stated in the governing CLAUDE.md files. Name the cheaper alternative.` },
  { key: 'altitude', model: 'opus', prompt: `FINDER angle - altitude. Check each change is implemented at the right depth: special cases layered on shared infrastructure, per-component copies of org-wide facts or policies, parsing presentation out of free text where structured fields exist, transient scaffolding persisted as repo truth. Prefer findings where one deeper fix removes several shallow ones.` },
  { key: 'conventions', model: 'sonnet', prompt: `FINDER angle - conventions. Read the governing CLAUDE.md files in the worktree and flag CLEAR violations only - quote the exact rule and the exact violating line (no style preferences). Include any canonical-serialization rules, no-hardcoded-facts rules, and content-integrity/E-E-A-T rules those files state.` },
]

// ── Phase 1: Find (chunks of 5 to honor the <=5-concurrent pacing rule) ────
phase('Find')
const finderResults = []
for (let i = 0; i < ANGLES.length; i += 5) {
  const chunk = ANGLES.slice(i, i + 5)
  const res = await parallel(chunk.map((a) => () =>
    agent(
      `You are a code-review FINDER. ${a.prompt}

${SCOPE}

Return up to 6 candidate findings. Every candidate needs a nameable, concrete failure scenario (inputs/state -> wrong output, or the concrete maintenance/perf cost for cleanup angles). Pass every such candidate through - do not self-censor; the verify phase filters.`,
      { model: a.model, label: `find:${a.key}:${a.model}`, phase: 'Find', schema: CANDIDATES }
    )
  ))
  finderResults.push(...res)
}
const candidates = finderResults.filter(Boolean).flatMap((r) => r.candidates || [])
log(`${candidates.length} raw candidates from ${finderResults.filter(Boolean).length}/8 angles`)

if (!candidates.length) return { findings: [], fix: null, note: 'no candidates surfaced' }

// ── Phase 2: Verify (ONE batched verifier: dedup + one vote per candidate) ──
phase('Verify')
const VERDICTS = {
  type: 'object',
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      maxItems: 10,
      items: {
        type: 'object',
        required: ['file', 'line', 'summary', 'failure_scenario', 'verdict'],
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
          verdict: { type: 'string', enum: ['CONFIRMED', 'PLAUSIBLE'] },
          fix_hint: { type: 'string' },
        },
      },
    },
    refuted: { type: 'array', items: { type: 'string' } },
  },
}
const verified = await agent(
  `You are a code-review VERIFIER. ${SCOPE}

Candidates (from 8 independent finder angles; near-duplicates expected):
${JSON.stringify(candidates, null, 2)}

1) Dedup near-duplicates (same defect, same location -> keep one, note convergence in its summary).
2) For each deduped candidate return exactly one verdict. Recall-biased: PLAUSIBLE by default for realistic states; REFUTED only when constructible from the code (quote the actual line, show the invariant, or cite an in-diff guard). Keep CONFIRMED and PLAUSIBLE; list refuted ones as one-line strings in 'refuted'.
3) Rank most-severe first, cap at 10 (correctness outranks cleanup). Add a one-line fix_hint per finding.`,
  { model: 'opus', label: 'verify:batched', phase: 'Verify', schema: VERDICTS }
)
const findings = (verified && verified.findings) || []
log(`${findings.length} findings survived; ${(verified && verified.refuted || []).length} refuted`)

// ── Phase 3: Fix (optional; commits to the worktree) ───────────────────────
let fix = null
if (applyFixes && findings.length) {
  phase('Fix')
  fix = await agent(
    `You are the merge-gate FIX-APPLIER. ${SCOPE}

Apply these verified findings directly in the worktree at ${wt} (branch ${branch} is checked out there):
${JSON.stringify(findings, null, 2)}

Rules: fix correctness bugs and cleanups alike; SKIP any finding whose fix would change intended behavior, require work well outside the diff, or that you judge a false positive - record the skip with a reason instead of arguing. Preserve file line endings (some repos carry CRLF files - edit lines, never rewrite whole files through text-mode scripts). Lint/syntax-check every touched file using the command the governing CLAUDE.md documents for its language (skip silently if none is documented). If a fix touches a serialized snapshot or export artifact that a database or external state must be re-synced from, note that the orchestrator must run the project's import/re-export step (do NOT touch databases or live state yourself). Commit all fixes in the worktree as one commit: imperative message referencing the issues, ending with the line: Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>. Do not push, do not merge, never touch the primary checkout (the live tree stays on ${base}).

Final message: compact report - fixed (per finding, one line), skipped (with reasons), commit hash, git diff --stat of your commit, and any artifacts needing an orchestrator-side import/re-sync step.`,
    { model: 'opus', label: 'fix:apply', phase: 'Fix' }
  )
}

return { findings, fix }
