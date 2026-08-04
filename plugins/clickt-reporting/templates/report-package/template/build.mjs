#!/usr/bin/env node
// Build a self-contained report HTML for one period.
//
//   node template/build.mjs 2026-07              # periods/2026-07/ → report.html
//   node template/build.mjs 2026-W32
//   node template/build.mjs --fixture monthly    # template/fixtures/monthly/ → report.html
//
// Reads config/client.json + config/goals.json, the period's data.json and
// commentary.md; validates; renders monthly or weekly by meta_envelope.period_type.
// Validation errors abort — client-facing numbers must not render wrong.

import { readFileSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { validateData } from "./validate.mjs";
import { METRICS } from "./partials/derive.mjs";
import { makeFormatters, esc } from "./partials/fmt.mjs";
import { renderMonthly } from "./partials/monthly.mjs";
import { renderWeekly } from "./partials/weekly.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const pkgRoot = join(here, "..");

function fail(msg) {
  console.error(`\n✖ ${msg}`);
  process.exit(1);
}

// ---- resolve target ----
const args = process.argv.slice(2);
let periodDir, label;
if (args[0] === "--fixture") {
  const which = args[1] || "monthly";
  periodDir = join(here, "fixtures", which);
  label = `fixture:${which}`;
} else if (args[0]) {
  periodDir = join(pkgRoot, "periods", args[0]);
  label = args[0];
} else {
  fail("Usage: node template/build.mjs <period-id> | --fixture monthly|weekly");
}
if (!existsSync(periodDir)) fail(`Period directory not found: ${periodDir}`);

// ---- load inputs ----
const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
const config = readJson(join(pkgRoot, "config", "client.json"));
// A period-local goals.json (used by fixtures) overrides the client-level one.
const goalsPath = existsSync(join(periodDir, "goals.json"))
  ? join(periodDir, "goals.json")
  : join(pkgRoot, "config", "goals.json");
const goals = existsSync(goalsPath) ? readJson(goalsPath) : null;
const dataPath = join(periodDir, "data.json");
if (!existsSync(dataPath)) fail(`Missing ${dataPath}`);
const data = readJson(dataPath);

// commentary.md → { sectionId: text } keyed by "## <id>" headings.
let commentaryMap = {};
const commentaryPath = join(periodDir, "commentary.md");
if (existsSync(commentaryPath)) {
  const raw = readFileSync(commentaryPath, "utf8");
  let current = null;
  for (const line of raw.split("\n")) {
    const h = line.match(/^##\s+(\S+)/);
    if (h) { current = h[1].toLowerCase(); commentaryMap[current] = ""; }
    else if (current) commentaryMap[current] += line + "\n";
  }
}

// ---- validate ----
const { errors, warnings } = validateData(data, config);
for (const w of warnings) console.warn(`⚠ ${w}`);
if (errors.length) {
  for (const e of errors) console.error(`✖ ${e}`);
  fail(`Validation failed with ${errors.length} error(s) — build aborted.`);
}

// goals sanity: unknown metrics warn (goal simply won't resolve)
for (const set of goals?.goal_sets ?? [])
  for (const goal of set.goals ?? [])
    if (!METRICS[goal.metric]) console.warn(`⚠ goals: unknown metric "${goal.metric}" (goal id ${goal.id})`);

// ---- sibling weekly pulses (for the monthly report's Pulses tab) ----
// Paths resolve in the deployed/dist layout where pulse-<id>.html sits beside
// the monthly page. Fixture builds have no siblings and render the empty state.
let pulses = [];
const periodsRoot = join(pkgRoot, "periods");
if (existsSync(periodsRoot) && args[0] !== "--fixture") {
  for (const id of readdirSync(periodsRoot).sort().reverse()) {
    const dp = join(periodsRoot, id, "data.json");
    if (!existsSync(dp)) continue;
    try {
      const envW = JSON.parse(readFileSync(dp, "utf8")).meta_envelope;
      if (envW.period_type === "weekly")
        pulses.push({ id, label: envW.period_label, file: `pulse-${id}.html`, range: envW.date_range });
    } catch { /* skip unreadable period */ }
  }
}

// ---- render ----
const fmt = makeFormatters(config);
const ctx = { data, config, goals, commentaryMap, fmt, pulses };
const type = data.meta_envelope.period_type;
const body = type === "weekly" ? renderWeekly(ctx) : renderMonthly(ctx);

const css = readFileSync(join(here, "partials", "styles.css"), "utf8");
const runtime = readFileSync(join(here, "partials", "runtime.js"), "utf8");
const title = `${config.client.name} — ${type === "weekly" ? "Weekly Pulse" : "Monthly Performance"} ${data.meta_envelope.period_label}`;

// Artifact-ready page content: no doctype/html/head/body wrapper — the Artifact
// tool adds the skeleton. Opening the file directly in a browser also works.
const html = `<title>${esc(title)}</title>
<style>
${css}</style>
<div class="page">
${body}
</div>
<script>
${runtime}</script>
`;

const outPath = join(periodDir, "report.html");
writeFileSync(outPath, html);
// Local-preview twin with a proper skeleton (report.html itself stays
// artifact-ready — the Artifact tool adds the wrapper at publish time).
writeFileSync(
  join(periodDir, "report-preview.html"),
  `<!doctype html>\n<html lang="${config.client.locale?.slice(0, 2) || "en"}">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n</head>\n<body>\n${html}\n</body>\n</html>\n`,
);
console.log(`✔ Built ${label} (${type}) → ${outPath}`);
if (warnings.length) console.log(`  ${warnings.length} warning(s) above.`);
