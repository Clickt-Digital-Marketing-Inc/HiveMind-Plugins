"""Plugin-wide guards that must outlive the files they guard.

The `_failures` accumulator guard (HM-791 for `_shared`, HM-799 for the skills)
--------------------------------------------------------------------------------
Every test module in this plugin keeps the script shape: `check(name, cond,
detail)` PRINTS and APPENDS to a module-global `_failures`, and nothing in the
`test_*` functions ever asserts that list. Only each file's `main()` — the
standalone runner, `python3 tests/test_perf.py` — inspects the accumulator and
exits non-zero. Under pytest, `main()` never runs, so a collected
`test_liveness_gating()` that consists solely of `check()` calls passes NO
MATTER WHAT the code under test does.

HM-791 fixed this one level up for `_shared/tests/`. The per-skill trees
(`skills/*/tests/`) are siblings of `_shared/`, so that conftest never governed
them: on this branch, perturbing every cost/spend value in
`skills/google-ads-performance-reporting/tests/sample-liveness.json`, or
deleting the dormant gate in `scripts/perf_core.py` outright, left
`pytest skills/google-ads-performance-reporting -q` byte-identical to the
unperturbed run.

So the assertion lives here, at the plugin root — one level above BOTH
`_shared/` and `skills/`, above every `skills/<skill>/tests/` tree, so deleting
any skill (or any `tests/` directory) cannot delete the guard, and a skill added
later by the google-ads kernel ports is covered by construction rather than by
someone remembering to add a conftest.

Mechanism: an autouse fixture records `len(_failures)` before each test and
asserts, after it, that the test appended NOTHING new. Per-test deltas (rather
than asserting the whole list) attribute each failed `check()` to exactly the
test that produced it, so one root-cause failure does not cascade into an ERROR
on every later passing test in the module. It is order-independent,
selection-independent and parallel-safe.

Scope: any collected module that exposes a `_failures` list. Modules without one
are untouched — the fixture returns early for them.

`_shared/conftest.py` deliberately defines a fixture with the SAME name; pytest
resolves a fixture to its most specific definition, so tests under `_shared/`
use that one (and its module-scope caveat documented there) and are not
double-checked by this one.

Caveat inherited from HM-791: a `check()` battery run at MODULE scope (import
time) is already accumulated before the first test's baseline and is NOT caught
by a per-test delta. `_shared/tests/test_analytics.py` is the one file in that
shape; its own appended `test_no_check_failures()` is what makes it red.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _assert_no_accumulated_check_failures(request):
    module = getattr(request.node, "module", None)
    before = len(getattr(module, "_failures", ()) or ())
    yield
    failures = getattr(module, "_failures", None)
    if failures is None:
        return
    new = failures[before:]
    assert not new, (
        f"{module.__name__}: {len(new)} failed check(s) accumulated in "
        f"`_failures` during this test — {', '.join(map(str, new))}. `check()` "
        f"records instead of asserting, so this fixture is what makes it red "
        f"regardless of how the run was selected or ordered."
    )
