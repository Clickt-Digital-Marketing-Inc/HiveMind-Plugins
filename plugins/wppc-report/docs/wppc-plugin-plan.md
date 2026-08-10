# wPPC — v1 Packaging & Improvements

## Context

wPPC (Weighted Profit-Per-Click) is a deterministic, sabermetric linear-weights scoring tool for Google & Meta Ads segment exports. It is code-complete (v1.0.0, 19/19 tests) but today it is a standalone, non-git folder at `~/Documents/Code HiveMind Development/wppc-report` with **xlsx-only** output. We are taking it to sale **in the same manner** as the audit plugins established in the "Skill bundles status report" session: an isolated private repo under `Clickt-Digital-Marketing-Inc`, sold via a one-time Polar product gated by a GitHub Repository Access benefit.

Before packaging, we implement a set of agreed methodology/honesty improvements and replace the xlsx-only output with the suite-standard **HTML-first 3-format bundle** (md + interactive HTML + xlsx backup). **Incrementality ships as its own separate plugin/product** (its own Linear track); wPPC carries only a documented, non-functional seam for it so the fast-follow has a planned interface.

Linear project (already created): **wPPC — Weighted Profit-Per-Click Plugin** (Clickt team) — https://linear.app/clickt/project/wppc-weighted-profit-per-click-plugin-41704dc00415

### Locked decisions (2026-07-12)
1. **W4 decay/fatigue** → include the trimmed **2-export delta** (current + prior period), kept separate from the point-in-time score. Full decay-curve deferred to a fast-follow.
2. **Incrementality (Layer 5)** → ship a **documented, non-functional `--incrementality` CLI slot** only; the consumer is built when the Incrementality plugin's output contract is locked.
3. **Charts** → **vendor Vega-Lite** into the plugin (reporting-style), not hand-authored SVG.

### Guiding constraints (from the eval brief + suite conventions)
- **Additive & default-off.** All new behavior is inert unless explicitly invoked, so the 19 fixtures stay green untouched.
- **No hardcoded methodology numbers** in `score.py`/`weights.py` library logic — tolerances/percentiles live in config or CLI defaults.
- **Determinism is sacred.** Python computes every number; HTML/md are templates filled from one model. No LLM in the numeric loop.
- **Self-contained output.** No `http(s)://`, `<link`, `src=`, or `cdn` outside the checksummed vendored runtime blobs.
- **White-label.** Clickt colors only, no logo, no third-party names in output.

---

## Scope: what we build in v1

### A. Methodology / honesty improvements

**W2 — k honesty (cheapest).** `estimate_k` already computes `k` and logs its fallback. Add a keyword-only `return_provenance: bool = False` to `estimate_k` (score.py:95) returning `(k, method)` where `method ∈ {"estimated","fallback"}`. In `score()` (score.py:55) call it with provenance and stash:
- `out.attrs["k_source"]`, `out.attrs["n_segments"]`, `out.attrs["n_stabilized"]`.
Zero change to the returned `k` value or columns → all `attrs["k"]`-reading tests stay green.

**W1 — weight-drift detection (also the shared substrate).**
- Serialize the immutable weight-table inputs as a JSON snapshot: `{timestamp, platform, cm3_order, repeat_rate, cm3_repeat, p_vector, telescope_sum}` from the `Weights` object. Written to a tool-owned sidecar `<stem>.weights.json` next to the outputs every run (describes *this* run; deterministic).
- New CLI `--weights-baseline <path>`: when supplied and existing, compare each input component vs the stored snapshot; flag any that moved beyond tolerance. Tolerance is **not** hardcoded in `score.py` — a `--drift-tolerance` CLI option (default `0.15`), overridable per-mapping via an optional `currency.drift_tolerance` key.
- Drift results (which input moved, by how much, pass/flag) go into the run-metadata block. Never auto-mutates the baseline — comparison is explicit.

