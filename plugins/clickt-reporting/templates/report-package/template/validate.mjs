// Validator for the normalized data contract (see schema/CONTRACT.md).
// Zero dependencies. Errors abort the build; warnings render with the report.

const PCT = (a, b) => (b === 0 ? (a === 0 ? 0 : Infinity) : Math.abs(a - b) / Math.abs(b));

const METRIC_FIELDS = {
  google_ads: ["spend", "impressions", "clicks", "ctr", "cpc", "conversions", "conversion_value"],
  meta: ["spend", "impressions", "clicks", "ctr", "cpc", "cpm", "reach", "frequency", "purchases", "revenue"],
  store: ["sessions", "orders", "conversion_rate", "aov", "revenue"],
};

const FUNNEL_STEPS = ["view_item", "add_to_cart", "begin_checkout", "purchase"];

function isNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

function checkMetrics(block, name, periodKey, fields, errors) {
  const p = block[periodKey];
  if (p == null) {
    if (periodKey !== "yoy") errors.push(`${name}.${periodKey}: missing`);
    return null;
  }
  for (const f of fields) {
    if (!isNum(p[f])) errors.push(`${name}.${periodKey}.${f}: missing or not a number`);
    else if (p[f] < 0) errors.push(`${name}.${periodKey}.${f}: negative (${p[f]})`);
  }
  return p;
}

// Derived-metric consistency, tolerated for rounding in source exports.
function checkDerived(name, periodKey, p, errors) {
  if (!p) return;
  const where = `${name}.${periodKey}`;
  if (isNum(p.ctr) && isNum(p.clicks) && isNum(p.impressions) && p.impressions > 0 && p.ctr > 0) {
    if (PCT(p.ctr, (p.clicks / p.impressions) * 100) > 0.10)
      errors.push(`${where}: ctr ${p.ctr} inconsistent with clicks/impressions (${((p.clicks / p.impressions) * 100).toFixed(2)})`);
  }
  if (isNum(p.cpc) && isNum(p.spend) && isNum(p.clicks) && p.clicks > 0 && p.cpc > 0) {
    if (PCT(p.cpc, p.spend / p.clicks) > 0.05)
      errors.push(`${where}: cpc ${p.cpc} inconsistent with spend/clicks (${(p.spend / p.clicks).toFixed(2)})`);
  }
  if (isNum(p.aov) && isNum(p.revenue) && isNum(p.orders) && p.orders > 0 && p.aov > 0) {
    if (PCT(p.aov, p.revenue / p.orders) > 0.02)
      errors.push(`${where}: aov ${p.aov} inconsistent with revenue/orders (${(p.revenue / p.orders).toFixed(2)})`);
  }
  if (isNum(p.conversion_rate) && isNum(p.orders) && isNum(p.sessions) && p.sessions > 0 && p.conversion_rate > 0) {
    if (PCT(p.conversion_rate, (p.orders / p.sessions) * 100) > 0.10)
      errors.push(`${where}: conversion_rate ${p.conversion_rate} inconsistent with orders/sessions (${((p.orders / p.sessions) * 100).toFixed(2)})`);
  }
}

function checkTrendSum(name, block, key, errors) {
  if (!Array.isArray(block.trend) || block.trend.length === 0) return;
  const sum = block.trend.reduce((a, d) => a + (isNum(d[key]) ? d[key] : 0), 0);
  const total = block.current?.[key];
  if (isNum(total) && total > 0 && PCT(sum, total) > 0.05)
    errors.push(`${name}.trend: sum of ${key} (${sum.toFixed(2)}) off current total (${total}) by >5%`);
}

function checkCampaignSum(name, block, spendKey, errors) {
  if (!Array.isArray(block.campaigns) || block.campaigns.length === 0) return;
  const sum = block.campaigns.reduce((a, c) => a + (isNum(c[spendKey]) ? c[spendKey] : 0), 0);
  const total = block.current?.[spendKey];
  // Campaign tables may be top-N (sum ≤ total) but must never exceed the block total.
  if (isNum(total) && sum > total * 1.02)
    errors.push(`${name}.campaigns: ${spendKey} sum (${sum.toFixed(2)}) exceeds block total (${total})`);
}

