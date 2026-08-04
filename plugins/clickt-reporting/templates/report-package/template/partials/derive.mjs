// Engine-side derivations. Adapters never precompute these (see CONTRACT.md).

import { pctChange } from "./fmt.mjs";

export function efficiency(spend, value) {
  if (spend == null || value == null || spend === 0) return null;
  return value / spend;
}

export function efficiencyLabel(config, section) {
  return config.sections[section]?.conversion_value_is === "profit" ? "POAS" : "ROAS";
}

// For a metrics block ({current, prior, yoy}): % deltas for every numeric field.
export function deltas(block, field) {
  if (!block?.current) return { prior: null, yoy: null };
  return {
    prior: pctChange(block.current[field], block.prior?.[field]),
    yoy: block.yoy ? pctChange(block.current[field], block.yoy[field]) : null,
  };
}

// MER is only honest when EVERY enabled ad channel's spend is present — a
// missing channel would silently shrink the denominator. Incomplete → mer null.
export function blended(data, config) {
  const enabled = (k) => config?.sections?.[k]?.enabled !== false;
  const channels = ["google_ads", "meta"].filter(enabled);
  const spendOf = (b, periodKey) => (b?.available !== false && b?.[periodKey] ? b[periodKey].spend : null);

  const spends = channels.map((k) => spendOf(data[k], "current"));
  const known = spends.filter((v) => v != null);
  const totalSpend = known.length ? known.reduce((a, v) => a + v, 0) : null;
  const spendComplete = spends.every((v) => v != null);
  const rev = data.store?.available !== false ? data.store?.current?.revenue ?? null : null;
  const mer = spendComplete && totalSpend > 0 && rev != null ? rev / totalSpend : null;

  const priorSpends = channels.map((k) => spendOf(data[k], "prior"));
  const priorKnown = priorSpends.filter((v) => v != null);
  const priorSpend = priorKnown.length ? priorKnown.reduce((a, v) => a + v, 0) : null;
  const priorComplete = priorSpends.every((v) => v != null);
  const priorRev = data.store?.available !== false ? data.store?.prior?.revenue ?? null : null;
  const priorMer = priorComplete && priorSpend > 0 && priorRev != null ? priorRev / priorSpend : null;

  // nCAC = total ad spend / store new customers — same completeness rule as MER.
  const nc = data.store?.available !== false ? data.store?.current?.new_customers ?? null : null;
  const priorNc = data.store?.available !== false ? data.store?.prior?.new_customers ?? null : null;
  const ncac = spendComplete && totalSpend > 0 && nc ? totalSpend / nc : null;
  const priorNcac = priorComplete && priorSpend > 0 && priorNc ? priorSpend / priorNc : null;

  return { totalSpend, mer, priorSpend, priorMer, spendComplete, ncac, priorNcac,
    ncacDelta: pctChange(ncac, priorNcac),
    merDelta: pctChange(mer, priorMer), spendDelta: spendComplete && priorComplete ? pctChange(totalSpend, priorSpend) : null };
}

// Latest goal set whose effective_from <= period start.
export function activeGoalSet(goals, periodStartDate) {
  const sets = (goals?.goal_sets ?? [])
    .filter((g) => g.effective_from <= periodStartDate)
    .sort((a, b) => (a.effective_from < b.effective_from ? 1 : -1));
  return sets[0] ?? null;
}

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const blockOk = (b) => b && b.available !== false;

// ---- Metric catalog ----------------------------------------------------------
// Every goal references a metric id. `resolve(ctx, goal)` returns the actual for
// the current period (null = no data → row renders without judgment).
// kind: "volume" pro-rates for MTD pace; "rate" holds steady.
// ctx = { data, s, g, m, b } (blocks pre-checked for availability; b = blended()).
function matchSku(s, goal) {
  if (!blockOk(s) || !goal?.sku_match) return null;
  const q = goal.sku_match.toLowerCase();
  const pools = [...(s.sku_metrics ?? []), ...(s.top_products ?? [])];
  return pools.find((p) => (p.title ?? "").toLowerCase().includes(q)) ?? null;
}

