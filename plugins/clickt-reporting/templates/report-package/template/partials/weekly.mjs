// Weekly pulse — dated one-pager: WoW scorecard, one mini trend, MTD pace, one commentary slot.

import { esc } from "./fmt.mjs";
import { lineChart } from "./charts.mjs";
import { tiles, sectionHead, commentary, goalRow, masthead, methodNotes, unavailable } from "./components.mjs";
import { efficiency, efficiencyLabel, deltas, blended, activeGoalSet, goalCtx, resolveGoalRows } from "./derive.mjs";

function daysBetween(a, b) {
  return Math.round((new Date(b + "T00:00:00Z") - new Date(a + "T00:00:00Z")) / 86400000) + 1;
}
function daysInMonthOf(dateStr) {
  const [y, m] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

export function renderWeekly({ data, config, goals, commentaryMap, fmt }) {
  const env = data.meta_envelope;
  const locale = config.client.locale;
  const b = blended(data, config);
  const parts = [];

  parts.push(masthead(config, env.period_label, `Weekly Pulse — ${env.period_label}`, []));
  parts.push(`<p class="report-sub">${esc(env.date_range.start)} to ${esc(env.date_range.end)} · vs prior week ${esc(env.prior_range.start)}–${esc(env.prior_range.end)}</p>`);

  // ---- Scorecard (WoW) ----
  const s = data.store, g = data.google_ads, m = data.meta;
  const wk = [];
  if (s?.available !== false && s) {
    wk.push(
      { label: "Store revenue", value: fmt.currency0(s.current.revenue), deltaPrior: deltas(s, "revenue").prior, priorLabel: "WoW" },
      ...(s.current.profit != null ? [{ label: "Store profit", value: fmt.currency0(s.current.profit), deltaPrior: deltas(s, "profit").prior, priorLabel: "WoW" }] : []),
      { label: "Orders", value: fmt.int(s.current.orders), deltaPrior: deltas(s, "orders").prior, priorLabel: "WoW" },
      ...(s.current.new_customers != null ? [{ label: "New customers", value: fmt.int(s.current.new_customers), deltaPrior: deltas(s, "new_customers").prior, priorLabel: "WoW" }] : []),
      { label: "Conversion rate", value: fmt.pct2(s.current.conversion_rate), deltaPrior: deltas(s, "conversion_rate").prior, priorLabel: "WoW" },
    );
  }
  if (g?.available !== false && g) {
    const poas = efficiency(g.current.spend, g.current.conversion_value);
    const priorPoas = efficiency(g.prior?.spend, g.prior?.conversion_value);
    wk.push({ label: `Google ${efficiencyLabel(config, "google_ads")}`, value: fmt.ratio(poas), deltaPrior: priorPoas ? ((poas - priorPoas) / priorPoas) * 100 : null, priorLabel: "WoW" });
  }
  if (m?.available !== false && m) {
    const roas = efficiency(m.current.spend, m.current.revenue);
    const priorRoas = efficiency(m.prior?.spend, m.prior?.revenue);
    wk.push({ label: "Meta ROAS", value: fmt.ratio(roas), deltaPrior: priorRoas ? ((roas - priorRoas) / priorRoas) * 100 : null, priorLabel: "WoW" });
    if (m.current.profit != null) {
      const mPoas = efficiency(m.current.spend, m.current.profit);
      const mPriorPoas = efficiency(m.prior?.spend, m.prior?.profit);
      wk.push({ label: "Meta POAS", value: fmt.ratio(mPoas), deltaPrior: mPriorPoas ? ((mPoas - mPriorPoas) / mPriorPoas) * 100 : null, priorLabel: "WoW" });
    }
  }
  wk.push({ label: b.spendComplete ? "Total ad spend" : "Ad spend (partial)", value: b.totalSpend == null ? "—" : fmt.currency0(b.totalSpend), deltaPrior: b.spendDelta, priorLabel: "WoW", invert: true });
  if (b.ncac != null) wk.push({ label: "nCAC", value: fmt.currency2(b.ncac), deltaPrior: b.ncacDelta, priorLabel: "WoW", invert: true });

  parts.push(`<section class="section">${sectionHead("This week", "Scorecard", "")}
${tiles(wk, fmt)}</section>`);

  // ---- Mini trend: store revenue daily (fallback: meta revenue) ----
  const trendSrc = s?.trend?.length ? { label: "Store revenue", trend: s.trend.map((d) => ({ date: d.date, v: d.revenue })) }
    : m?.trend?.length ? { label: "Meta revenue", trend: m.trend.map((d) => ({ date: d.date, v: d.revenue })) } : null;
  if (trendSrc) {
    parts.push(`<section class="section">${sectionHead("Trend", "Daily revenue", "")}
<div class="chart-card"><div class="chart-title">${esc(trendSrc.label)} — this week</div>
${lineChart("pulse-trend", { dates: trendSrc.trend.map((d) => d.date), locale, fmtTick: fmt.compactCur, fmtTip: fmt.currency2, series: [
  { key: "value", label: trendSrc.label, points: trendSrc.trend.map((d) => d.v) },
] })}</div></section>`);
  }

  // ---- Month-to-date pace vs goal ----
  const mtd = env.mtd;
  if (mtd?.range) {
    const goalSet = activeGoalSet(goals, mtd.range.start);
    if (goalSet) {
      const elapsed = daysBetween(mtd.range.start, mtd.range.end);
      const dim = daysInMonthOf(mtd.range.start);
      const paceFraction = Math.min(elapsed / dim, 1);
      const mtdActuals = {
        store_revenue: mtd.store_revenue ?? null,
        total_ad_spend: mtd.total_ad_spend ?? null,
        orders: mtd.orders ?? null,
        new_customers: mtd.new_customers ?? null,
        mer: mtd.total_ad_spend ? (mtd.store_revenue ?? 0) / mtd.total_ad_spend : null,
        ncac: mtd.total_ad_spend && mtd.new_customers ? mtd.total_ad_spend / mtd.new_customers : null,
      };
      const rows = resolveGoalRows(goalSet, goalCtx(data, config), fmt,
        { monthId: mtd.range.start.slice(0, 7), paceFraction, mtdActuals });
      if (rows.length) {
        parts.push(`<section class="section">${sectionHead("Goals", "Month-to-date pace", `day ${daysBetween(mtd.range.start, mtd.range.end)} of ${daysInMonthOf(mtd.range.start)}${goalSet.status === "proposed" ? " · targets proposed" : ""}`)}
<div class="goal-rows">${rows.map((r) => goalRow(r)).join("\n")}</div></section>`);
      }
    }
  } else {
    parts.push(`<section class="section">${sectionHead("Goals", "Month-to-date pace", "")}${unavailable("Pace", "No month-to-date data in this pull.")}</section>`);
  }

  parts.push(commentary("pulse", commentaryMap));

  parts.push(methodNotes([
    config.sections.google_ads.conversion_value_is === "profit"
      ? "Google Ads conversion value = profit → POAS. Meta value = revenue → ROAS. Never blended."
      : "Google and Meta efficiency both revenue-based ROAS.",
    `Sources: ${Object.entries(env.sources).map(([k, v]) => `${esc(k)} — ${esc(v)}`).join(" · ")}. Pulled ${esc(env.pulled_at)}.`,
    ...(env.method_notes ?? []).map((n) => esc(n)),
  ]));
  parts.push(`<footer class="footer"><span>Prepared by ${esc(config.agency.legal_name)}</span><span>${esc(config.client.website)}</span></footer>`);
  return parts.join("\n");
}
