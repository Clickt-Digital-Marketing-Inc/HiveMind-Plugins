"""Suite-wide guards that must outlive the files they guard.

The `_failures` accumulator guard
---------------------------------
The `_shared` test files (`tests/test_analytics.py`, `tests/test_csv_input.py`,
`tests/test_data_guards.py`) keep the plugin's script shape: `check(name, cond)`
prints and APPENDS to a module-global `_failures`, and none of that accumulation
is ever asserted by the checks themselves. Each file now ends (HM-791) with a
`test_no_check_failures` that asserts the accumulator — which makes a whole-file,
definition-order, single-process run honest, and nothing else. Select one node id
(`pytest tests/test_csv_input.py::test_typed_conversion`), pass `-k`, use `--lf`,
or let xdist schedule `test_no_check_failures` first, and every failed `check()`
in that file is reported green.

So the assertion lives here instead of only in those files: an autouse fixture
records `len(_failures)` before each test and asserts, after it, that the test
appended NOTHING new. Per-test deltas (rather than asserting the whole list)
attribute each failed `check()` to exactly the test that produced it, so one
root-cause failure does not cascade into an ERROR on every later passing test in
the module. It is order-independent, selection-independent and parallel-safe,
and it is placed one directory above `tests/` — the files it guards — so
deleting that directory cannot delete the guard: a later ported/added file in
this shape is covered by construction.

Scope: any collected module that exposes a `_failures` list is covered. That is
the three `tests/` files here AND `render/tests/test_render_toolkit.py`, which
uses the same `check()`-accumulator shape — its per-test checks are governed by
this delta fixture too. Modules without a `_failures` attribute (every other
test in this plugin) are untouched: the fixture returns early for them.

Note: `test_analytics.py` runs its `check()` battery at MODULE scope (import),
not inside `test_*` functions, so its failures are already present before the
first test's baseline and are NOT caught by this per-test delta. That file's
appended `test_no_check_failures()` — which asserts the whole `_failures` list —
is what makes it red; keep it.
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
