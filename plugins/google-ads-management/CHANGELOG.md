# Changelog

All notable changes to the `google-ads-management` plugin.

## Unreleased

### Added
- **`sample-liveness.json` — a shipped liveness-matrix fixture for
  `google-ads-performance-reporting` and `google-ads-budget-pacing` (HM-799).** Both skills'
  `test_liveness_gating` previously built their bands from an inline dict, so the matrix
  existed only inside a test body and nothing downstream could reuse it. The matrix now lives
  in each skill's `tests/sample-liveness.json`, `test_liveness_gating` loads it through
  `core.load_findings`, and the `hivemind-directives` half of HM-799 carries its own copy of the
  fixture to generate the `model_liveness` golden case. "Copy" is literal: two physical files, and
  nothing in this repo checks that they stay in sync — `grep -rn 'sample-liveness' . --exclude-dir=.git`
  returns only these CHANGELOG lines, the two test modules' `LIVENESS_FIXTURE` constants and the
  two SKILL.md inventories; no checksum, no generator, no sync test. Treat the fixture as a
  cross-repo contract and change both sides together, prose included: an edit inside its
  `_comment` moves the file's sha while producing zero signal in either suite shape here.
  Coverage gained over the inline
  dicts: perf's **third** `_liveness_note` return path ("Spent only in the prior window"),
  which no test in either repo exercised; pacing's **enabled-but-idle** recently_active band;
  and, in both, a recently_active / dormant contrast pair differing in exactly ONE input field
  (`status` / `campaign_status`) where the recently_active twin carries every value the dormant
  gate suppresses on its twin. Perf has ONE gate (`annotate_anomalies`), so deleting it makes the
  twins equal and the suite red. Pacing has THREE independent gates (`classify_row`, the
  pace-ratio gate, the pace-flag gate); each is pinned SEPARATELY, no single deletion reproduces
  the twin, and the fixture's `_comment` records the per-gate outcome. Widening any of them past
  dormant strips the recently_active twin's findings. All note strings **in these two
  skills** are now asserted **verbatim** rather than by substring, so two of their branches cannot
  swap and stay green; `grep -rn liveness_note skills/*/tests/*.py` shows three other skills
  (`google-ads-bidding-strategy`, `google-ads-account-health`, `google-ads-conversions-tracking`)
  still asserting their notes by substring. Kept out
  of `sample-findings.json` deliberately: perf's `revenue/spend` there is `23100/5600 = 4.125`
  exactly — the half-up rounding **boundary** `test_fixture_buckets` asserts on (`4.13`, where
  `round()` gives `4.12`) — and the recently_active "paused mid-window" band requires spend
  > 0, so adding it there would have moved the fixture off that boundary and silently deleted
  an existing check. No `scripts/` file was touched. Verification, **macOS local** (this repo has
  no GitHub Actions, so there is no CI run to cite): the standalone runners are green —
  `cd tests && python3 -B test_perf.py` and `python3 -B test_budget.py`, both exit 0. The pytest
  shape `uv run --no-project --with pytest --with openpyxl pytest
  skills/google-ads-performance-reporting skills/google-ads-budget-pacing _shared -q` reports
  `4 failed, 54 passed` — byte-identical to the same command run against `origin/main`, i.e. all
  four are pre-existing and environment-caused (`vl-convert-python` is not installed here), none
  in `test_liveness_gating`.
