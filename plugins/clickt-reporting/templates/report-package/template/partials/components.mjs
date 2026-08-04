// Shared page components. Everything returns an HTML string; all dynamic
// strings pass through esc().

import { esc } from "./fmt.mjs";

export function deltaChip(deltaPct, fmt, { label = "", invert = false } = {}) {
  if (deltaPct == null || !Number.isFinite(deltaPct)) return `<span class="chip flat">— ${esc(label)}</span>`;
  const good = invert ? deltaPct < 0 : deltaPct > 0;
  const cls = Math.abs(deltaPct) < 0.05 ? "flat" : good ? "up" : "down";
  const arrow = deltaPct > 0 ? "▲" : deltaPct < 0 ? "▼" : "•";
  return `<span class="chip ${cls}">${arrow} ${esc(fmt.delta(deltaPct))}${label ? ` ${esc(label)}` : ""}</span>`;
}

export function goalChip(attainPct) {
  if (attainPct == null) return `<span class="chip goal-na">no goal</span>`;
  const cls = attainPct >= 100 ? "goal-on" : "goal-off";
  return `<span class="chip ${cls}">${attainPct >= 100 ? "goal met" : `${Math.round(attainPct)}% of goal`}</span>`;
}

// tile: { label, value, unit?, deltaPrior?, deltaYoY?, goalAttain?, invert? }
export function kpiTile(t, fmt) {
  const compare = [
    t.deltaPrior !== undefined ? deltaChip(t.deltaPrior, fmt, { label: t.priorLabel ?? "vs prior", invert: t.invert }) : "",
    t.deltaYoY !== undefined && t.deltaYoY !== null ? deltaChip(t.deltaYoY, fmt, { label: "YoY", invert: t.invert }) : "",
    t.goalAttain !== undefined ? goalChip(t.goalAttain) : "",
    t.note ? `<span class="tile-note">${esc(t.note)}</span>` : "",
  ].filter(Boolean).join(" ");
  return `<div class="tile">
<div class="label">${esc(t.label)}</div>
<div class="value">${esc(t.value)}${t.unit ? `<span class="unit"> ${esc(t.unit)}</span>` : ""}</div>
<div class="compare">${compare}</div>
</div>`;
}

export function tiles(list, fmt) {
  return `<div class="tiles">${list.map((t) => kpiTile(t, fmt)).join("\n")}</div>`;
}

export function sectionHead(kicker, title, basis = "") {
  return `<div class="section-head"><span class="kicker">${esc(kicker)}</span><h2>${esc(title)}</h2>${basis ? `<span class="basis">${esc(basis)}</span>` : ""}</div>`;
}

export function unavailable(sectionName, reason) {
  return `<div class="unavailable"><div class="u-title">${esc(sectionName)} data unavailable this period</div><div>${esc(reason || "Source could not be pulled. Numbers are never approximated.")}</div></div>`;
}

// Minimal markdown: paragraphs, **bold**, *italic*, "- " lists.
function miniMd(text) {
  const inline = (s) => esc(s).replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\*([^*]+)\*/g, "<i>$1</i>");
  const blocks = text.trim().split(/\n\s*\n/);
  return blocks
    .map((b) => {
      const lines = b.split("\n");
      if (lines.every((l) => l.trim().startsWith("- ")))
        return `<ul>${lines.map((l) => `<li>${inline(l.trim().slice(2))}</li>`).join("")}</ul>`;
      return `<p>${inline(b)}</p>`;
    })
    .join("\n");
}

export function commentary(sectionId, commentaryMap) {
  const text = commentaryMap?.[sectionId];
  if (!text || !text.trim())
    return `<div class="commentary pending"><div class="c-label">Commentary</div><p>Commentary to follow.</p></div>`;
  return `<div class="commentary"><div class="c-label">Commentary</div>${miniMd(text)}</div>`;
}

// columns: [{ key, label, format }]
export function dataTable(columns, rows, fmt) {
  const head = columns.map((c) => `<th>${esc(c.label)}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${columns.map((c) => `<td>${c.format ? esc(c.format(r[c.key], fmt)) : esc(r[c.key])}</td>`).join("")}</tr>`)
    .join("\n");
  return `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

// row: { name, actualLabel, goalLabel, attainPct (may exceed 100), proposed }
export function goalRow(row) {
  const capped = Math.min(row.attainPct ?? 0, 130);
  const fillCls = row.attainPct >= 100 ? "over" : "under";
  const goalPos = Math.min((100 / 130) * 100, 100);
  return `<div class="goal-row">
<div class="name">${esc(row.name)}${row.proposed ? ` <span class="badge proposed">proposed</span>` : ""}</div>
<div class="meter"><div class="fill ${fillCls}" style="width:${((capped / 130) * 100).toFixed(1)}%"></div><div class="goal-tick" style="left:${goalPos.toFixed(1)}%"></div></div>
<div class="nums"><b>${esc(row.actualLabel)}</b> / ${esc(row.goalLabel)} · ${row.attainPct == null ? "—" : `${Math.round(row.attainPct)}%`}</div>
</div>`;
}

export function masthead(config, periodLabel, subtitle, badges = []) {
  return `<header class="masthead">
<div class="brand"><span class="dot"></span>${esc(config.agency.name)} · Performance Reporting</div>
<div class="meta">${esc(config.client.name)} · ${esc(periodLabel)}</div>
</header>
<div class="report-title">
<h1>${esc(config.client.name)} — ${esc(subtitle)} ${badges.join(" ")}</h1>
</div>`;
}

export function methodNotes(items) {
  return `<section class="method"><h2>Method notes</h2><ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul></section>`;
}