**W4 — 2-export decay delta.** New CLI `--prior-input <path>`: load the prior-period CSV through the **same** `load_segments(mapping, platform)` (io.py is already pure and reusable — no schema change), run `score()` on it, join on `segment_id`, and compute per-segment `wPPC+_prior`, `wPPC+_delta`, `delta_pct`, and a `trend ∈ {Rising, Flat, Falling}` flag (thresholds config-driven, default ±5pts). Surfaced as **appended** columns (Report tab col 10+, so chart/CF ranges are untouched) and a decay panel in HTML/md. Kept strictly separate from the point-in-time wPPC+ (never blended). Provenance: `decay: computed | not-run`.

**Layer-5 seam — non-functional `--incrementality <path>`.** Add the option and an optional keyword `incrementality: dict | None = None` to `score()` defaulting to `None` = identity. In v1 the file is **loaded, shape-validated, and recorded in metadata as "provided, not applied (v1)"** — the multiplier is not applied. Document the intended contract in a reference doc + SKILL.md so the fast-follow issue has a locked interface:
- IM table per tier/group: `{value, ci, power, tier, window, timestamp}`.
- `weight_causal = weight_attributed × IM_applied`, applied to the numerator **before** shrinkage (insertion point: score.py between line 42 and 44).
- Confidence banding `IM_applied = IM×cw + 1.0×(1−cw)`; staleness > ~90d → `IM_applied → 1.0`.

**Run-metadata block (connective tissue).** A single JSON-serializable object carrying: `baseline`, `replacement`, `k`, `k_source`, `n_segments`, `n_stabilized`, `self_check_pass`, `telescope_sum`, `weights_version` + `drift` flags, `decay` status, `incrementality` status, `generated` (ISO timestamp), `platform`. Assembled in a new `wppc/model.py` and surfaced first-class in all three outputs.

### B. HTML-first 3-format output

Introduce a single source of truth and three renderers, mirroring `plugins/google-ads-audit/skills/google-ads-audit/scripts/audit_model.py` + `audit_html.py` + `audit_md.py`:

- **`wppc/model.py`** — `build_model(results_df, weights, run_meta, decay=None) -> dict`: one JSON-serializable model `{provenance, metadata, segments[], weights_table, self_check, decision_lens, decay, charts}`. All renderers read only this.
- **`wppc/render_md.py`** — Obsidian-ready markdown record: frontmatter (run-metadata) + segments table + weights/self-check + decay table. Static chart SVGs via vl-convert. LLM-readable vault format.
- **`wppc/render_html.py`** — self-contained interactive HTML (primary deliverable), combining the audit-style shell with the reporting-style Vega charts:
  - GSAP motion (vendored `gsap.min.js`, sentinel-wrapped, strippable via `animate=False`) — mirror `audit_html.py:gsap_blob()`.
  - `<script id="data" type="application/json">` model block + a client IIFE that renders a **sortable/filterable segments table** (filter by stabilized Y/N, MAR sign, wPPC+ band; search by segment_id; same conditional coloring as the xlsx), a **decision lens** (Scale / Cut / Watch chips derived deterministically from MAR + stabilized), the weights/self-check panel, and the run-metadata header.
  - Four **Vega-Lite** charts via the vendored runtime inlined between checksum sentinels: MAR by segment, wPPC+ by segment, derived weights w(S), closing-ratio vs wPPC scatter.
- **`wppc/report.py` (xlsx backup)** — keep the existing 3-tab workbook. Additive only: append decay columns to the **right** of `REPORT_COLUMNS` (preserves chart `Reference`/CF ranges), and add a new **4th "Run" tab** for the run-metadata block (zero risk to existing tabs). openpyxl stays the only xlsx dep.

