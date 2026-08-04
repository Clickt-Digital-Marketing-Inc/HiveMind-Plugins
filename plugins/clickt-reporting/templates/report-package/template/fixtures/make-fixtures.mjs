#!/usr/bin/env node
// Regenerate fixture datasets. Deterministic (seeded PRNG) so golden builds
// are reproducible. Totals are computed FROM the daily series, so derived
// fields always satisfy the validator.
//   node template/fixtures/make-fixtures.mjs

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

let seed = 42;
function rnd() { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; }
const r2 = (v) => Math.round(v * 100) / 100;

function dailySeries(startISO, days, base, wobble) {
  const out = [];
  const [y, m, d] = startISO.split("-").map(Number);
  for (let i = 0; i < days; i++) {
    const dt = new Date(Date.UTC(y, m - 1, d + i));
    out.push({ date: dt.toISOString().slice(0, 10), f: base * (1 + (rnd() - 0.5) * wobble) });
  }
  return out;
}

function channelBlock({ start, days, spendBase, valueMult, kind }) {
  const spendDays = dailySeries(start, days, spendBase, 0.5);
  const valueDays = spendDays.map((s) => ({ date: s.date, v: s.f * valueMult * (0.6 + rnd() * 0.9) }));
  const spend = r2(spendDays.reduce((a, s) => a + s.f, 0));
  const value = r2(valueDays.reduce((a, s) => a + s.v, 0));
  const impressions = Math.round(spend * (55 + rnd() * 15));
  const clicks = Math.round(impressions * (0.02 + rnd() * 0.01));
  const conv = Math.max(3, Math.round(clicks * (0.02 + rnd() * 0.02)));
  const base = {
    spend, impressions, clicks,
    ctr: r2((clicks / impressions) * 100),
    cpc: r2(spend / clicks),
  };
  if (kind === "google") return { ...base, conversions: conv, conversion_value: value, revenue: r2(value * (2.6 + rnd())), _trend: spendDays.map((s, i) => ({ date: s.date, spend: r2(s.f), conversion_value: r2(valueDays[i].v) })) };
  const reach = Math.round(impressions / (3 + rnd()));
  return { ...base, cpm: r2((spend / impressions) * 1000), reach, frequency: r2(impressions / reach), purchases: conv, revenue: value, profit: r2(value * (0.25 + rnd() * 0.12)), _trend: spendDays.map((s, i) => ({ date: s.date, spend: r2(s.f), revenue: r2(valueDays[i].v) })) };
}

function storeBlock({ start, days, revBase }) {
  const revDays = dailySeries(start, days, revBase, 0.6);
  const revenue = r2(revDays.reduce((a, s) => a + s.f, 0));
  const orders = Math.max(5, Math.round(revenue / (150 + rnd() * 60)));
  const sessions = Math.round(orders / (0.01 + rnd() * 0.01));
  const ordDays = revDays.map((s) => Math.round((s.f / revenue) * orders));
  return {
    current: { sessions, orders, conversion_rate: r2((orders / sessions) * 100), aov: r2(revenue / orders), revenue,
      profit: r2(revenue * (0.5 + rnd() * 0.12)), new_customers: Math.round(orders * (0.45 + rnd() * 0.2)) },
    trend: revDays.map((s, i) => ({ date: s.date, revenue: r2(s.f), orders: ordDays[i] })),
  };
}

function strip(block) { const { _trend, ...rest } = block; return rest; }