export const METRICS = {
  store_revenue:   { label: "Store revenue",    fmt: "currency0", kind: "volume", resolve: ({ s }) => (blockOk(s) ? num(s.current?.revenue) : null) },
  store_profit:    { label: "Store profit",     fmt: "currency0", kind: "volume", resolve: ({ s }) => (blockOk(s) ? num(s.current?.profit) : null) },
  orders:          { label: "Orders",           fmt: "int",       kind: "volume", resolve: ({ s }) => (blockOk(s) ? num(s.current?.orders) : null) },
  new_customers:   { label: "New customers",    fmt: "int",       kind: "volume", resolve: ({ s }) => (blockOk(s) ? num(s.current?.new_customers) : null) },
  sessions:        { label: "Sessions",         fmt: "int",       kind: "volume", resolve: ({ s }) => (blockOk(s) ? num(s.current?.sessions) : null) },
  conversion_rate: { label: "Conversion rate",  fmt: "pct2",      kind: "rate",   resolve: ({ s }) => (blockOk(s) ? num(s.current?.conversion_rate) : null) },
  aov:             { label: "AOV",              fmt: "currency2", kind: "rate",   resolve: ({ s }) => (blockOk(s) ? num(s.current?.aov) : null) },
  total_ad_spend:  { label: "Ad spend (budget)",fmt: "currency0", kind: "volume", mode: "budget", resolve: ({ b }) => (b.spendComplete ? b.totalSpend : null) },
  mer:             { label: "MER",              fmt: "ratio",     kind: "rate",   resolve: ({ b }) => b.mer },
  ncac:            { label: "nCAC",             fmt: "currency2", kind: "rate",   direction: "lower", resolve: ({ b }) => b.ncac },
  google_spend:    { label: "Google Ads spend", fmt: "currency0", kind: "volume", mode: "budget", resolve: ({ g }) => (blockOk(g) ? num(g.current?.spend) : null) },
  google_profit:   { label: "Google Ads profit",fmt: "currency0", kind: "volume", resolve: ({ g }) => (blockOk(g) ? num(g.current?.conversion_value) : null) },
  google_revenue:  { label: "Google Ads revenue",fmt: "currency0",kind: "volume", resolve: ({ g }) => (blockOk(g) ? num(g.current?.revenue) : null) },
  google_poas:     { label: "Google Ads POAS",  fmt: "ratio",     kind: "rate",   resolve: ({ g }) => (blockOk(g) ? efficiency(num(g.current?.spend), num(g.current?.conversion_value)) : null) },
  google_roas:     { label: "Google Ads ROAS",  fmt: "ratio",     kind: "rate",   resolve: ({ g }) => (blockOk(g) ? efficiency(num(g.current?.spend), num(g.current?.revenue)) : null) },
  meta_spend:      { label: "Meta spend",       fmt: "currency0", kind: "volume", mode: "budget", resolve: ({ m }) => (blockOk(m) ? num(m.current?.spend) : null) },
  meta_revenue:    { label: "Meta revenue",     fmt: "currency0", kind: "volume", resolve: ({ m }) => (blockOk(m) ? num(m.current?.revenue) : null) },
  meta_profit:     { label: "Meta profit",      fmt: "currency0", kind: "volume", resolve: ({ m }) => (blockOk(m) ? num(m.current?.profit) : null) },
  meta_roas:       { label: "Meta ROAS",        fmt: "ratio",     kind: "rate",   resolve: ({ m }) => (blockOk(m) ? efficiency(num(m.current?.spend), num(m.current?.revenue)) : null) },
  meta_poas:       { label: "Meta POAS",        fmt: "ratio",     kind: "rate",   resolve: ({ m }) => (blockOk(m) ? efficiency(num(m.current?.spend), num(m.current?.profit)) : null) },
  meta_purchases:  { label: "Meta purchases",   fmt: "int",       kind: "volume", resolve: ({ m }) => (blockOk(m) ? num(m.current?.purchases) : null) },
  sku_units:       { label: "SKU units",        fmt: "int",       kind: "volume", scoped: "sku", resolve: ({ s }, goal) => num(matchSku(s, goal)?.units) },
  sku_revenue:     { label: "SKU revenue",      fmt: "currency0", kind: "volume", scoped: "sku", resolve: ({ s }, goal) => num(matchSku(s, goal)?.revenue) },
};

export function goalCtx(data, config) {
  return { data, s: data.store, g: data.google_ads, m: data.meta, b: blended(data, config) };
}

// Goals active for a period: period "monthly" (default) applies everywhere; a
// specific "YYYY-MM" applies only to that month and overrides a same-id default.
function goalsForPeriod(goalSet, monthId) {
  const list = goalSet?.goals ?? [];
  const applies = list.filter((g) => !g.period || g.period === "monthly" || g.period === monthId);
  const byId = new Map();
  for (const g of applies) {
    const prev = byId.get(g.id);
    if (!prev || (g.period && g.period !== "monthly")) byId.set(g.id, g);
  }
  return [...byId.values()];
}

// rows for the attainment section; paceFraction (0..1) pro-rates volume goals.
// mtdActuals (optional) overrides resolver output for MTD pace views.
export function resolveGoalRows(goalSet, ctx, fmt, { monthId, paceFraction = 1, mtdActuals = null } = {}) {
  if (!goalSet) return [];
  const proposed = goalSet.status === "proposed";
  const rows = [];
  for (const goal of goalsForPeriod(goalSet, monthId)) {
    const metric = METRICS[goal.metric];
    if (!metric || goal.target == null) continue;
    const direction = goal.direction ?? metric.direction ?? "higher";
    const actual = mtdActuals ? (goal.metric in mtdActuals ? mtdActuals[goal.metric] : undefined) : metric.resolve(ctx, goal);
    if (mtdActuals && actual === undefined) continue;   // metric not in the MTD pull
    const effTarget = goal.target * (metric.kind === "volume" ? paceFraction : 1);
    const attainPct = actual == null || effTarget === 0 ? null
      : direction === "lower"
        ? (actual === 0 ? null : (effTarget / actual) * 100)
        : (actual / effTarget) * 100;
    const label = goal.label ?? (metric.scoped === "sku" ? `${metric.label} — ${goal.sku_match ?? "?"}` : metric.label);
    rows.push({
      key: goal.metric, id: goal.id,
      name: label + (paceFraction < 1 && effTarget !== goal.target ? " (pace)" : ""),
      actualLabel: fmt[goal.format ?? metric.fmt](actual),
      goalLabel: fmt[goal.format ?? metric.fmt](effTarget),
      attainPct, proposed, mode: metric.mode, direction,
      noData: actual == null,
    });
  }
  return rows;
}

export function funnelSteps(traffic, fmt) {
  if (!traffic || traffic.available === false) return null;
  const cur = traffic.funnel.current, prior = traffic.funnel.prior;
  const defs = [
    ["view_item", "Viewed product"],
    ["add_to_cart", "Added to cart"],
    ["begin_checkout", "Began checkout"],
    ["purchase", "Purchased"],
  ];
  return defs.map(([key, label]) => {
    const d = pctChange(cur[key], prior?.[key]);
    return { key, label, count: cur[key], deltaLabel: d == null ? "" : fmt.delta(d) };
  });
}