- **A plugin-root `conftest.py` binds the `check()` accumulator to pytest for every skill
  (HM-799 merge gate — the per-skill half of the HM-791 fix below).** Every test module in this
  plugin keeps the script shape: `check(name, cond, detail)` prints and appends to a module-level
  `_failures`, and only each file's `main()` — the standalone `python3 tests/test_X.py` runner —
  ever inspects it. HM-791 bound that accumulator to pytest for `_shared/tests/` via
  `_shared/conftest.py`, but `_shared/` is a **sibling** of `skills/`, so no skill's tests were
  covered and HM-799's new `test_liveness_gating` coverage was vacuous under pytest. Measured on
  this branch before the fix, with
  `... pytest skills/google-ads-performance-reporting skills/google-ads-budget-pacing _shared -q`:
  deleting perf's dormant gate outright (`perf_core.py`'s
  `rr["flags"] = [] if rr.get("liveness") == "dormant" else f` -> `rr["flags"] = f`) left the run
  at `4 failed, 54 passed` — byte-identical to the unmutated baseline — while the standalone
  runner exited 1 with `FAILED (3)`. The new `plugins/google-ads-management/conftest.py` sits one
  level above BOTH `_shared/` and every `skills/<skill>/tests/` tree, so deleting a skill (or a
  `tests/` directory) cannot delete its guard and a skill added by a later kernel port is covered
  by construction; it adds the same order-, selection- and xdist-independent autouse per-test
  delta fixture, deliberately sharing the `_shared` fixture's name so the more specific definition
  still wins under `_shared/`. With it, the same mutation reports `4 failed, 54 passed, 1 error`
  with the error attributed to `test_perf.py::test_liveness_gating`; perturbing the liveness
  fixture, and deleting pacing's `classify_row` gate, each behave the same way. Whole-plugin
  effect, `uv run --no-project --with pytest --with openpyxl pytest .
  --ignore=skills/google-ads-products/tests -q`: `32 failed, 145 passed` before, `32 failed,
  145 passed, 4 errors` after — the 4 are tests in three untouched skills
  (`google-ads-account-health` x2, `google-ads-audience-targeting`,
  `google-ads-pmax-listing-groups`) whose accumulated `check()` failures pytest had been
  reporting as passes; all four are shape-dependent (those skills' standalone runners exit 0).
  They are pre-existing defects this conftest makes VISIBLE, not regressions introduced here,
  and they are tracked as **HM-803**; they must not block this fix.
  No `check()` line and no `scripts/` file was touched, and no standalone runner changed.
  The `scripts/` encoding exposure this gate deliberately did not fix is tracked as **HM-804**.
- **`_shared/tests/{test_analytics,test_csv_input,test_data_guards}.py` collect and run for
  real under pytest (HM-791; false-green class fixed downstream by HM-726/R16 in
  hivemind-directives).** These files use the check()-accumulator pattern with a standalone
  `__main__` runner: `check(name, cond)` only appends to a module `_failures` list and never
  asserts. Under bare pytest `test_analytics.py` had zero `test_*` functions and collected 0
  items; `test_csv_input.py`/`test_data_guards.py` collected real items that passed
  unconditionally regardless of `check()` outcome. Harmless while this repo had no CI and no
  pytest installed — the moment either arrived, the suite would lie. Each file gains one
  appended `test_no_check_failures()` asserting the accumulator, and a new
  `_shared/conftest.py` (one directory above `_shared/tests/`, so it outlives that directory)
  adds an order/selection-independent autouse fixture asserting the same thing after every
  test. No `_shared` source file or `check()` line was touched; the standalone
  `python3 test_X.py` runner is unchanged.

### Fixed
- **The 4 `check()`-accumulator errors the plugin-root `conftest.py` unmasked are gone; the 32
  pre-existing failures are untouched (HM-803).** Command, from `plugins/google-ads-management`:
  `PYTHONDONTWRITEBYTECODE=1 uv run --no-project --with pytest --with openpyxl pytest .
  --ignore=skills/google-ads-products/tests -q` — `32 failed, 145 passed, 4 errors` before,
  `32 failed, 145 passed` after. The two failure sets are identical line-for-line, not merely
  equal in count: `diff <(grep '^FAILED' before.txt) <(grep '^FAILED' after.txt)` is empty, where
  each file is that command's output filtered and sorted. **Three of the four were not defects in
  these skills** — correcting the HM-799 gate entry above, which called all four "pre-existing
  defects ... shape-dependent (those skills' standalone runners exit 0)". They are environment
  coupling: `test_health.py::test_orphan_negatives_regression`,
  `test_health.py::test_bundle_emit_and_xlsx_recalc` and
  `test_pmax_listing.py::test_empty_retail_builder_bundle` invoke chart-declaring builders without
  `--no-charts`, so `_shared/render/bundle.py`'s deliberate hard-fail (exit 2 rather than silently
  shipping a chartless report) fires wherever the pinned `vl-convert-python==1.7.0` wheel is
  absent. Adding `--with vl-convert-python==1.7.0` to the same command makes all three pass on the
  pre-fix tree. Nor were the standalone runners all green: on the pre-fix tree in an environment
  without that wheel, `python3 -B tests/test_health.py` exits **1** and
  `python3 -B tests/test_pmax_listing.py` exits **2**; only `test_core.py` exits 0. The **two**
  test modules that invoke a builder CLI (`test_health.py`, `test_pmax_listing.py` — `grep -rn
  'def chart_args' skills | wc -l` -> 2) now derive their builder argv through a local
  `chart_args()` at **4** call sites (`grep -rn '+ chart_args()' skills/*/tests/*.py | wc -l` -> 4;
  the fourth, `test_reject_html_format`, was added by the HM-803 merge gate — its green otherwise
  rested on `build_health_report.py` validating `--formats` before reaching the chart path).
  `test_core.py`, the third module touched by HM-803, defines no `chart_args()` and runs no
  builder subprocess. The helper returns `[]` when `import vl_convert` SUCCEEDS and
  `["--no-charts"]` when it raises — the same real-import probe as the guard it compensates for
  (`_shared/render/charts.py::render_chart_svg`) and as `_has_vl_convert()` in the shared
  toolkit's tests; `importlib.util.find_spec` was rejected by the gate because a locatable but
  unimportable dist (arch-mismatched wheel) resolves under it while the builder still exits 2.
  Each call prints the mode it selected, so a green log can be told apart from a chart-blind one.
  The full chart path stays under test on a correctly provisioned machine and the false red
  disappears elsewhere. None of the three asserts on chart SVGs; their subjects (artifact
  emission, the orphan-negatives lines, xlsx recalc cells, the campaign-benchmark no-row-loss
  table) are unchanged. **The fourth was a real defect** — `test_core.py`'s
  `test_bundle_md_lazy_no_openpyxl` asserted `"openpyxl" not in sys.modules`, a claim about
  process-global state that is only meaningful in a fresh interpreter; its own `main()` comment
  admitted as much by pinning the runner's test order. Under a whole-plugin pytest run it reported
  on whichever other skill's xlsx test had imported openpyxl first, so it passed alone and errored
  in company. The claim now runs in a subprocess (`sys.executable -B -c`) that imports the same
  module surface the test file imports at module scope (`audience_core`, `audience_csv`,
  `audience_spec`, the render toolkit), builds the md-only bundle and reports the verdict as JSON;
  a failed or unparseable probe is a FAIL, never a pass, and it fails under its OWN check name
  (`openpyxl laziness probe ran in a fresh interpreter`) so probe breakage is never reported as a
  laziness regression. The probe's sys.path roots and fixture are checked to exist before it is
  spawned, and its `formats` come over argv rather than a hardcoded copy of the in-process call.
  Mutation-verified, one at a time on a committed baseline, each reverted with
  `git restore --source=HEAD` and re-run under `PYTHONDONTWRITEBYTECODE=1`: flipping
  `build_health_report.py`'s `--no-artifacts` default to `False` errors both account-health tests;
  forcing `chart_args()` to `return []` reproduces all three original chart errors exactly;
  importing `openpyxl` at the top of `audience_spec.py` errors the laziness test; truncating
  `pmax_listing_core.py`'s `"benchmarks"` model list to one row errors the pmax test. No
  `scripts/` behavior, no compute function's output and no existing `check()` name changed (the
  gate ADDED one, the probe-ran check named above); `conftest.py` and `_shared/` are
  byte-identical. Still red and out of scope: `test_pmax_listing.py`'s standalone runner exits 2
  in a wheel-less environment because of `test_bundle_md_html_parity_and_lazy`, one of the 32.
  Two known gaps are filed: (a) **HM-817** — the plugin has no single
  reproducible green across environments — the command above yields `32 failed, 145 passed`
  without the `vl-convert-python` wheel and `23 failed, 154 passed, 9 errors` with it
  (measured POST-fix on this branch; the pre-fix tree showed 10 — HM-803's probe fix
  removed one); (b) **HM-818** — the
  process-global `"openpyxl" not in sys.modules` probe pattern survives at 10 further live
  sites (`grep -rn '"openpyxl" not in sys.modules' skills | wc -l` -> 11 = 10 probe sites
  + 1 comment at `google-ads-audience-targeting/tests/test_core.py:380`; 9 sites in skills
  outside HM-803's scope, 1 inside it at
  `google-ads-pmax-listing-groups/tests/test_pmax_listing.py:417`), where it is
  order-dependent under a whole-plugin run exactly as it was here.