**Vega vendoring** — copy the reporting-style chart layer in-tree (isolation pattern; each consumer copies its own vendor tree):
- New `wppc/charts.py` mirroring `plugins/google-ads-management/_shared/render/charts.py`: the declarative `spec["charts"] = [{id, title, mark, encoding, transform, width, height, md, widget}]` contract, `build_vl_spec`, `render_chart_svg` (lazy `vl_convert`), `vendor_blob()`, and a copied frozen `CLICKT_THEME` (teal `#1f7a82` etc.).
- New `wppc/vendor/`: `vega.min.js` (5.30.0), `vega-lite.min.js` (5.20.1), `embed_shim.js`, `gsap.min.js` (3.12.5), `SHA256SUMS`, `VERSIONS.md` — copied byte-identical from the existing vendored trees.
- Pin `vl-convert-python==1.7.0` in `requirements.txt` (matches suite; version-lock contract with `vega-lite.min.js` major.minor 5.20).

**CLI evolution (`wppc/cli.py`).** Move the `report` command from `--output <xlsx>` to the audit-style **`--outdir`** where the tool owns filenames (`wppc_{platform}_{slug}_{date}.{md,html,xlsx,weights.json}`) and emits all three formats; add `--no-animate`, `--weights-baseline`, `--drift-tolerance`, `--prior-input`, `--incrementality`, and a `--formats md,html,xlsx` selector (default all). Keep the existing `--output` as an accepted alias mapping to xlsx-only for back-compat. Final stdout line is machine-readable JSON `{"md":...,"html":...,"xlsx":...,"weights":...,"baseline":...,"k":...,"k_source":...,"outdir":...}` (mirrors `build_audit.py`). No CLI tests exist, so this is test-safe.

### C. White-label scrub
- Remove the "Clickt |" brand string from `sample_data/google_segments.sample.csv` preamble and the internal path/brand comments in `config/mapping.clickt-searchterms.yaml` (keep the mapping, genericize the comments) — or drop the client mapping from the shipped bundle.
- Keep `Clickt Digital Marketing Inc.` only in `plugin.json` author / source copyright headers (never emitted into output). HTML/md/xlsx lead with the account/segment data, no logo, no credit — mirror `audit_html.py`'s white-label guarantee.
- No other third-party names exist in the repo (confirmed: no Optmyzr / PPC personalities / FanGraphs, etc.). Sabermetric terms (wOBA/WAR) stay.

### D. Determinism / self-containment tests
Add a `tests/test_render.py` mirroring `plugins/google-ads-audit/.../tests/test_audit.py`:
- Self-containment regex `r"https?://|<link|src=|cdn"` on the HTML minus the vendored blobs.
- Vendored-file SHA-256 parity vs `SHA256SUMS`; `animate=False` carries zero GSAP bytes.
- HTML/md byte-identical modulo the `generated` timestamp (determinism).
- Model → all-three-formats agreement (no format re-derives numbers).

