// Monthly report page assembly.

import { esc } from "./fmt.mjs";
import { lineChart, funnelChart } from "./charts.mjs";
import {
  tiles, sectionHead, unavailable, commentary, dataTable, goalRow,
  masthead, methodNotes,
} from "./components.mjs";
import {
  efficiency, efficiencyLabel, deltas, blended, activeGoalSet, goalCtx,
  resolveGoalRows, funnelSteps,
} from "./derive.mjs";

export function renderMonthly({ data, config, goals, commentaryMap, fmt, pulses = [] }) {
  const panels = [];
  const env = data.meta_envelope;
  const locale = config.client.locale;
  const b = blended(data, config);
  const goalSet = activeGoalSet(goals, env.date_range.start);
  const attainment = resolveGoalRows(goalSet, goalCtx(data, config), fmt, { monthId: env.period_id });
  const attainByKey = {};
  for (const r of attainment) if (!(r.key in attainByKey)) attainByKey[r.key] = r;
  const badges = env.partial_period ? ['<span class="badge partial">partial period</span>'] : [];
  const parts = [];

  parts.push(masthead(config, env.period_label, `Monthly Performance — ${env.period_label}`, badges));
  parts.push(`<p class="report-sub">${esc(env.date_range.start)} to ${esc(env.date_range.end)} · compared to ${esc(env.prior_range.start)}–${esc(env.prior_range.end)}${env.yoy_range ? ` and ${esc(env.yoy_range.start.slice(0, 7))} (YoY)` : ""}</p>`);

  // ---- Executive scorecard ----
  const s = data.store, g = data.google_ads, m = data.meta;
  const storeOk = s?.available !== false;
  const execTiles = [];
  if (storeOk) {
    execTiles.push(
      { label: "Store revenue", value: fmt.currency0(s.current.revenue), deltaPrior: deltas(s, "revenue").prior, deltaYoY: deltas(s, "revenue").yoy, goalAttain: attainByKey.store_revenue?.attainPct },
      ...(s.current.profit != null ? [{ label: "Store profit", value: fmt.currency0(s.current.profit), deltaPrior: deltas(s, "profit").prior, deltaYoY: deltas(s, "profit").yoy, goalAttain: attainByKey.store_profit?.attainPct }] : []),
      { label: "Orders", value: fmt.int(s.current.orders), deltaPrior: deltas(s, "orders").prior, deltaYoY: deltas(s, "orders").yoy, goalAttain: attainByKey.orders?.attainPct },
      ...(s.current.new_customers != null ? [{ label: "New customers", value: fmt.int(s.current.new_customers), deltaPrior: deltas(s, "new_customers").prior, goalAttain: attainByKey.new_customers?.attainPct }] : []),
      { label: "Conversion rate", value: fmt.pct2(s.current.conversion_rate), deltaPrior: deltas(s, "conversion_rate").prior, deltaYoY: deltas(s, "conversion_rate").yoy, goalAttain: attainByKey.conversion_rate?.attainPct },
      { label: "AOV", value: fmt.currency2(s.current.aov), deltaPrior: deltas(s, "aov").prior, deltaYoY: deltas(s, "aov").yoy, goalAttain: attainByKey.aov?.attainPct },
    );
  }
  execTiles.push({ label: b.spendComplete ? "Total ad spend" : "Ad spend (partial)", value: b.totalSpend == null ? "—" : fmt.currency0(b.totalSpend), deltaPrior: b.spendDelta, invert: true });
  execTiles.push({ label: "MER", value: fmt.ratio(b.mer), deltaPrior: b.merDelta, goalAttain: attainByKey.mer?.attainPct });
  if (b.ncac != null || attainByKey.ncac) execTiles.push({ label: "nCAC", value: fmt.currency2(b.ncac), deltaPrior: b.ncacDelta, invert: true, goalAttain: attainByKey.ncac?.attainPct });

  panels.push({ id: "exec", title: "Executive Summary", html: `<section class="section">${sectionHead("Overview", "Executive scorecard", b.spendComplete ? "" : "ad spend incomplete — see section notes")}
${tiles(execTiles, fmt)}
${commentary("exec", commentaryMap)}</section>` });

  // ---- Attainment ----
  panels.push({ id: "attainment", title: "Attainment", html: `<section class="section">${sectionHead("Goals", "Attainment", goalSet ? (goalSet.status === "proposed" ? "targets proposed — pending client agreement" : "") : "no goals configured")}
${attainment.length ? `<div class="goal-rows">${attainment.map((r) => goalRow(r)).join("\n")}</div>` : `<div class="unavailable"><div class="u-title">No goals set for this period</div><div>Set targets in the Goals section of the reporting dashboard to activate this section.</div></div>`}
${commentary("attainment", commentaryMap)}</section>` });

  // ---- Google Ads ----
  const gLabel = efficiencyLabel(config, "google_ads");
  const gHasRevenue = g?.available !== false && g?.current?.revenue != null;
  const gBasis = config.sections.google_ads.conversion_value_is === "profit"
    ? (gHasRevenue ? "Primary conversion value = profit (POAS) · revenue stream shown alongside (ROAS)" : "Conversion value = profit · efficiency shown as POAS")
    : "Conversion value = revenue · efficiency shown as ROAS";
  if (g?.available === false) {
    panels.push({ id: "google", title: "Google Ads", html: `<section class="section">${sectionHead("Paid Search", "Google Ads", gBasis)}${unavailable("Google Ads", g.unavailable_reason)}${commentary("google_ads", commentaryMap)}</section>` });
  } else if (g) {
    const gd = (f) => deltas(g, f);
    const poas = efficiency(g.current.spend, g.current.conversion_value);
    const priorPoas = efficiency(g.prior?.spend, g.prior?.conversion_value);
    const gRoas = gHasRevenue ? efficiency(g.current.spend, g.current.revenue) : null;
    const gPriorRoas = gHasRevenue ? efficiency(g.prior?.spend, g.prior?.revenue) : null;
    const gTiles = [
      { label: "Spend", value: fmt.currency0(g.current.spend), deltaPrior: gd("spend").prior, invert: true },
      ...(gHasRevenue ? [{ label: "Revenue", value: fmt.currency0(g.current.revenue), deltaPrior: gd("revenue").prior }] : []),
      { label: gLabel === "POAS" ? "Profit (conv. value)" : "Revenue (conv. value)", value: fmt.currency0(g.current.conversion_value), deltaPrior: gd("conversion_value").prior, deltaYoY: gd("conversion_value").yoy },
      ...(gRoas != null ? [{ label: "ROAS", value: fmt.ratio(gRoas), deltaPrior: gPriorRoas ? ((gRoas - gPriorRoas) / gPriorRoas) * 100 : null }] : []),
      { label: gLabel, value: fmt.ratio(poas), deltaPrior: priorPoas ? ((poas - priorPoas) / priorPoas) * 100 : null, goalAttain: attainByKey.google_poas?.attainPct },
      { label: "Conversions", value: fmt.int(g.current.conversions), deltaPrior: gd("conversions").prior },
      { label: "Clicks", value: fmt.int(g.current.clicks), deltaPrior: gd("clicks").prior },
      { label: "CPC", value: fmt.currency2(g.current.cpc), deltaPrior: gd("cpc").prior, invert: true },
    ];
    const gChart = g.trend?.length
      ? `<div class="chart-card"><div class="chart-title">Daily spend vs ${gLabel === "POAS" ? "profit" : "revenue"}<span class="legend"><span class="key"><span class="swatch value"></span>${gLabel === "POAS" ? "Profit" : "Revenue"}</span><span class="key"><span class="swatch spend"></span>Spend</span></span></div>
${lineChart("google-trend", { dates: g.trend.map((d) => d.date), locale, fmtTick: fmt.compactCur, fmtTip: fmt.currency2, series: [
  { key: "value", label: gLabel === "POAS" ? "Profit" : "Revenue", points: g.trend.map((d) => d.conversion_value) },
  { key: "spend", label: "Spend", points: g.trend.map((d) => d.spend) },
] })}</div>` : "";
    const gTable = g.campaigns?.length
      ? dataTable([
          { key: "name", label: "Campaign" },
          { key: "spend", label: "Spend", format: (v, f) => f.currency0(v) },
          { key: "clicks", label: "Clicks", format: (v, f) => f.int(v) },
          { key: "conversions", label: "Conv.", format: (v, f) => f.int(v) },
          { key: "conversion_value", label: gLabel === "POAS" ? "Profit" : "Rev.", format: (v, f) => f.currency0(v) },
          { key: "_eff", label: gLabel, format: (v, f) => f.ratio(v) },
        ], g.campaigns.map((c) => ({ ...c, _eff: efficiency(c.spend, c.conversion_value) })), fmt)
      : "";
    panels.push({ id: "google", title: "Google Ads", html: `<section class="section">${sectionHead("Paid Search", "Google Ads", gBasis)}
${tiles(gTiles, fmt)}${gChart}${gTable}
${commentary("google_ads", commentaryMap)}</section>` });
  }

  // ---- Meta Ads ----
  if (m?.available === false) {
    panels.push({ id: "meta", title: "Meta Ads", html: `<section class="section">${sectionHead("Paid Social", "Meta Ads", "Purchase value = revenue · ROAS")}${unavailable("Meta Ads", m.unavailable_reason)}${commentary("meta", commentaryMap)}</section>` });
  } else if (m) {
    const md = (f) => deltas(m, f);
    const roas = efficiency(m.current.spend, m.current.revenue);
    const priorRoas = efficiency(m.prior?.spend, m.prior?.revenue);
    const mHasProfit = m.current.profit != null;
    const mPoas = mHasProfit ? efficiency(m.current.spend, m.current.profit) : null;
    const mPriorPoas = mHasProfit ? efficiency(m.prior?.spend, m.prior?.profit) : null;
    const mTiles = [
      { label: "Spend", value: fmt.currency0(m.current.spend), deltaPrior: md("spend").prior, invert: true },
      { label: "Revenue", value: fmt.currency0(m.current.revenue), deltaPrior: md("revenue").prior, deltaYoY: md("revenue").yoy },
      ...(mHasProfit
        ? [{ label: "Profit", value: fmt.currency0(m.current.profit), deltaPrior: md("profit").prior }]
        : [{ label: "Profit", value: "—", note: "not tracked on Meta — see method notes" }]),
      { label: "ROAS", value: fmt.ratio(roas), deltaPrior: priorRoas ? ((roas - priorRoas) / priorRoas) * 100 : null, goalAttain: attainByKey.meta_roas?.attainPct },
      ...(mPoas != null ? [{ label: "POAS", value: fmt.ratio(mPoas), deltaPrior: mPriorPoas ? ((mPoas - mPriorPoas) / mPriorPoas) * 100 : null }] : []),
      { label: "Purchases", value: fmt.int(m.current.purchases), deltaPrior: md("purchases").prior },
      { label: "Reach", value: fmt.int(m.current.reach), deltaPrior: md("reach").prior },
      { label: "Frequency", value: (m.current.frequency ?? 0).toFixed(2), deltaPrior: md("frequency").prior, invert: true },
    ];
    const mChart = m.trend?.length
      ? `<div class="chart-card"><div class="chart-title">Daily spend vs revenue<span class="legend"><span class="key"><span class="swatch value"></span>Revenue</span><span class="key"><span class="swatch spend"></span>Spend</span></span></div>
${lineChart("meta-trend", { dates: m.trend.map((d) => d.date), locale, fmtTick: fmt.compactCur, fmtTip: fmt.currency2, series: [
  { key: "value", label: "Revenue", points: m.trend.map((d) => d.revenue) },
  { key: "spend", label: "Spend", points: m.trend.map((d) => d.spend) },
] })}</div>` : "";
    const mTable = m.campaigns?.length
      ? dataTable([
          { key: "name", label: "Campaign" },
          { key: "spend", label: "Spend", format: (v, f) => f.currency0(v) },
          { key: "clicks", label: "Clicks", format: (v, f) => f.int(v) },
          { key: "purchases", label: "Purchases", format: (v, f) => f.int(v) },
          { key: "revenue", label: "Revenue", format: (v, f) => f.currency0(v) },
          { key: "_eff", label: "ROAS", format: (v, f) => f.ratio(v) },
        ], m.campaigns.map((c) => ({ ...c, _eff: efficiency(c.spend, c.revenue) })), fmt)
      : "";
    panels.push({ id: "meta", title: "Meta Ads", html: `<section class="section">${sectionHead("Paid Social", "Meta Ads", mHasProfit ? "Purchase value = revenue (ROAS) · profit via registration event (POAS)" : "Purchase value = revenue · ROAS")}
${tiles(mTiles, fmt)}${mChart}${mTable}
${commentary("meta", commentaryMap)}</section>` });
  }

  // ---- Store performance (CRO) ----
  const t = data.traffic;
  if (s?.available === false) {
    panels.push({ id: "store", title: "Store", html: `<section class="section">${sectionHead("Store", "Store performance", "")}${unavailable("Store", s.unavailable_reason)}${commentary("store", commentaryMap)}</section>` });
  } else if (s) {
    const sChart = s.trend?.length
      ? `<div class="chart-card"><div class="chart-title">Daily store revenue</div>
${lineChart("store-trend", { dates: s.trend.map((d) => d.date), locale, fmtTick: fmt.compactCur, fmtTip: fmt.currency2, series: [
  { key: "value", label: "Revenue", points: s.trend.map((d) => d.revenue) },
] })}</div>` : "";
    const funnel = funnelSteps(t, fmt);
    const funnelHtml = funnel
      ? `<div class="chart-card"><div class="chart-title">Purchase funnel — ${esc(env.period_label)}</div>${funnelChart({ steps: funnel, fmtInt: fmt.int, fmtPct: fmt.pct1 })}</div>`
      : (t?.available === false ? unavailable("Funnel & channels", t.unavailable_reason) : "");
    const channelsHtml = t?.available !== false && t?.channels?.length
      ? dataTable([
          { key: "channel", label: "Channel" },
          { key: "sessions", label: "Sessions", format: (v, f) => f.int(v) },
          { key: "conversion_rate", label: "Conv. rate", format: (v, f) => f.pct2(v) },
          { key: "revenue", label: "Revenue", format: (v, f) => f.currency0(v) },
        ], t.channels, fmt)
      : "";
    const productsHtml = s.top_products?.length
      ? dataTable([
          { key: "title", label: "Top products" },
          { key: "units", label: "Units", format: (v, f) => f.int(v) },
          { key: "revenue", label: "Revenue", format: (v, f) => f.currency0(v) },
        ], s.top_products, fmt)
      : "";
    const sTiles = [
      { label: "Sessions", value: fmt.int(s.current.sessions), deltaPrior: deltas(s, "sessions").prior, deltaYoY: deltas(s, "sessions").yoy },
      { label: "Orders", value: fmt.int(s.current.orders), deltaPrior: deltas(s, "orders").prior },
      { label: "Conversion rate", value: fmt.pct2(s.current.conversion_rate), deltaPrior: deltas(s, "conversion_rate").prior },
      { label: "AOV", value: fmt.currency2(s.current.aov), deltaPrior: deltas(s, "aov").prior },
      { label: "Revenue", value: fmt.currency0(s.current.revenue), deltaPrior: deltas(s, "revenue").prior },
    ];
    panels.push({ id: "store", title: "Store", html: `<section class="section">${sectionHead("Store", "Store performance", "")}
${tiles(sTiles, fmt)}${sChart}${funnelHtml}${channelsHtml}${productsHtml}
${commentary("store", commentaryMap)}</section>` });
  }

  // ---- Weekly Pulses tab (dropdown + inline embed of sibling pulse pages) ----
  const pulsesHtml = pulses.length
    ? `<div class="pulse-picker"><label for="pulse-select">Week</label><select id="pulse-select" data-pulse-select>${pulses
        .map((pl, i) => `<option value="${esc(pl.file)}"${i === 0 ? " selected" : ""}>${esc(pl.label)} (${esc(pl.range.start)} – ${esc(pl.range.end)})</option>`)
        .join("")}</select><a class="pulse-open" data-pulse-open href="${esc(pulses[0].file)}" target="_blank" rel="noopener">Open full page ↗</a></div>
<iframe class="pulse-frame" data-pulse-frame data-lazy-src="${esc(pulses[0].file)}" title="Weekly pulse"></iframe>`
    : `<div class="unavailable"><div class="u-title">No weekly pulses yet</div><div>Weekly pulses appear here as they are published.</div></div>`;
  panels.push({ id: "pulses", title: "Weekly Pulses", html: `<section class="section">${sectionHead("Weekly", "Weekly pulses", pulses.length ? `${pulses.length} available` : "")}
${pulsesHtml}</section>` });

  // ---- Tab shell ----
  parts.push(`<nav class="tabs" role="tablist" aria-label="Report sections">${panels
    .map((p, i) => `<button class="tab${i === 0 ? " active" : ""}" role="tab" id="tab-${p.id}" aria-controls="panel-${p.id}" aria-selected="${i === 0}" data-tab="${p.id}">${esc(p.title)}</button>`)
    .join("")}</nav>`);
  parts.push(panels
    .map((p, i) => `<div class="tab-panel${i === 0 ? " active" : ""}" role="tabpanel" id="panel-${p.id}" aria-labelledby="tab-${p.id}">${p.html}</div>`)
    .join("\n"));

  // ---- Method notes ----
  const notes = [
    config.sections.google_ads.conversion_value_is === "profit"
      ? "<b>Google Ads conversion value is configured as profit</b> — efficiency renders as POAS (profit ÷ spend), not ROAS. Never compared 1:1 with Meta ROAS."
      : "Google Ads conversion value is revenue; efficiency renders as ROAS.",
    "Meta purchase value is revenue (Meta-attributed); ROAS = revenue ÷ spend.",
    "MER = store revenue ÷ total ad spend — platform-agnostic; the only blended efficiency metric in this report.",
    "Attribution differs by platform; channel numbers do not sum to store totals.",
    `Sources: ${Object.entries(env.sources).map(([k, v]) => `${esc(k)} — ${esc(v)}`).join(" · ")}. Pulled ${esc(env.pulled_at)}.`,
  ];
  if (goalSet?.status === "proposed") notes.push("Goal targets are proposed and pending client agreement.");
  if (gHasRevenue) notes.push("Google revenue is the account's revenue-based conversion actions (same Google attribution as the profit stream); Google ROAS = revenue ÷ spend, POAS = profit ÷ spend.");
  if (m?.available !== false && m) notes.push(m.current?.profit != null
    ? "Meta profit is the ProfitMetrics profit value carried on the complete-registration event (Meta attribution); Meta POAS = profit ÷ spend."
    : "Meta profit is not tracked — the ad account has no profit conversion event. Profit is shown only where a platform reports it; it is never estimated.");
  if (b.ncac != null) notes.push("nCAC = total ad spend ÷ store new customers (first-time purchasers). Blended across channels, like MER.");
  if (storeOk && s.current.profit != null) notes.push("Store profit comes from the profit-tracking analytics property (ProfitMetrics), same source family as store revenue.");
  for (const n of env.method_notes ?? []) notes.push(esc(n));
  parts.push(methodNotes(notes));

  parts.push(`<footer class="footer"><span>Prepared by ${esc(config.agency.legal_name)}</span><span>${esc(config.client.website)}</span></footer>`);

  return parts.join("\n");
}