- **`_shared/csv_input.py` — a single comma + exactly 3 fractional digits no longer inflates
  fr/de decimal columns 1000x (HM-794; symmetric twin of HM-778).** After HM-778/R17 the
  single-comma guard grouped on `,\d{3}$`, which was still too wide: `_num('0,125')` -> `125.0`
  and `_num('1 234,125')` -> `1234125.0` (the space is stripped before `_clean_separators`, so
  `'1234,125'` reached the group branch). fr/de Conv. rate, Avg. CPC and fractional-conversion
  columns carry 3-4 decimals, so these read 1000x high — a *plausible wrong number*, not a loud
  `0.0` — and `reconcile.build` derived its control totals from the same inflated rows, so
  `reconcile.verify` still passed. The group reading is now anchored to the ONE en shape a
  single thousands group can take — `re.fullmatch(r"[+-]?[1-9]\d{0,2},\d{3}", s)`: 1-3 leading
  digits, no leading zero, exactly 3 trailing digits (`'1,234'` -> `1234`, `'10,500'` ->
  `10500`). Every other single-comma cell is now the decidable decimal it always was:
  `'0,125'` -> `0.125` (leading zero — no locale groups a value < 1000), `'1234,125'` ->
  `1234.125` (>=4-digit head — not a valid single group; catches space-grouped fr/de too),
  `'1,2345'` -> `1.2345` (>3 fractional digits, already fixed by R17). Multiple commas stay
  grouping (`'1,234,567'` -> `1234567`). **Irreducible residual, unchanged and documented:**
  the exact `'1,234'` shape is byte-identical between an en thousands group (1234) and an fr/de
  decimal (1.234); it keeps the en reading, symmetric with the single-dot default (`'1.234'` ->
  `1.234`) so the twin spellings agree. Deciding it honestly needs column-level locale
  inference — HM-785, whose scope covers the comma-only shape alongside the dot-only one.
  Regression + boundary coverage: `_shared/tests/test_csv_input.py::test_comma_three_digit_decimals`.
