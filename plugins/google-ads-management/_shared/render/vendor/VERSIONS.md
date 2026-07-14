# Vendored chart runtime — pinned versions

These files are committed verbatim (byte-identical to the upstream npm builds)
and inlined into the standalone `*_explorer.html` by `render/charts.py:vendor_blob()`.
They are the ONLY third-party JS anywhere in the toolkit's outputs. Never edit
them; to upgrade, re-download, re-pin here, regenerate `SHA256SUMS`, and keep
the vl-convert pin in lockstep (see below).

| File | Version | Source (downloaded 2026-07-06) |
|---|---|---|
| `vega.min.js` | 5.30.0 | https://cdn.jsdelivr.net/npm/vega@5.30.0/build/vega.min.js |
| `vega-lite.min.js` | 5.20.1 | https://cdn.jsdelivr.net/npm/vega-lite@5.20.1/build/vega-lite.min.js |
| `embed_shim.js` | n/a (in-repo) | Written here; replaces vega-embed (no action menu, no external links) |

SHA-256 checksums live in `SHA256SUMS` (same directory) and are verified by
`render/tests/test_render_toolkit.py`.

## Version-lock contract

Static SVGs (md report, in-chat widgets) are rendered by **vl-convert-python
1.7.0** (pinned exact in this plugin's `requirements.txt`), which
bundles Vega-Lite 5.20.x and Vega 5.30.x. The vendored runtime above must stay on
the **same Vega-Lite major.minor** so the live explorer charts and the static
SVGs agree. Verified at pin time:

```
>>> import vl_convert; vl_convert.get_vegalite_versions()
['5.8', '5.14', '5.15', '5.16', '5.17', '5.18', '5.19', '5.20', '5.21']
```

`render/charts.py` passes `vl_version="5.20"` explicitly on every static render;
`VL_VERSION` there must match the `vega-lite.min.js` major.minor here.
