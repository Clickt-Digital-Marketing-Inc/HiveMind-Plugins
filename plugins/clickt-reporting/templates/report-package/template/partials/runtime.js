// Tooltip + crosshair runtime for line charts. Inlined into the report at build
// time; no external requests. Progressive: charts render fully without it.
(function () {
  document.querySelectorAll("[data-chart]").forEach(function (wrap) {
    var svg = wrap.querySelector("svg");
    var tip = wrap.querySelector("[data-tooltip]");
    var cross = wrap.querySelector("[data-crosshair]");
    var payloadEl = wrap.querySelector("[data-points]");
    if (!svg || !tip || !payloadEl) return;
    var points;
    try { points = JSON.parse(payloadEl.textContent); } catch (e) { return; }
    if (!points.length) return;

    function svgX(evt) {
      var rect = svg.getBoundingClientRect();
      var vb = svg.viewBox.baseVal;
      return ((evt.clientX - rect.left) / rect.width) * vb.width;
    }
    function nearest(px) {
      var best = 0, bd = Infinity;
      for (var i = 0; i < points.length; i++) {
        var d = Math.abs(points[i].x - px);
        if (d < bd) { bd = d; best = i; }
      }
      return points[best];
    }
    svg.addEventListener("mousemove", function (evt) {
      var p = nearest(svgX(evt));
      if (cross) {
        cross.style.display = "block";
        cross.setAttribute("x1", p.x);
        cross.setAttribute("x2", p.x);
      }
      var html = '<div class="t-date">' + p.label + "</div>";
      for (var i = 0; i < p.rows.length; i++)
        html += '<div class="t-row"><span class="k">' + p.rows[i].k + "</span><span>" + p.rows[i].v + "</span></div>";
      tip.innerHTML = html;
      tip.style.display = "block";
      var rect = wrap.getBoundingClientRect();
      var left = evt.clientX - rect.left + 14;
      if (left + tip.offsetWidth > rect.width) left = evt.clientX - rect.left - tip.offsetWidth - 14;
      tip.style.left = left + "px";
      tip.style.top = (evt.clientY - rect.top - 10) + "px";
    });
    svg.addEventListener("mouseleave", function () {
      tip.style.display = "none";
      if (cross) cross.style.display = "none";
    });
  });
})();

// Tab switcher (monthly report). Hash-deep-linkable; print CSS shows all panels.
(function () {
  var tabs = document.querySelectorAll(".tabs .tab");
  if (!tabs.length) return;
  function activate(id, push) {
    document.querySelectorAll(".tabs .tab").forEach(function (t) {
      var on = t.getAttribute("data-tab") === id;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach(function (p) {
      p.classList.toggle("active", p.id === "panel-" + id);
    });
    if (push) history.replaceState(null, "", "#" + id);
    // Lazy-load embeds in the newly shown panel (e.g. the weekly-pulse iframe).
    var panel = document.getElementById("panel-" + id);
    if (panel) panel.querySelectorAll("iframe[data-lazy-src]").forEach(function (f) {
      f.src = f.getAttribute("data-lazy-src");
      f.removeAttribute("data-lazy-src");
    });
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { activate(t.getAttribute("data-tab"), true); });
  });
  var initial = (location.hash || "").slice(1);
  if (initial && document.getElementById("panel-" + initial)) activate(initial, false);
})();

// Weekly-pulse picker: dropdown swaps the embedded pulse; same-origin height sync.
(function () {
  var sel = document.querySelector("[data-pulse-select]");
  var frame = document.querySelector("[data-pulse-frame]");
  var open = document.querySelector("[data-pulse-open]");
  if (!sel || !frame) return;
  sel.addEventListener("change", function () {
    frame.src = sel.value;
    if (open) open.href = sel.value;
  });
  frame.addEventListener("load", function () {
    try {
      var h = frame.contentDocument.documentElement.scrollHeight;
      if (h > 400) frame.style.height = h + 40 + "px";
    } catch (e) { /* cross-origin fallback: keep min-height */ }
  });
})();
