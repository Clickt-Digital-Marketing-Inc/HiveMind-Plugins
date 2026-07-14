# Vendored runtime — wPPC

These files are committed **verbatim** (byte-identical to the upstream builds) and are
the ONLY third-party JS anywhere in wPPC's outputs. Never edit them by hand; to
upgrade, re-download, re-pin the version here, regenerate `SHA256SUMS`
(`shasum -a 256 *.js`), and re-run `tests/test_charts.py`.

| File | Library | Version | Source | Downloaded |
| -- | -- | -- | -- | -- |
| `vega.min.js` | Vega | 5.30.0 | https://cdn.jsdelivr.net/npm/vega@5.30.0/build/vega.min.js | 2026-07-06 |
| `vega-lite.min.js` | Vega-Lite | 5.20.1 | https://cdn.jsdelivr.net/npm/vega-lite@5.20.1/build/vega-lite.min.js | 2026-07-06 |
| `embed_shim.js` | n/a (in-repo) | n/a | Written here; replaces vega-embed (no action menu, no external links) | 2026-07-06 |
| `gsap.min.js` | GSAP core | 3.12.5 | https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js | 2026-07-08 |

`vega.min.js`, `vega-lite.min.js`, and `embed_shim.js` are the chart runtime
consumed together by `charts.py:vendor_blob()` (load order matters: vega, then
vega-lite, then the embed shim). `gsap.min.js` is a **separate** blob — it is
not part of the chart runtime and is not touched by `vendor_blob()`; it is
consumed directly by the HTML renderer (a later issue) for count-up/reveal
animations.

## Version-lock contract

Static SVGs (md report, in-Claude tuner widget) are rendered by
**vl-convert-python 1.7.0** (pinned exact in `requirements.txt`), which bundles
Vega-Lite 5.20.x and Vega 5.30.x. The vendored runtime above must stay on the
**same Vega-Lite major.minor** so the live standalone-explorer charts and the
static SVGs agree. Verified at pin time:

```
>>> import vl_convert; vl_convert.get_vegalite_versions()
['5.8', '5.14', '5.15', '5.16', '5.17', '5.18', '5.19', '5.20', '5.21']
```

`charts.py` passes `vl_version="5.20"` explicitly on every static render;
`VL_VERSION` there must match the `vega-lite.min.js` major.minor here.

## GSAP license

GSAP is free for everyone including commercial, sold products under the GSAP
standard license (Webflow, 2025) — no separate business license required; the
only prohibited use is building a competing no-code animation tool. Verified
2026-07-08 (gsap.com/community/standard-license).
