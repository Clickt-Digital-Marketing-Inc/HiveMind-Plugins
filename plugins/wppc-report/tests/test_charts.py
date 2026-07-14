"""Vega-Lite chart layer: vendor parity, the four declared specs render, and
vendor_blob() self-containment.

Mirrors the determinism discipline in wppc/charts.py — every render here is a
pure function of (declaration, synthetic rows), no live data, no clock.
"""

import hashlib

import pytest

from wppc import charts as C

# The exact byte-identical vendor hashes this issue pins (CLI-402).
_EXPECTED_HASHES = {
    "vega.min.js": "e432c751a6363f4a61da62920cc7d7ebd13cf09d82949f8f486248f8071dc3ce",
    "vega-lite.min.js": "cfaa9b39c9dc6ba8749d81dde236cb9d89938978df400640adaf934a790cfae7",
    "embed_shim.js": "9f4b8a906bb35ac0efd5da86999cec112defb561ff0c11b8c22013a7b12a2d1e",
    "gsap.min.js": "28033e449a31ebcc396e5be8b13b63152bf03094288fb5867034321927bce087",
}

# Small synthetic row fixtures keyed by chart id, matching each declaration's
# encoding field names exactly.
_ROWS_BY_CHART = {
    "mar_by_segment": [
        {"segment_id": "kw_a", "MAR": 120.5},
        {"segment_id": "kw_b", "MAR": -15.0},
    ],
    "wppc_plus_by_segment": [
        {"segment_id": "kw_a", "wPPC+": 130.0},
        {"segment_id": "kw_b", "wPPC+": 82.0},
    ],
    "derived_weights": [
        {"state": "click", "w": 1.05},
        {"state": "engagement", "w": 1.26},
        {"state": "add_to_cart", "w": 6.09},
        {"state": "initiate_checkout", "w": 9.24},
        {"state": "purchase", "w": 24.36},
        {"state": "repeat", "w": 21.00},
    ],
    "closing_ratio_vs_wppc": [
        {"segment_id": "kw_a", "closing_ratio": 0.85, "wPPC": 12.4},
        {"segment_id": "kw_b", "closing_ratio": 1.15, "wPPC": 9.8},
    ],
}


def test_vendor_sha256_parity():
    sums_path = C.VENDOR_DIR / "SHA256SUMS"
    assert sums_path.exists(), "wppc/vendor/SHA256SUMS is missing"
    listed = {}
    for line in sums_path.read_text().strip().splitlines():
        digest, name = line.split()
        listed[name] = digest

    # Every file listed in SHA256SUMS actually exists and its hash matches.
    for name, digest in listed.items():
        fpath = C.VENDOR_DIR / name
        assert fpath.exists(), f"vendor file '{name}' listed in SHA256SUMS but missing on disk"
        got = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert got == digest, f"{name}: SHA256SUMS says {digest}, actual is {got}"

    # The four expected vendored files/hashes are present and correct.
    for name, expected in _EXPECTED_HASHES.items():
        assert name in listed, f"'{name}' missing from SHA256SUMS"
        assert listed[name] == expected, f"{name}: expected {expected}, SHA256SUMS has {listed[name]}"
        fpath = C.VENDOR_DIR / name
        got = hashlib.sha256(fpath.read_bytes()).hexdigest()
        assert got == expected, f"{name}: expected {expected}, actual file hash is {got}"


@pytest.mark.parametrize("decl", C.WPPC_CHARTS, ids=lambda d: d["id"])
def test_wppc_chart_renders(decl):
    vl_spec = C.build_vl_spec(decl)
    rows = _ROWS_BY_CHART[decl["id"]]
    svg = C.render_chart_svg(vl_spec, rows)
    assert isinstance(svg, str) and svg, f"{decl['id']}: render_chart_svg returned empty output"
    assert "<svg" in svg, f"{decl['id']}: output does not contain '<svg'"


def test_wppc_charts_declares_all_four_ids():
    ids = [c["id"] for c in C.WPPC_CHARTS]
    assert ids == [
        "mar_by_segment",
        "wppc_plus_by_segment",
        "derived_weights",
        "closing_ratio_vs_wppc",
    ]


def test_vendor_blob_self_containment():
    blob = C.vendor_blob()
    assert C.VENDOR_BEGIN in blob
    assert C.VENDOR_END in blob
    for name in C.VENDOR_FILES:
        content = (C.VENDOR_DIR / name).read_text()
        assert content in blob, f"vendor_blob() missing content of {name}"
    # GSAP is a separate blob, never part of the chart runtime.
    assert "gsap" not in blob.lower(), "vendor_blob() must not contain GSAP — it is a separate blob"
    assert "gsap.min.js" not in C.VENDOR_FILES
