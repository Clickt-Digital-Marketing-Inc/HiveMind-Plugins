---
description: Guide a protected remote CM3 report run without exposing CSV rows or local compute.
---

Run the `cm3-by-product-report` skill end-to-end through contract version 1.0.
Use only `cm3_prepare_uploads`, direct raw-body PUTs through the skill's thin
helper, and `cm3_generate_report`. Never invoke the retained legacy local
compute/render files or offer a local fallback.
