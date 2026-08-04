// Goals tab: in-page editor for the active goal set. Pure client-side (CSP-safe);
// Export produces the complete goals.json to hand back for config/goals.json.

import { esc } from "./fmt.mjs";
import { METRICS } from "./derive.mjs";

export function renderGoalsTab({ goals, goalSet, config }) {
  const catalog = Object.entries(METRICS).map(([id, m]) => ({
    id, label: m.label, direction: m.direction ?? "higher", scoped: m.scoped ?? null, fmt: m.fmt,
  }));
  const payload = {
    file: goals ?? { version: 2, goal_sets: [] },
    activeEffectiveFrom: goalSet?.effective_from ?? null,
    catalog,
    client: config.client.name,
  };
  return `<section class="section">
<details class="ge-disclosure">
<summary class="section-head"><span class="ge-chevron" aria-hidden="true">▸</span><span class="kicker">Targets</span><h2>Goals</h2><span class="basis">edit targets → Export JSON → send it back to update the config</span></summary>
<div class="goals-editor" data-goals-editor>
  <div class="ge-meta">
    <label>Effective from <input type="date" data-ge-effective></label>
    <label>Status <select data-ge-status><option value="proposed">proposed</option><option value="agreed">agreed</option></select></label>
  </div>
  <div class="table-wrap"><table class="data ge-table">
    <thead><tr><th>Goal</th><th>Metric</th><th>SKU match</th><th>Period</th><th>Target</th><th>Direction</th><th></th></tr></thead>
    <tbody data-ge-rows></tbody>
  </table></div>
  <div class="ge-actions">
    <button type="button" class="ge-btn" data-ge-add>+ Add goal</button>
    <button type="button" class="ge-btn primary" data-ge-export>Export JSON</button>
    <button type="button" class="ge-btn" data-ge-download hidden>Download goals.json</button>
    <button type="button" class="ge-btn" data-ge-copy hidden>Copy</button>
    <span class="ge-note" data-ge-msg></span>
  </div>
  <textarea class="ge-output" data-ge-output hidden readonly rows="14" spellcheck="false" aria-label="Exported goals.json"></textarea>
  <p class="ge-help">Period: <b>monthly</b> applies every month; a specific month like <b>2026-12</b> applies only then and overrides the monthly goal with the same name. SKU goals match product titles (case-insensitive substring) and need the SKU in the store data pull. Direction <b>lower</b> means under-target is good (e.g. nCAC).</p>
</div>
</details>
<script type="application/json" data-ge-payload>${JSON.stringify(payload).replace(/</g, "\\u003c")}</script>
</section>`;
}
