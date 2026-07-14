"""CSV/YAML loading: skip_rows preamble handling + precise missing-column error."""

import textwrap

import pytest

from wppc.io import MappingError, load_mapping, load_segments

_MAPPING = {
    "skip_rows": 2,
    "segment_id": "Search keyword",
    "denominator": "Clicks",
    "funnel": {
        "click": "Clicks",
        "engagement": "Engaged sessions",
        "add_to_cart": "Add to cart",
        "initiate_checkout": "Begin checkout",
        "purchase": "Purchases",
    },
    "repeats": "Repeat purchases",
    "currency": {"CM3_order": 42.0, "repeat_rate": 0.5, "CM3_repeat": 42.0},
}


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text).lstrip("\n"))
    return str(p)


def test_skip_rows_locates_header_below_preamble(tmp_path):
    csv = _write(tmp_path, "g.csv", """
        Report title row
        "April 14, 2026 - May 13, 2026"
        Search keyword,Clicks,Engaged sessions,Add to cart,Begin checkout,Purchases,Repeat purchases
        kw_a,400,240,60,28,10,2
        kw_b,400,120,18,12,10,0
    """)
    df, currency = load_segments(csv, _MAPPING, "google")
    assert list(df["segment_id"]) == ["kw_a", "kw_b"]
    assert df["clicks"].sum() == 800
    assert df["purchase"].tolist() == [10, 10]
    assert currency["CM3_order"] == 42.0


def test_missing_column_fails_with_named_error(tmp_path):
    # 'Purchases' column is absent.
    csv = _write(tmp_path, "g.csv", """
        Report title row
        "date range"
        Search keyword,Clicks,Engaged sessions,Add to cart,Begin checkout,Repeat purchases
        kw_a,400,240,60,28,2
    """)
    with pytest.raises(MappingError) as exc:
        load_segments(csv, _MAPPING, "google")
    msg = str(exc.value)
    assert "Purchases" in msg
    assert "google" in msg


def test_thousands_separators_parsed(tmp_path):
    csv = _write(tmp_path, "g.csv", """
        title
        "range"
        Search keyword,Clicks,Engaged sessions,Add to cart,Begin checkout,Purchases,Repeat purchases
        kw_big,"2,000","1,400",420,260,150,70
    """)
    df, _ = load_segments(csv, _MAPPING, "google")
    assert df["clicks"].iloc[0] == 2000
    assert df["engagement"].iloc[0] == 1400


def test_load_mapping_missing_platform(tmp_path):
    yml = _write(tmp_path, "m.yaml", """
        google:
          skip_rows: 0
          segment_id: x
          denominator: Clicks
          funnel: {click: Clicks, engagement: e, add_to_cart: a, initiate_checkout: i, purchase: p}
          repeats: r
          currency: {CM3_order: 1, repeat_rate: 0, CM3_repeat: 1}
    """)
    with pytest.raises(MappingError, match="meta"):
        load_mapping(yml, "meta")


def test_load_mapping_missing_currency_key(tmp_path):
    yml = _write(tmp_path, "m.yaml", """
        google:
          segment_id: x
          denominator: Clicks
          funnel: {click: Clicks, engagement: e, add_to_cart: a, initiate_checkout: i, purchase: p}
          repeats: r
          currency: {CM3_order: 1, repeat_rate: 0}
    """)
    with pytest.raises(MappingError, match="CM3_repeat"):
        load_mapping(yml, "google")
