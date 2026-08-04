#!/usr/bin/env bash
# Deploy the client's report site to reports.clickt.ca (Hetzner box, Caddy).
# Server layout: /root/reports/<client-slug>/ served at reports.clickt.ca/<client-slug>/
# behind per-client basic_auth (see deploy/SERVER.md). Reports are drafts until
# John approves — deploying is safe (auth-gated), but only share credentials
# with the client after sign-off.
set -euo pipefail
cd "$(dirname "$0")/.."

HOST="${REPORTS_HOST:-root@5.161.204.210}"
CLIENT="$(node -p 'JSON.parse(require("fs").readFileSync("config/client.json","utf8")).client.slug')"

node template/build-dist.mjs
rsync -az --delete "dist/${CLIENT}/" "${HOST}:/root/reports/${CLIENT}/"
echo "✔ deployed → https://reports.clickt.ca/${CLIENT}/"
