// Formatting helpers. All client-facing numbers flow through here.

export function makeFormatters(config) {
  const locale = config.client.locale || "en-CA";
  const currency = config.client.currency || "CAD";
  const cur0 = new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 });
  const cur2 = new Intl.NumberFormat(locale, { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const int = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const d1 = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const d2 = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return {
    currency0: (v) => (v == null ? "—" : cur0.format(v)),
    currency2: (v) => (v == null ? "—" : cur2.format(v)),
    int: (v) => (v == null ? "—" : int.format(v)),
    pct1: (v) => (v == null ? "—" : `${d1.format(v)}%`),
    pct2: (v) => (v == null ? "—" : `${d2.format(v)}%`),
    ratio: (v) => (v == null || !Number.isFinite(v) ? "—" : `${d2.format(v)}×`),
    compactCur: (v) => {
      if (v == null) return "—";
      const abs = Math.abs(v);
      if (abs >= 1000) return `$${d1.format(v / 1000)}k`;
      return cur0.format(v);
    },
    delta: (v) => {
      if (v == null || !Number.isFinite(v)) return null;
      const sign = v > 0 ? "+" : "";
      return `${sign}${d1.format(v)}%`;
    },
  };
}

// Percent change current vs base; null when base is 0/absent (renders as —).
export function pctChange(current, base) {
  if (current == null || base == null || base === 0) return null;
  return ((current - base) / Math.abs(base)) * 100;
}

export function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function monthLabel(dateStr, locale = "en-CA") {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(locale, { month: "short", day: "numeric", timeZone: "UTC" });
}
