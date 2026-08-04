#!/usr/bin/env node
// Assemble the deployable site for one client into dist/<client-slug>/:
//   index.html                 — Clickt-branded list of available reports
//   monthly-<id>.html          — standalone monthly reports
//   pulse-<id>.html            — standalone weekly pulses
// Reads periods/*/report-preview.html (full-skeleton builds). Run builds first.
//   node template/build-dist.mjs

import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync, copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { esc } from "./partials/fmt.mjs";
import { renderGoalsTab } from "./partials/goals-tab.mjs";
import { activeGoalSet } from "./partials/derive.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = join(here, "..");
const config = JSON.parse(readFileSync(join(pkgRoot, "config", "client.json"), "utf8"));
const slug = config.client.slug;
const outDir = join(pkgRoot, "dist", slug);
mkdirSync(outDir, { recursive: true });

const periods = [];
for (const id of readdirSync(join(pkgRoot, "periods")).sort().reverse()) {
  const dir = join(pkgRoot, "periods", id);
  const preview = join(dir, "report-preview.html");
  const dataPath = join(dir, "data.json");
  if (!existsSync(preview) || !existsSync(dataPath)) continue;
  const env = JSON.parse(readFileSync(dataPath, "utf8")).meta_envelope;
  const kind = env.period_type === "weekly" ? "pulse" : "monthly";
  const file = `${kind}-${id}.html`;
  copyFileSync(preview, join(outDir, file));
  periods.push({ id, file, kind, label: env.period_label, range: env.date_range, pulled: env.pulled_at });
}

const css = readFileSync(join(here, "partials", "styles.css"), "utf8");
const goalsPath = join(pkgRoot, "config", "goals.json");
const goals = existsSync(goalsPath) ? JSON.parse(readFileSync(goalsPath, "utf8")) : null;
const goalSet = activeGoalSet(goals, new Date().toISOString().slice(0, 10));
const goalsSection = renderGoalsTab({ goals, goalSet, config });
const editorJs = readFileSync(join(here, "partials", "goals-editor.js"), "utf8");
const item = (p) => `<li class="report-item"><a href="${esc(p.file)}"><span class="kind">${p.kind === "pulse" ? "Weekly pulse" : "Monthly report"}</span><span class="rlabel">${esc(p.label)}</span><span class="rrange">${esc(p.range.start)} – ${esc(p.range.end)}</span></a></li>`;
const monthly = periods.filter((p) => p.kind === "monthly");
const pulses = periods.filter((p) => p.kind === "pulse");

writeFileSync(join(outDir, "index.html"), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${esc(config.client.name)} — Performance Reports</title>
<style>
${css}
.report-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }
.report-item a { display: grid; grid-template-columns: 130px 1fr auto; gap: 14px; align-items: baseline; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; text-decoration: none; color: var(--ink); }
.report-item a:hover { border-color: var(--accent); }
.report-item .kind { font-size: 11px; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; color: var(--warm); }
.report-item .rlabel { font-weight: 600; }
.report-item .rrange { font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; }
@media (max-width: 560px) { .report-item a { grid-template-columns: 1fr; gap: 3px; } }
</style>
</head>
<body>
<div class="page">
<header class="masthead">
<div class="brand"><span class="dot"></span>${esc(config.agency.name)} · Performance Reporting</div>
<div class="meta">${esc(config.client.name)}</div>
</header>
<div class="report-title"><h1>${esc(config.client.name)} — Performance Reports</h1>
<p class="report-sub">Monthly reports and weekly pulses. Questions? Reply to your ${esc(config.agency.name)} contact.</p></div>
${monthly.length ? `<section class="section"><div class="section-head"><span class="kicker">Monthly</span><h2>Monthly reports</h2></div><ul class="report-list">${monthly.map(item).join("\n")}</ul></section>` : ""}
${pulses.length ? `<section class="section"><div class="section-head"><span class="kicker">Weekly</span><h2>Weekly pulses</h2></div><ul class="report-list">${pulses.map(item).join("\n")}</ul></section>` : ""}
${goalsSection}
<footer class="footer"><span>Prepared by ${esc(config.agency.legal_name)}</span><span>${esc(config.client.website)}</span></footer>
</div>
<script>
${editorJs}</script>
</body>
</html>
`);
console.log(`✔ dist/${slug}: index.html + ${periods.length} report(s) — ${periods.map((p) => p.file).join(", ")}`);
