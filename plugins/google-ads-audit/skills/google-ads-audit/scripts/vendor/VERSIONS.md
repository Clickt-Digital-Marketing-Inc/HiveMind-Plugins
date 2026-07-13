# Vendored runtime — google-ads-audit

These files are committed **verbatim** and inlined into the interactive HTML report
so it stays fully self-contained (zero external references). Never edit them by hand.
To upgrade: re-download, re-pin the version here, regenerate `SHA256SUMS`
(`shasum -a 256 gsap.min.js`), and re-run `tests/test_audit.py`.

| File | Library | Version | Source | Downloaded |
| -- | -- | -- | -- | -- |
| `gsap.min.js` | GSAP core | 3.12.5 | https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js | 2026-07-08 |

**Why core only:** the report uses `gsap.to` / `gsap.from` / timelines for the Health
Score count-up, gauge sweep, and staggered reveals — no plugins (ScrollTrigger,
SplitText, etc.) are required.

**License:** GSAP is free for everyone including commercial, sold products under the
GSAP standard license (Webflow, 2025) — no separate business license required; the
only prohibited use is building a competing no-code animation tool. Verified
2026-07-08 (gsap.com/community/standard-license). The library is inlined between the
`/*__GSAP_JS_BEGIN__*/ … /*__GSAP_JS_END__*/` sentinels in `audit_html.py`; the
self-containment test excises that byte-checksummed region before scanning for
external references (GSAP's banner contains gsap.com URLs).
