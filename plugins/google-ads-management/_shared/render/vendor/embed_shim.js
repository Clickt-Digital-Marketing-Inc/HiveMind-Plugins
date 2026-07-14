/* Minimal Vega-Lite embed shim. Replaces vega-embed so the explorer stays
   fully self-contained: no action menu, no external links, ~30 lines vs 100KB.
   Load order in the explorer: vega.min.js, vega-lite.min.js, then this file.

   vlEmbed(el, spec) -> vega.View
     Compiles a Vega-Lite spec, mounts an SVG view into `el`, and runs it.
     The returned View is live: push new rows with
       view.change("rows", vega.changeset().remove(() => true).insert(rows)).run()
     (all chart specs in this toolkit read from the named dataset "rows"; the
     changeset form is required — the view.data(name, values) setter does not
     reliably propagate through Vega-Lite's derived datasets). */
function vlEmbed(el, spec) {
  var rt = vega.parse(vegaLite.compile(spec).spec);
  return new vega.View(rt, { renderer: "svg", container: el, hover: false }).run();
}