- **`_shared/csv_input.py` — locale-formatted UI exports no longer parse to zero (HM-778).**
  `_num` substituted the no-break space instead of stripping it, so `float()` raised and the
  `except` returned `0.0` for every money and count cell in an fr/de-locale Google Ads UI
  export — silently, with no `CsvInputError`, and with `reconcile.build` deriving its control
  totals from the same zeroed rows, so `reconcile.verify` passed on what was effectively a $0
  account. `_num` now strips **all** whitespace (covering U+00A0, U+202F — the group separator
  current CLDR gives fr-FR — and U+2009) and resolves the group/decimal separator in either
  order via the new `_clean_separators` (`'1.234,56'` and `'1,234.56'` both -> `1234.56`),
  which additionally fixes a pre-existing 1000x under-read of de-format money. Every en form
  the module already handled is unchanged (`'1,234.56'`, `'5,000'`, `'CA$1,023.31'`, `'12.3%'`,
  `'--'`). Known, documented limitation: a dot-grouped de integer (`'1.234'` = 1234) is
  byte-identical to an en decimal and keeps the en reading; column-level locale inference is
  HM-785. Regression coverage: `_shared/tests/test_csv_input.py::test_locale_number_formats` —
  the no-break-space family, both separator orders, the unchanged en forms, and an end-to-end
  fr-format CSV that must assemble to real row values and real control totals.
- **`_shared/analytics.py` — `signals` no longer silently ignores `mult` on an absolute rule**
  (HM-779). `mult` scales a *relative* threshold (`value_key`); a rule pairing it with an
  absolute `value` was accepted by `_validate_rule` and then dropped by the evaluator, so
  `{"key":"cost","op":"gt","value":100,"mult":2}` compared against 100 instead of 200 —
  inflating `pre_score` severities with no error, while every other malformed rule shape
  raised loudly. `_validate_rule` now rejects it with a `ValueError`. No shipped rule spec in
  this repo used that shape (all 9 `mult` rules across the skills and parity vectors carry
  `value_key`), so no skill output changes. The evaluator and the canonical `JS_MIRROR` are
  byte-identical — validation is a Python-side precondition the mirror has never encoded.