### E. Packaging / go-to-sale (same manner)
1. **Bring wPPC into the canonical marketplace repo** as `plugins/wppc-report/` in `HiveMind-Marketing-Skills` (this working dir): plugin layout with `.claude-plugin/plugin.json` (update existing), `requirements.txt` (pandas, pyyaml, click, openpyxl, vl-convert-python==1.7.0), `pyproject.toml`, `wppc/` package, `config/`, `sample_data/`, `tests/`, and `skills/wppc-report/SKILL.md` (rewrite for 3-format output + output-dir behavior + white-label). Drop the committed `.venv`. Register in root `.claude-plugin/marketplace.json`.
2. **Isolate** to a new private repo `Clickt-Digital-Marketing-Inc/wPPC` (fully standalone; builds from inside the copy), following the Google-Ads-Audit precedent. Parent stays canonical; rsync-sync on each merge with a commit citing the parent PR.
3. **Polar**: create one-time product **"HiveMind | wPPC"** (proposed price $99.97 one-time USD, to match Google Ads Audit — confirm at execution) with a **GitHub Repository Access benefit** pointing at the isolated repo, role Read. Create checkout link. This is the gate (buy → auto-invite; cancel → auto-revoke). No runtime license code (the suite's license gate is a deliberate no-op).

---

## Critical files

**Modify (additive):**
- `wppc/score.py` — `estimate_k` provenance return; `score()` stashes `k_source`/`n_segments`/`n_stabilized`; default-off `incrementality=None` identity hook before shrinkage.
- `wppc/cli.py` — new options + `--outdir` orchestration of the 3-format emit + weights snapshot/baseline compare + prior-input decay + machine-readable stdout.
- `wppc/report.py` — append decay columns (right of `REPORT_COLUMNS`), add 4th "Run" tab.
- `wppc/weights.py` — no logic change; snapshot serialization reads the existing `Weights` fields.
- `skills/wppc-report/SKILL.md`, `README.md`, `.claude-plugin/plugin.json`, `pyproject.toml`/`requirements.txt`.
- `sample_data/google_segments.sample.csv`, `config/mapping.clickt-searchterms.yaml` — white-label scrub.

**New:**
- `wppc/model.py`, `wppc/render_html.py`, `wppc/render_md.py`, `wppc/charts.py`
- `wppc/vendor/{vega.min.js, vega-lite.min.js, embed_shim.js, gsap.min.js, SHA256SUMS, VERSIONS.md}`
- `wppc/references/incrementality-seam.md` (Layer-5 contract for the fast-follow)
- `tests/test_render.py`, plus decay/drift/k-provenance unit tests

**Reuse (copy patterns from, do not import across repos):**
- `plugins/google-ads-audit/skills/google-ads-audit/scripts/{audit_model.py, audit_html.py, audit_md.py, build_audit.py}`
- `plugins/google-ads-management/_shared/render/{charts.py, html.py, vendor/*}`
- `plugins/google-ads-audit/skills/google-ads-audit/tests/test_audit.py`

---

## Linear issues to create (on approval) in the wPPC project

**v1 build (parent-ordered):**
1. `[wPPC] Run-metadata block + W2 k-honesty (k_source, provenance attrs)`
2. `[wPPC] W1 weight-drift detection (snapshot sidecar + --weights-baseline + tolerance)`
3. `[wPPC] W4 2-export decay delta (--prior-input, trend flag, separate panel)`
4. `[wPPC] Non-functional --incrementality seam + Layer-5 contract doc`
5. `[wPPC] Vendor Vega-Lite chart layer (wppc/charts.py + vendor tree + vl-convert pin)`
6. `[wPPC] HTML-first 3-format output (model.py + render_html + render_md + xlsx Run tab)`
7. `[wPPC] CLI: --outdir orchestration + machine-readable stdout`
8. `[wPPC] White-label scrub (sample data / client mapping) + determinism/self-containment tests`
9. `[wPPC] Package as plugin + register in marketplace.json`
10. `[wPPC] Isolate to private Clickt repo + Polar product "HiveMind | wPPC" + GitHub-access gate`

**Fast-follows (backlog):**
- `[wPPC] Incrementality Layer-5 consumer (implement against locked Read-out contract)`
- `[wPPC] W4 full decay curve (multi-period slope / half-life)`
- `[wPPC] W1 baseline lifecycle (bless / auto-update workflow)`

---

## Verification

- **Fixtures:** `pytest -q` → 19/19 still green after each additive change (proves default-off).
- **New unit tests:** k-provenance (`k_source` correct for estimated vs single-segment fallback), drift flag fires at >tolerance and is silent within, decay `trend` classification on a synthetic 2-export pair, `--incrementality` records "not applied" and leaves scores identical to the no-flag run.
- **Render tests:** `test_render.py` self-containment regex + vendored SHA-256 + `animate=False` zero-GSAP + determinism (byte-identical modulo timestamp).
- **End-to-end:** run the CLI on the bundled samples →
  `python -m wppc.cli report --platform google --input sample_data/google_segments.sample.csv --mapping config/mapping.google.sample.yaml --outdir <tmp>` → confirm md + HTML + xlsx + weights.json land, open the HTML in a browser (or preview) and verify the sortable table, decision lens, four Vega charts, and GSAP motion render with no network calls (check the network panel is empty); re-run with `--prior-input` and `--weights-baseline` to confirm the decay panel and drift flags appear; re-run with `--incrementality` and diff the scores against the base run (must be identical).
- **Packaging:** from inside the isolated repo copy, `pip install -r requirements.txt && pytest -q` passes with zero parent-repo dependency; `/plugin marketplace add` smoke on the private repo.

---

## Linear population structure (for approval before any write)

Target: existing project **wPPC — Weighted Profit-Per-Click Plugin** (Clickt team, id `63d13bde-…`). 4 milestones + a Fast-follows backlog; 10 v1 issues + 3 backlog issues; each body written as a standalone prompt (Objective / Context / Task / Acceptance criteria / Notes) with concrete paths, the "19/19 tests stay green; additive & default-off" rule, and the self-containment/determinism/white-label constraints baked in.

**M1 — Methodology & metadata**
| # | Issue | Priority | blockedBy |
|---|---|---|---|
| 1 | Run-metadata block + W2 k-honesty (`k_source`, provenance attrs) | Urgent | — |
| 2 | W1 weight-drift detection (snapshot sidecar + `--weights-baseline` + tolerance) | High | 1 |
| 3 | W4 2-export decay delta (`--prior-input`, trend flag, separate panel) | High | 1 |
| 4 | Non-functional `--incrementality` seam + Layer-5 contract doc | Medium | 1 |

**M2 — HTML-first output & charts**
| # | Issue | Priority | blockedBy |
|---|---|---|---|
| 5 | Vendor Vega-Lite chart layer (`wppc/charts.py` + vendor tree + `vl-convert` pin) | High | — (parallelizable with M1) |
| 6 | HTML-first 3-format output (`model.py` + `render_html` + `render_md` + xlsx Run tab) | High | 1, 5 |
| 7 | CLI `--outdir` orchestration + machine-readable stdout | Medium | 6 |

**M3 — White-label, tests & packaging**
| # | Issue | Priority | blockedBy |
|---|---|---|---|
| 8 | White-label scrub + determinism/self-containment tests (`test_render.py`) | High | 7 |
| 9 | Package as plugin + register in `marketplace.json` | Medium | 8 |

**M4 — Go-to-sale**
| # | Issue | Priority | blockedBy |
|---|---|---|---|
| 10 | Isolate to private Clickt repo + Polar product "HiveMind \| wPPC" + GitHub-access gate | High (Ops) | 9 |

**Fast-follows (no milestone)**
| # | Issue | Priority | blockedBy |
|---|---|---|---|
| 11 | Incrementality Layer-5 consumer (implement against locked Read-out contract) | Low | 4; external Incrementality plugin contract |
| 12 | W4 full decay curve (multi-period slope / half-life) | Low | 3 |
| 13 | W1 baseline lifecycle (bless / auto-update workflow) | Low | 2 |

**Labels:** `phase:methodology`, `phase:output`, `phase:packaging`, `phase:sale`, `fast-follow`, `ops` (on #10).

**Recommended execution order (tie-break rules, appended to project description):**
1. Milestone order M1 → M2 → M3 → M4; fast-follows only after v1 (M1–M4) ships.
2. Within a milestone, higher priority first; respect `blockedBy`.
3. #5 (vendor Vega) may be pulled forward in parallel with M1 — it has no dependency.
4. #11 stays blocked until the separate Incrementality plugin's Read-out output contract is locked.

**Also created:** the project "Lessons Log" document; governance files under `plugins/wppc-report/` (`CLAUDE.md`, `docs/PROJECT.md`, `docs/wppc-plugin-plan.md` = unedited copy of this plan, `tasks/todo.md`). No `CLAUDE.md` at the shared repo root.