export function validateData(data, config) {
  const errors = [];
  const warnings = [];

  const env = data?.meta_envelope;
  if (!env) return { errors: ["meta_envelope: missing"], warnings };
  for (const f of ["period_type", "period_id", "period_label", "date_range", "prior_range", "pulled_at", "sources"]) {
    if (env[f] == null) errors.push(`meta_envelope.${f}: missing`);
  }
  if (env.date_range && !/^\d{4}-\d{2}-\d{2}$/.test(env.date_range.start ?? ""))
    errors.push("meta_envelope.date_range.start: not YYYY-MM-DD");
  if (env.partial_period) warnings.push("Partial period — report will be labeled as such");
  if (env.period_type === "weekly" && env.mtd == null)
    warnings.push("meta_envelope.mtd missing — weekly pace vs goal will not render");

  for (const name of Object.keys(METRIC_FIELDS)) {
    if (config?.sections?.[name]?.enabled === false) continue;
    const block = data[name];
    if (!block) { errors.push(`${name}: block missing (set available:false if source is down)`); continue; }
    if (block.available === false) {
      warnings.push(`${name}: unavailable — ${block.unavailable_reason || "no reason given"}`);
      continue;
    }
    const fields = METRIC_FIELDS[name];
    for (const periodKey of ["current", "prior", "yoy"]) {
      const p = checkMetrics(block, name, periodKey, fields, errors);
      checkDerived(name, periodKey, p, errors);
    }
    if (block.yoy == null) warnings.push(`${name}.yoy: null (no YoY comparison)`);
    if (name === "google_ads") { checkTrendSum(name, block, "spend", errors); checkTrendSum(name, block, "conversion_value", errors); checkCampaignSum(name, block, "spend", errors); }
    if (name === "meta") {
      checkTrendSum(name, block, "spend", errors); checkTrendSum(name, block, "revenue", errors); checkCampaignSum(name, block, "spend", errors);
      for (const periodKey of ["current", "prior", "yoy"]) {
        const p = block[periodKey];
        if (!p || p.profit == null) continue;
        if (!isNum(p.profit) || p.profit < 0) errors.push(`meta.${periodKey}.profit: invalid`);
        else if (isNum(p.revenue) && p.profit > p.revenue * 1.02)
          errors.push(`meta.${periodKey}: profit (${p.profit}) exceeds revenue (${p.revenue})`);
      }
    }
    if (name === "store") {
      checkTrendSum(name, block, "revenue", errors);
      if (!Array.isArray(block.top_products) || block.top_products.length === 0)
        warnings.push("store.top_products: empty");
      for (const periodKey of ["current", "prior", "yoy"]) {
        const p = block[periodKey];
        if (!p) continue;
        if (p.new_customers != null) {
          if (!isNum(p.new_customers) || p.new_customers < 0) errors.push(`store.${periodKey}.new_customers: invalid`);
          else if (isNum(p.orders) && p.new_customers > p.orders)
            errors.push(`store.${periodKey}.new_customers (${p.new_customers}) exceeds orders (${p.orders})`);
        }
        if (p.profit != null) {
          if (!isNum(p.profit) || p.profit < 0) errors.push(`store.${periodKey}.profit: invalid`);
          else if (isNum(p.revenue) && p.profit > p.revenue)
            errors.push(`store.${periodKey}.profit (${p.profit}) exceeds revenue (${p.revenue})`);
        }
      }
    }
    if (name === "google_ads") {
      for (const periodKey of ["current", "prior", "yoy"]) {
        const p = block[periodKey];
        if (!p || p.revenue == null) continue;
        if (!isNum(p.revenue) || p.revenue < 0) errors.push(`google_ads.${periodKey}.revenue: invalid`);
        else if (isNum(p.conversion_value) && p.conversion_value > p.revenue * 1.02)
          errors.push(`google_ads.${periodKey}: conversion_value/profit (${p.conversion_value}) exceeds revenue (${p.revenue})`);
      }
    }
  }

  const traffic = data.traffic;
  if (config?.sections?.traffic?.enabled !== false) {
    if (!traffic) errors.push("traffic: block missing (set available:false if source is down)");
    else if (traffic.available === false) {
      warnings.push(`traffic: unavailable — ${traffic.unavailable_reason || "no reason given"}`);
    } else {
      for (const periodKey of ["current", "prior"]) {
        const f = traffic.funnel?.[periodKey];
        if (!f) { errors.push(`traffic.funnel.${periodKey}: missing`); continue; }
        for (const s of FUNNEL_STEPS) if (!isNum(f[s]) || f[s] < 0) errors.push(`traffic.funnel.${periodKey}.${s}: missing/negative`);
        for (let i = 1; i < FUNNEL_STEPS.length; i++) {
          const hi = f[FUNNEL_STEPS[i - 1]], lo = f[FUNNEL_STEPS[i]];
          if (isNum(hi) && isNum(lo) && lo > hi)
            errors.push(`traffic.funnel.${periodKey}: ${FUNNEL_STEPS[i]} (${lo}) > ${FUNNEL_STEPS[i - 1]} (${hi}) — funnel must decrease`);
        }
      }
      if (!Array.isArray(traffic.channels) || traffic.channels.length === 0)
        warnings.push("traffic.channels: empty");
    }
  }

  return { errors, warnings };
}