function makeMonthly() {
  const gCur = channelBlock({ start: "2026-07-01", days: 31, spendBase: 95, valueMult: 2.6, kind: "google" });
  const gPri = channelBlock({ start: "2026-06-01", days: 30, spendBase: 88, valueMult: 2.3, kind: "google" });
  const gYoy = channelBlock({ start: "2025-07-01", days: 31, spendBase: 60, valueMult: 2.0, kind: "google" });
  const mCur = channelBlock({ start: "2026-07-01", days: 31, spendBase: 135, valueMult: 3.4, kind: "meta" });
  const mPri = channelBlock({ start: "2026-06-01", days: 30, spendBase: 142, valueMult: 3.1, kind: "meta" });
  const mYoy = channelBlock({ start: "2025-07-01", days: 31, spendBase: 90, valueMult: 2.8, kind: "meta" });
  const sCur = storeBlock({ start: "2026-07-01", days: 31, revBase: 780 });
  const sPri = storeBlock({ start: "2026-06-01", days: 30, revBase: 720 });
  const sYoy = storeBlock({ start: "2025-07-01", days: 31, revBase: 520 });

  const purchases = sCur.current.orders;
  const funnelCur = { view_item: Math.round(purchases * 38), add_to_cart: Math.round(purchases * 9.5), begin_checkout: Math.round(purchases * 3.2), purchase: purchases };
  const funnelPri = { view_item: Math.round(purchases * 41), add_to_cart: Math.round(purchases * 10.4), begin_checkout: Math.round(purchases * 3.0), purchase: sPri.current.orders };

  const gCampaigns = ["Brand — Search", "Pantry Staples — PMax", "FR — Search", "Bulk Foods — Search"].map((name, i) => {
    const share = [0.34, 0.31, 0.2, 0.15][i];
    return { name, spend: r2(gCur.spend * share), impressions: Math.round(gCur.impressions * share), clicks: Math.round(gCur.clicks * share), conversions: Math.round(gCur.conversions * share), conversion_value: r2(gCur.conversion_value * share * (0.8 + rnd() * 0.4)) };
  });
  const mCampaigns = ["Prospecting — Advantage+", "Retargeting — DPA", "FR — Prospecting"].map((name, i) => {
    const share = [0.52, 0.28, 0.2][i];
    return { name, spend: r2(mCur.spend * share), impressions: Math.round(mCur.impressions * share), clicks: Math.round(mCur.clicks * share), purchases: Math.round(mCur.purchases * share), revenue: r2(mCur.revenue * share * (0.8 + rnd() * 0.4)) };
  });

  return {
    meta_envelope: {
      period_type: "monthly", period_id: "2026-07", period_label: "July 2026 (FIXTURE)",
      date_range: { start: "2026-07-01", end: "2026-07-31" },
      prior_range: { start: "2026-06-01", end: "2026-06-30" },
      yoy_range: { start: "2025-07-01", end: "2025-07-31" },
      partial_period: false, pulled_at: "2026-08-04",
      sources: { google_ads: "fixture", meta: "fixture", store: "fixture", traffic: "fixture" },
      mtd: null,
    },
    google_ads: { available: true, unavailable_reason: null, current: strip(gCur), prior: strip(gPri), yoy: strip(gYoy), trend: gCur._trend, campaigns: gCampaigns },
    meta: { available: true, unavailable_reason: null, current: strip(mCur), prior: strip(mPri), yoy: strip(mYoy), trend: mCur._trend, campaigns: mCampaigns },
    store: {
      available: true, unavailable_reason: null,
      current: sCur.current, prior: sPri.current, yoy: sYoy.current, trend: sCur.trend,
      top_products: [
        { title: "Organic Rolled Oats 2 kg", revenue: 2140.5, units: 61 },
        { title: "Maple Syrup Amber 1 L", revenue: 1893.25, units: 43 },
        { title: "Raw Almonds 1 kg", revenue: 1544.0, units: 39 },
        { title: "Basmati Rice 5 kg", revenue: 1210.75, units: 28 },
        { title: "Nutritional Yeast 500 g", revenue: 989.4, units: 34 },
      ],
      bottom_products: [],
    },
    traffic: {
      available: true, unavailable_reason: null,
      funnel: { current: funnelCur, prior: funnelPri },
      channels: [
        { channel: "Paid Search", sessions: 6120, revenue: 7280.4, conversion_rate: 1.62 },
        { channel: "Paid Social", sessions: 5240, revenue: 6110.8, conversion_rate: 1.31 },
        { channel: "Organic Search", sessions: 7930, revenue: 5230.15, conversion_rate: 0.94 },
        { channel: "Direct", sessions: 3480, revenue: 3924.6, conversion_rate: 1.44 },
        { channel: "Email", sessions: 1120, revenue: 1610.2, conversion_rate: 2.61 },
      ],
    },
  };
}