- **Merge-gate follow-through on HM-778 (R17).** The locale fix reached `_num` only, which
  left the surrounding parsing surface inconsistent — several of these were silent-zeroing or
  wrong-value bugs of exactly the class HM-778 was filed to end:
  - `csv_input.parse_num(v, default=0.0)` is now the PUBLIC number parser, and
    `google-ads-budget-pacing/scripts/assemble_from_csv.py` calls it (`default=None`) instead
    of its own clone. The clone still substituted the no-break space and stripped commas
    unconditionally, so within ONE findings file an fr/de export produced correct
    `cost`/`conversions` (shared `_num`) and a 100x-high or dropped `daily_budget` plus 10x-high
    lost-IS (clone) — pacing % confidently wrong rather than obviously zeroed, and outside what
    reconciliation covers. Reuse `parse_num`; never re-derive a local number parser.
  - Summary-row detection matches localized labels (`Total : ...`, `Gesamt: ...`, and the other
    UI spellings), colon still required. An `total:`-only filter kept fr/de total rows as data
    rows — inert while their cells parsed to `0.0`, but a doubling of every control total once
    HM-778 made them real (build and verify agree on the inflated sum, so verify still passes).
  - `_clean_separators`: a single `','` is a group separator only in the one shape an en
    thousands group can take (exactly 3 trailing digits), so fr cells with 3-4 decimals
    (`'1,2345'`) read as decimals instead of a 1000x over-read; two or more `'.'`
    (`'1.234.567'`) is unambiguous grouping instead of a `float()` failure returning `0.0`.
    The single-dot HM-785 carve-out is unchanged.
  - Currency handling accepts `€ £ ¥` on either side (`'€1 234,56'`, `'1 234,56 €'`), which
    returned `0.0` before — in precisely the locales this fix targets. An alphabetic suffix
    (`'1234,56 EUR'`) is still unhandled and documented as such.
  - `_pct`'s unsigned branch: `'0,9'` now reads as the fraction 0.9, agreeing with its en twin
    `'0.9'` (it previously parsed as 9.0 and came back 0.09). Real output change on such cells,
    the intended one, and now pinned by checks.
  - The three surfaces restating the `num` contract (`_shared/README.md`,
    `google-ads-foundation/references/artifact-formats.md`, `csv_input.py`'s module contract
    line) describe the locale semantics and point at `parse_num`.
  - Byte-IO family (R16): `widget_emit`, `render/bundle`, `render/charts` and `gaql_raw` pin
    `encoding="utf-8"` / `utf-8-sig`. With locale rows surviving, non-ASCII campaign names now
    reach the writers, and `write_text()` would otherwise use the host's preferred encoding.
  - `test_analytics.py`'s "relative mult defaults to 1.0" check is asserted at the boundary
    (x == y, `ge` fires / `gt` does not); the old 150-vs-100 probe passed for any default in
    [0, 1.5) and pinned nothing HM-779's docstring made normative.

## 2.0.0 — Advisor upgrade & 3-format parity

Headline release: every data skill is now a dual-input (Google Ads MCP **or** user CSV),
done-with-you **advisor** that emits an analytical bundle and then leads a prioritized,
model-grounded recommendation conversation. This redefines the output contract of the existing
management skills (previously Editor-CSV-first), hence the major version bump.

### Shared foundations (`_shared/`)
- **Analytics primitives** (`analytics.py`) — deterministic, kernel-mirrorable `concentration`
  (top-share / HHI / effective-N), `signals` (declarative per-row rule flags), and `pre_score`
  (weighted flag scoring), back-ported from the audit plugins. Pure stdlib; a canonical
  `JS_MIRROR` keeps the browser translation in lockstep.
- **Shared CSV manual-input path** (`csv_input.py`) — the CSV twin of the MCP path
  (`assemble_from_csv` / `load_csv_rows`) running the same transcription-firewall + reconciliation
  discipline, producing a model **identical** to the MCP path except for an honest
  `meta.source: user_csv` label. Handles Google Ads UI export quirks (locale header variance,
  title/summary rows, BOM, thousands separators, percent columns).
- **Advisor output contract** — documented in `google-ads-foundation` (emit hero HTML report →
  recommend from model numbers → offer Editor apply-CSVs), with an honest data-source posture for
  API-blind data (Auction Insights, Customer Match match rates, Enhanced-Conversions / Consent-Mode).

### 7 skills deepened (already-3-format → advisor + concentration/signals + CSV input)
`budget-pacing`, `keywords-search-terms`, `performance-reporting`, `pmax-campaigns`,
`pmax-listing-groups`, `products`, `quality-score` — added shared analytics (n-gram / asset-group /
tier / dominant-factor concentration, period/anomaly signals & pre-scorers), the advisor
recommendation layer, and the dual MCP/CSV input path.

### 5 skills built to advisor bundles
- Full 3-format bundle (md + interactive HTML explorer + tunable xlsx): `bidding-strategy`,
  `competitive-analysis` (Auction Insights via CSV), `conversions-tracking`.
- Reduced bundle (md + tunable xlsx — structural/checklist signal, no per-row HTML filter):
  `account-health`, `audience-targeting`.

### Hub + integration
- The `google-ads` hub (`references/catalog.json` + `SKILL.md`) wires the 5 newly-tunable/advisor
  skills into the "manage Google Ads" menu, with per-task input mode, window, and declared formats.

### Parity & verification
- Node↔Python kernel-parity gate coverage for **all** tunable kernels plus the shared
  analytics primitives (`skills/google-ads/tests/run_parity.py`): 13 kernels green.
- Provenance token normalized to `mcp` for live pulls (HM-572); conversions-tracking JS_KERNEL
  parity gate added (HM-571).

### First-published baseline
## 1.0.0
- Initial `google-ads-management` plugin: the `google-ads` hub plus foundation and the
  management skills, driving the read-only Google Ads MCP and producing Editor CSVs and the
  early md/HTML/xlsx bundles on the shared `render/` toolkit.
