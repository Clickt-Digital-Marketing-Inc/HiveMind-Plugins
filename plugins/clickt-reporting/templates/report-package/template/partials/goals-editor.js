// Goals-tab editor runtime. Edits the ACTIVE goal set; Export rebuilds the full
// goals.json (other historical sets preserved untouched). No network calls.
(function () {
  var root = document.querySelector("[data-goals-editor]");
  var payloadEl = document.querySelector("[data-ge-payload]");
  if (!root || !payloadEl) return;
  var payload;
  try { payload = JSON.parse(payloadEl.textContent); } catch (e) { return; }
  var catalog = payload.catalog;
  var file = payload.file;
  var sets = file.goal_sets || [];
  var active = null;
  for (var i = 0; i < sets.length; i++)
    if (sets[i].effective_from === payload.activeEffectiveFrom) active = sets[i];
  if (!active) { active = { effective_from: new Date().toISOString().slice(0, 10), status: "proposed", goals: [] }; sets.push(active); }
  var goals = (active.goals || []).map(function (g) { return Object.assign({}, g); });

  var effectiveInput = root.querySelector("[data-ge-effective]");
  var statusSelect = root.querySelector("[data-ge-status]");
  var tbody = root.querySelector("[data-ge-rows]");
  var msg = root.querySelector("[data-ge-msg]");
  var output = root.querySelector("[data-ge-output]");
  var dlBtn = root.querySelector("[data-ge-download]");
  var copyBtn = root.querySelector("[data-ge-copy]");
  effectiveInput.value = active.effective_from || "";
  statusSelect.value = active.status || "proposed";

  function catFor(id) {
    for (var i = 0; i < catalog.length; i++) if (catalog[i].id === id) return catalog[i];
    return null;
  }
  function metricOptions(sel) {
    return catalog.map(function (c) {
      return '<option value="' + c.id + '"' + (c.id === sel ? " selected" : "") + ">" + c.label + "</option>";
    }).join("");
  }
  function el(html) { var t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; }

  function renderRows() {
    tbody.innerHTML = "";
    goals.forEach(function (g, idx) {
      var cat = catFor(g.metric) || {};
      var skuDisabled = cat.scoped === "sku" ? "" : " disabled";
      var row = el('<tr>' +
        '<td><input type="text" data-f="label" value="' + (g.label || "").replace(/"/g, "&quot;") + '" placeholder="' + (cat.label || g.metric) + '"></td>' +
        '<td><select data-f="metric">' + metricOptions(g.metric) + "</select></td>" +
        '<td><input type="text" data-f="sku_match"' + skuDisabled + ' value="' + (g.sku_match || "").replace(/"/g, "&quot;") + '" placeholder="' + (cat.scoped === "sku" ? "product title contains…" : "—") + '"></td>' +
        '<td><input type="text" data-f="period" value="' + (g.period || "monthly") + '" size="8"></td>' +
        '<td><input type="number" step="any" data-f="target" value="' + (g.target != null ? g.target : "") + '"></td>' +
        '<td><select data-f="direction"><option value="higher"' + ((g.direction || cat.direction || "higher") === "higher" ? " selected" : "") + ">higher is better</option><option value=\"lower\"" + ((g.direction || cat.direction) === "lower" ? " selected" : "") + ">lower is better</option></select></td>" +
        '<td><button type="button" class="ge-del" title="Remove goal">✕</button></td></tr>');
      row.addEventListener("input", function (ev) {
        var f = ev.target.getAttribute("data-f");
        if (!f) return;
        var v = ev.target.value;
        if (f === "target") g.target = v === "" ? null : Number(v);
        else if (f === "metric") {
          g.metric = v;
          var c = catFor(v) || {};
          g.direction = c.direction || "higher";
          if (c.scoped !== "sku") delete g.sku_match;
          renderRows();
        } else if (v === "" || (f === "period" && v === "monthly")) delete g[f];
        else g[f] = v;
      });
      row.querySelector(".ge-del").addEventListener("click", function () { goals.splice(idx, 1); renderRows(); });
      tbody.appendChild(row);
    });
  }
  renderRows();

  root.querySelector("[data-ge-add]").addEventListener("click", function () {
    goals.push({ id: "goal_" + (goals.length + 1) + "_" + Math.random().toString(36).slice(2, 6), metric: catalog[0].id, target: null });
    renderRows();
  });

  root.querySelector("[data-ge-export]").addEventListener("click", function () {
    var problems = [];
    goals.forEach(function (g, i) {
      var cat = catFor(g.metric);
      if (!cat) problems.push("row " + (i + 1) + ": unknown metric");
      if (g.target == null || isNaN(g.target)) problems.push("row " + (i + 1) + ": target missing");
      if (cat && cat.scoped === "sku" && !g.sku_match) problems.push("row " + (i + 1) + ": SKU match required");
      if (g.period && g.period !== "monthly" && !/^\d{4}-\d{2}$/.test(g.period)) problems.push("row " + (i + 1) + ": period must be 'monthly' or YYYY-MM");
      if (!g.id) g.id = g.metric + "_" + i;
    });
    if (problems.length) { msg.textContent = problems.join(" · "); return; }
    active.effective_from = effectiveInput.value || active.effective_from;
    active.status = statusSelect.value;
    active.goals = goals;
    file.version = 2;
    var json = JSON.stringify(file, null, 2);
    output.value = json;
    output.hidden = false; dlBtn.hidden = false; copyBtn.hidden = false;
    msg.textContent = "Send this JSON back to update config/goals.json.";
  });
  copyBtn.addEventListener("click", function () {
    output.select();
    try { navigator.clipboard.writeText(output.value); msg.textContent = "Copied."; }
    catch (e) { document.execCommand("copy"); msg.textContent = "Copied (fallback)."; }
  });
  dlBtn.addEventListener("click", function () {
    var blob = new Blob([output.value], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "goals.json";
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
  });
})();