function makeWeekly() {
  const gCur = channelBlock({ start: "2026-08-03", days: 7, spendBase: 92, valueMult: 2.7, kind: "google" });
  const gPri = channelBlock({ start: "2026-07-27", days: 7, spendBase: 97, valueMult: 2.4, kind: "google" });
  const mCur = channelBlock({ start: "2026-08-03", days: 7, spendBase: 130, valueMult: 3.5, kind: "meta" });
  const mPri = channelBlock({ start: "2026-07-27", days: 7, spendBase: 139, valueMult: 3.0, kind: "meta" });
  const sCur = storeBlock({ start: "2026-08-03", days: 7, revBase: 810 });
  const sPri = storeBlock({ start: "2026-07-27", days: 7, revBase: 760 });

  return {
    meta_envelope: {
      period_type: "weekly", period_id: "2026-W32", period_label: "Week 32, 2026 (FIXTURE)",
      date_range: { start: "2026-08-03", end: "2026-08-09" },
      prior_range: { start: "2026-07-27", end: "2026-08-02" },
      yoy_range: null, partial_period: false, pulled_at: "2026-08-10",
      sources: { google_ads: "fixture", meta: "fixture", store: "fixture", traffic: "fixture" },
      mtd: { range: { start: "2026-08-01", end: "2026-08-09" }, store_revenue: 7420.5, total_ad_spend: 2105.3, orders: 41, new_customers: 19 },
    },
    google_ads: { available: true, unavailable_reason: null, current: strip(gCur), prior: strip(gPri), yoy: null, trend: gCur._trend, campaigns: [] },
    meta: { available: true, unavailable_reason: null, current: strip(mCur), prior: strip(mPri), yoy: null, trend: mCur._trend, campaigns: [] },
    store: { available: true, unavailable_reason: null, current: sCur.current, prior: sPri.current, yoy: null, trend: sCur.trend, top_products: [], bottom_products: [] },
    traffic: { available: false, unavailable_reason: "Funnel omitted from the weekly pulse pull.", funnel: null, channels: [] },
  };
}

const goals = {
  version: 2,
  goal_sets: [{
    effective_from: "2026-01-01", status: "proposed",
    goals: [
      { id: "store_revenue", metric: "store_revenue", target: 26000 },
      { id: "store_profit", metric: "store_profit", target: 14000 },
      { id: "total_ad_spend", metric: "total_ad_spend", target: 7500 },
      { id: "mer", metric: "mer", target: 3.5 },
      { id: "orders", metric: "orders", target: 150 },
      { id: "new_customers", metric: "new_customers", target: 80 },
      { id: "ncac", metric: "ncac", target: 90 },
      { id: "conversion_rate", metric: "conversion_rate", target: 1.3 },
      { id: "aov", metric: "aov", target: 170 },
      { id: "google_poas", metric: "google_poas", target: 2.2 },
      { id: "meta_roas", metric: "meta_roas", target: 3.0 },
      { id: "oats_units", label: "Rolled Oats units", metric: "sku_units", sku_match: "rolled oats", target: 70 },
      { id: "dec_revenue", metric: "store_revenue", target: 40000, period: "2026-12" },
    ],
  }],
};

// Broken fixture: funnel inversion + inconsistent AOV + impossible new-customer
// count + profit above revenue → validator must abort on all four.
function makeBroken() {
  const d = makeMonthly();
  d.traffic.funnel.current.add_to_cart = d.traffic.funnel.current.view_item * 2;
  d.store.current.aov = d.store.current.aov * 3;
  d.store.current.new_customers = d.store.current.orders + 50;
  d.store.current.profit = d.store.current.revenue * 1.4;
  return d;
}

for (const [name, data] of [["monthly", makeMonthly()], ["weekly", makeWeekly()], ["broken", makeBroken()]]) {
  const dir = join(here, name);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "data.json"), JSON.stringify(data, null, 2));
  writeFileSync(join(dir, "goals.json"), JSON.stringify(goals, null, 2));
  console.log(`✔ wrote fixtures/${name}/data.json`);
}

// Sample commentary exercises the filled state; weekly stays empty to show the
// "commentary to follow" state.
writeFileSync(join(here, "monthly", "commentary.md"), `## exec
A strong July: revenue grew while total spend held roughly flat, pushing MER up. **Meta prospecting** drove most of the gain.

## google_ads
Brand search stayed efficient; PMax profit dipped mid-month on a feed issue (resolved July 22).

## store
- Conversion rate improved for the third straight month
- Checkout drop-off remains the weakest funnel step — A/B test planned for August
`);
console.log("✔ wrote fixtures/monthly/commentary.md");
