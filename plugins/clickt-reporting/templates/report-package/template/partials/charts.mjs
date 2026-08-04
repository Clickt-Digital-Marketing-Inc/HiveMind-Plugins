// Inline-SVG chart builders. Presentational only — data arrives pre-derived.
// Hover layer: each line chart ships per-date hit columns + a tooltip div,
// driven by the shared runtime.js (inlined at build time).

import { esc, monthLabel } from "./fmt.mjs";

function niceTicks(max, count = 4) {
  if (max <= 0) return [0, 1];
  const step = Math.pow(10, Math.floor(Math.log10(max / count)));
  const candidates = [step, step * 2, step * 2.5, step * 5, step * 10];
  const chosen = candidates.find((c) => max / c <= count) || step * 10;
  const top = Math.ceil(max / chosen) * chosen;
  const ticks = [];
  for (let v = 0; v <= top + chosen / 2; v += chosen) ticks.push(v);
  return ticks;
}

// Two-series (max) daily trend on a single shared currency axis.
// series: [{ key: "value"|"spend", label, points: number[] }], dates: string[]
export function lineChart(id, { dates, series, locale, fmtTick, fmtTip }) {
  const W = 900, H = 250, L = 58, R = 96, T = 12, B = 28;
  const iw = W - L - R, ih = H - T - B;
  const allVals = series.flatMap((s) => s.points).filter((v) => v != null);
  const ticks = niceTicks(Math.max(...allVals, 1));
  const yMax = ticks[ticks.length - 1];
  const x = (i) => L + (dates.length === 1 ? iw / 2 : (i / (dates.length - 1)) * iw);
  const y = (v) => T + ih - (v / yMax) * ih;

  const grid = ticks
    .map((t) => `<line class="gridline" x1="${L}" y1="${y(t)}" x2="${L + iw}" y2="${y(t)}"/>` +
      `<text x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${esc(fmtTick(t))}</text>`)
    .join("");

  const nLabels = Math.min(6, dates.length);
  const labelIdx = new Set(Array.from({ length: nLabels }, (_, k) => Math.round((k / Math.max(nLabels - 1, 1)) * (dates.length - 1))));
  const xLabels = dates
    .map((d, i) => (labelIdx.has(i) ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(monthLabel(d, locale))}</text>` : ""))
    .join("");

  // End labels: resolve vertical collisions so close-ending series stay legible.
  const labelYs = series.map((s) => {
    const last = s.points[s.points.length - 1];
    return last == null ? null : y(last) + 4;
  });
  const MIN_GAP = 14;
  for (let i = 0; i < labelYs.length; i++) {
    for (let j = i + 1; j < labelYs.length; j++) {
      if (labelYs[i] == null || labelYs[j] == null) continue;
      const gap = labelYs[j] - labelYs[i];
      if (Math.abs(gap) < MIN_GAP) {
        const push = (MIN_GAP - Math.abs(gap)) / 2;
        if (gap >= 0) { labelYs[i] -= push; labelYs[j] += push; }
        else { labelYs[i] += push; labelYs[j] -= push; }
      }
    }
  }

  const paths = series
    .map((s, si) => {
      const pts = s.points.map((v, i) => (v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean);
      const last = s.points[s.points.length - 1];
      const endDot = last == null ? "" : `<circle class="dot-${s.key}" cx="${x(s.points.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="3.5"/>`;
      const endLabel = last == null ? "" : `<text class="endlabel" x="${(L + iw + 8).toFixed(1)}" y="${labelYs[si].toFixed(1)}">${esc(s.label)}</text>`;
      return `<polyline class="series-${s.key}" points="${pts.join(" ")}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>${endDot}${endLabel}`;
    })
    .join("");

  // Hover payload: one entry per date with formatted values.
  const payload = dates.map((d, i) => ({
    label: monthLabel(d, locale),
    rows: series.map((s) => ({ k: s.label, v: s.points[i] == null ? "—" : fmtTip(s.points[i]) })),
    x: Number(x(i).toFixed(1)),
  }));

  return `<div class="chart-wrap" data-chart="${esc(id)}">
<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily trend chart">
${grid}
<line class="axisline" x1="${L}" y1="${T + ih}" x2="${L + iw}" y2="${T + ih}"/>
${xLabels}
${paths}
<line class="crosshair" data-crosshair y1="${T}" y2="${T + ih}" x1="0" x2="0"/>
</svg>
<div class="tooltip" data-tooltip></div>
<script type="application/json" data-points>${JSON.stringify(payload).replace(/</g, "\\u003c")}</script>
</div>`;
}

// Horizontal funnel: monotonically decreasing steps with conversion-to-next labels.
export function funnelChart({ steps, fmtInt, fmtPct }) {
  const W = 900, rowH = 44, gap = 14, L = 150, R = 190;
  const H = steps.length * rowH + (steps.length - 1) * gap + 8;
  const maxCount = Math.max(steps[0]?.count ?? 1, 1);
  const bw = W - L - R;

  const rows = steps
    .map((s, i) => {
      const yTop = i * (rowH + gap);
      const w = Math.max((s.count / maxCount) * bw, 2);
      const next = steps[i + 1];
      const rate = next && s.count > 0 ? (next.count / s.count) * 100 : null;
      const rateLabel = rate == null ? "" :
        `<text class="funnel-count" x="${L + 4}" y="${yTop + rowH + gap - 3}">↓ ${esc(fmtPct(rate))} continue</text>`;
      return `<text class="funnel-label" x="${L - 10}" y="${yTop + rowH / 2 + 4}" text-anchor="end">${esc(s.label)}</text>
<rect class="funnel-bar" x="${L}" y="${yTop}" width="${w.toFixed(1)}" height="${rowH - 12}" rx="4"/>
<text class="funnel-count" x="${L + w + 8}" y="${yTop + rowH / 2 - 2}">${esc(fmtInt(s.count))}${s.deltaLabel ? `  ${esc(s.deltaLabel)} vs prior` : ""}</text>
${rateLabel}`;
    })
    .join("\n");

  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Purchase funnel">${rows}</svg>`;
}
