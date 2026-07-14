#!/usr/bin/env python3
"""JS<->Python parity for the cm3 HTML explorer's live rollups.

Builds the explorer with --no-charts (so jsdom loads cleanly with no Vega
runtime), computes the By Campaign / By Vendor / By Category (L1-L5) / By
Product Type (L1-L5) rollups in Python via compute() at the report defaults
and two cumulative tuned scenarios (a band cutoff, then a cost assumption),
and runs explorer_parity_cm3.mjs to assert the explorer's live rollupData(dim)
kernel matches Python at every point — bucket names, sort order, and all
numeric columns to 1e-6.

This is the explorer analogue of run_parity_cm3.py (which covers the in-Claude
tuner widget). The rollup tables that render in the explorer are driven by the
same rollupData() the harness evaluates, so this pins the live UI to Python.

Dev-only: needs `npm install` in this dir (jsdom). The plugin never runs this.
Run: python3 tests/run_explorer_parity_cm3.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL))

import cm3_by_product as cm3   # noqa: E402
import cm3_html               # noqa: E402

PY = sys.executable
NODE = "node"
SAMPLE = HERE / "sample-shopping.csv"

# Must mirror cm3_by_product.main()'s inputs.setdefault() block.
BASE_INPUTS = {
    "cogs_pct": 65, "ship_pct": 20, "proc_pct": 2.9, "fixed_costs": 0,
    "band_exc": 0.10, "band_high": 0.05, "band_avg": 0.00, "band_low": -0.25,
}
# explorer control key -> (inputs key, scale from the control's JS value to the input)
CTRL_TO_INPUT = {
    "ship": ("ship_pct", 100), "proc": ("proc_pct", 100), "fixed": ("fixed_costs", 1),
    "exc": ("band_exc", 1), "high": ("band_high", 1), "avg": ("band_avg", 1), "low": ("band_low", 1),
}
# Cumulative tunes: a cutoff first, then a cost assumption — both non-vacuous on the fixture.
STEPS = [("exc", 0.05), ("ship", 0.30)]

# A synthetic multi-level fixture: category depths L1-L3 and product-type depths
# L1-L2 (mixed, so deeper levels and the '(unset)' bucket both occur), a vendorless
# product (vendor rollup must skip it), and a $0-revenue product. This exercises the
# level loop and unset bucketing that the L1-only sample CSV never reaches.
_ML_HEADER = (
    "Product Title,Campaign,Category (1st level),Category (2nd level),"
    "Category (3rd level),Category (4th level),Category (5th level),"
    "Product type (1st level),Product type (2nd level),Product type (3rd level),"
    "Product type (4th level),Product type (5th level),Clicks,Impr.,Cost,"
    "Conversions,Conv. value,Currency code"
)
_ML_ROWS = [
    'Widget A : Acme,PMax,Apparel,Shirts,Tees,,,Tops,Tees,,,,120,4000,300,8,1400,CAD',
    'Widget B : Acme,PMax,Apparel,Shirts,,,,Tops,,,,,60,2000,150,3,520,CAD',
    'Gadget C : Nimbus,Search,Electronics,Cables,,,,Wires,,,,,90,3300,410,5,900,CAD',
    'Gizmo D,Search,Electronics,,,,,,,,,,40,1500,220,0,0,CAD',
    'Thing E : Acme,Display,,,,,,Misc,,,,,25,900,60,1,140,CAD',
    'Doohickey F : Nimbus,PMax,Apparel,Pants,,,,Bottoms,,,,,75,2600,260,4,1180,CAD',
]


def _write_multilevel_csv(path: Path) -> None:
    path.write_text("Shopping products\n\"Mar 1, 2026 - Mar 31, 2026\"\n"
                    + _ML_HEADER + "\n" + "\n".join(_ML_ROWS) + "\n", encoding="utf-8")


def _brow(name, b, tot, vcogs=None):
    row = {
        "name": name, "n": b.n_products, "impr": b.impr, "clicks": b.clicks,
        "conv": b.conv, "cost": b.cost, "rev": b.conv_value, "roas": b.roas,
        "cm3": b.cm3, "cm3_pct": b.cm3_pct, "share": (b.cm3 / tot) if tot else 0,
    }
    if vcogs is not None:
        row["vcogs"] = vcogs.get(name)
    return row


def rollups_for(csv_path: Path, inputs: dict) -> dict:
    products, _, _ = cm3.parse_csv(str(csv_path))
    ctx = cm3.compute(products, dict(inputs))
    tot = ctx["totals"].cm3
    vc = cm3_html._vendor_cogs_map(ctx)

    def blist(items, vcogs=None):
        return [_brow(n, b, tot, vcogs) for n, b in sorted(items, key=lambda kv: -kv[1].cm3)]

    return {
        "camp": {"rows": blist(ctx["by_campaign"].items())},
        "ven": {"rows": blist(ctx["by_vendor"].items(), vc)},
        "cat": {"levels": [{"level": lvl, "rows": blist(bk.items())} for lvl, bk in ctx["cat_levels"]]},
        "pt": {"levels": [{"level": lvl, "rows": blist(bk.items())} for lvl, bk in ctx["pt_levels"]]},
    }


# ── Pivot cross-tab parity: an exact Python mirror of the explorer's
# pivotData(rowDim,colDim,measure). Combos exercise single-level dims, a
# taxonomy-level dim on each axis, a summed measure, a count, and a ratio.
PIVOT_COMBOS = [
    ("camp", "ven", "cm3"),
    ("catL0", "camp", "rev"),
    ("ptL0", "ven", "n"),
    ("camp", "ven", "cm3_pct"),
]


def _pv_key(p, dim):
    # Mirrors JS pivotKey: camp keeps its "(no campaign)" fallback; every other
    # dim maps a blank value to "(unset)" so the cross-tab conserves all products.
    if dim == "camp":
        return p.campaign or "(no campaign)"
    if dim == "ven":
        return p.vendor if p.vendor else "(unset)"
    if dim.startswith("catL"):
        n = int(dim[4:]); v = p.cat[n] if n < len(p.cat) else ""
        return v if v else "(unset)"
    if dim.startswith("ptL"):
        n = int(dim[3:]); v = p.ptype[n] if n < len(p.ptype) else ""
        return v if v else "(unset)"
    return "(unset)"


def _pv_measure(b, meas):
    if meas == "cm3_pct":
        return (b["cm3"] / b["rev"]) if b["rev"] > 0 else None
    if meas == "roas":
        return (b["rev"] / b["cost"]) if b["cost"] > 0 else None
    return b[meas]  # cm3 | rev | cost | n (summed on the bucket)


def pivot_for(csv_path, inputs, rowDim, colDim, measure):
    products, _, _ = cm3.parse_csv(str(csv_path))
    cm3.compute(products, dict(inputs))  # sets p.cm3 etc.

    def nb():
        return {"n": 0, "cost": 0.0, "rev": 0.0, "cm3": 0.0}

    def add(b, p):
        b["n"] += 1; b["cost"] += p.cost; b["rev"] += p.conv_value; b["cm3"] += p.cm3

    cellB, rowB, colB, grand = {}, {}, {}, nb()
    for p in products:
        rk, ck = _pv_key(p, rowDim), _pv_key(p, colDim)
        cellB.setdefault(rk, {}).setdefault(ck, nb()); add(cellB[rk][ck], p)
        rowB.setdefault(rk, nb()); add(rowB[rk], p)
        colB.setdefault(ck, nb()); add(colB[ck], p)
        add(grand, p)

    def mv(b):
        return _pv_measure(b, measure)

    neg = float("-inf")

    def skey(m, k):
        v = mv(m[k]); return neg if v is None else v

    all_row = sorted(rowB.keys(), key=lambda k: skey(rowB, k), reverse=True)
    all_col = sorted(colB.keys(), key=lambda k: skey(colB, k), reverse=True)
    row_keys, col_keys = all_row[:12], all_col[:12]
    cell = {rk: {ck: (mv(cellB[rk][ck]) if ck in cellB[rk] else None) for ck in col_keys}
            for rk in row_keys}
    return {
        "measure": measure, "rowDim": rowDim, "colDim": colDim,
        "rowKeys": row_keys, "colKeys": col_keys, "cell": cell,
        "rowTot": {rk: mv(rowB[rk]) for rk in row_keys},
        "colTot": {ck: mv(colB[ck]) for ck in col_keys},
        "grand": mv(grand),
        "extraRows": len(all_row) - len(row_keys),
        "extraCols": len(all_col) - len(col_keys),
        "nRows": len(all_row), "nCols": len(all_col),
    }


def pivots_for(csv_path, inputs):
    return [{"combo": [rd, cd, ms], "pivot": pivot_for(csv_path, inputs, rd, cd, ms)}
            for (rd, cd, ms) in PIVOT_COMBOS]


def _run_one(td: Path, csv_path: Path, label: str) -> int:
    expl = td / f"explorer_{label}.html"
    r = subprocess.run(
        [PY, str(SKILL / "cm3_by_product.py"), "--csv", str(csv_path),
         "--no-charts", "--no-normalize", "--output-html", str(expl)],
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        print(f"FAIL — explorer build failed ({label})")
        return 1

    default = rollups_for(csv_path, BASE_INPUTS)
    default_pivots = pivots_for(csv_path, BASE_INPUTS)
    cur = dict(BASE_INPUTS)
    steps = []
    for key, val in STEPS:
        ik, scale = CTRL_TO_INPUT[key]
        cur[ik] = val * scale
        steps.append({"key": key, "value": val,
                      "rollups": rollups_for(csv_path, cur),
                      "pivots": pivots_for(csv_path, cur)})

    expf = td / f"expected_{label}.json"
    expf.write_text(json.dumps({"default": default, "defaultPivots": default_pivots, "steps": steps}),
                    encoding="utf-8")

    r = subprocess.run([NODE, str(HERE / "explorer_parity_cm3.mjs"), str(expl), str(expf)],
                       capture_output=True, text=True, cwd=str(HERE))
    sys.stdout.write(f"[{label}] ")
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r.returncode


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        ml_csv = tdp / "multilevel-shopping.csv"
        _write_multilevel_csv(ml_csv)
        rc = 0
        rc |= _run_one(tdp, SAMPLE, "sample")
        rc |= _run_one(tdp, ml_csv, "multilevel")
        return rc


if __name__ == "__main__":
    sys.exit(main())
