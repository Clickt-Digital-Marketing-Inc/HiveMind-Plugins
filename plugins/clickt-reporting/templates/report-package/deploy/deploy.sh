#!/usr/bin/env bash
# Deploy one client report site to an explicitly named destination.
set -euo pipefail

usage() {
  echo "Usage: $0 --destination <exact-rsync-target-ending-in-client-slug> --confirm deploy:<client-slug>" >&2
}

DESTINATION=""
CONFIRMATION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --destination)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      DESTINATION="$2"
      shift 2
      ;;
    --confirm)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      CONFIRMATION="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$DESTINATION" && -n "$CONFIRMATION" ]] || { usage; exit 2; }
[[ "$DESTINATION" != *$'\n'* && "$DESTINATION" != *$'\r'* ]] || {
  echo "REFUSE: destination contains a control character" >&2
  exit 2
}

cd "$(dirname "$0")/.."
CLIENT="$(node -p 'JSON.parse(require("fs").readFileSync("config/client.json","utf8")).client.slug')"
[[ "$CLIENT" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || {
  echo "REFUSE: client slug must match ^[a-z0-9]+(-[a-z0-9]+)*$" >&2
  exit 2
}

NORMALIZED_DESTINATION="${DESTINATION%/}"
DESTINATION_PATH="${NORMALIZED_DESTINATION#*:}"
[[ "${DESTINATION_PATH##*/}" == "$CLIENT" ]] || {
  echo "REFUSE: destination must end in the exact client slug '$CLIENT'" >&2
  exit 2
}

node template/build-dist.mjs
[[ -d "dist/${CLIENT}" ]] || {
  echo "REFUSE: build did not create dist/${CLIENT}/" >&2
  exit 2
}

echo "Dry run for dist/${CLIENT}/ -> ${NORMALIZED_DESTINATION}/"
rsync -azn --itemize-changes "dist/${CLIENT}/" "${NORMALIZED_DESTINATION}/"
echo "Dry run passed."

EXPECTED_CONFIRMATION="deploy:${CLIENT}"
[[ "$CONFIRMATION" == "$EXPECTED_CONFIRMATION" ]] || {
  echo "REFUSE: confirmation must be exactly '$EXPECTED_CONFIRMATION'" >&2
  exit 2
}

# Deliberately no --delete: files absent from this build remain recoverable at destination.
rsync -az "dist/${CLIENT}/" "${NORMALIZED_DESTINATION}/"
echo "Deployed ${CLIENT} to the explicitly supplied destination."
