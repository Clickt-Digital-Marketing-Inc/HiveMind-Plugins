# Canonical paid-plugin sync

`HiveMind-Marketing-Skills` is the development source of truth for the overlapping paid
plugins. This marketplace mirror byte-tracks the payload population declared in
`.canonical-sync.json`.

Run a sync from an explicit local canonical checkout and commit:

```bash
python3 -B scripts/sync_paid_plugins.py \
  --canonical-repo /path/to/HiveMind-Marketing-Skills \
  --canonical-ref <full-canonical-commit>
```

Then update `.canonical-sync.json`'s `sourceCommit`, patch-bump every plugin whose payload
changed, regenerate `.payload-lock.json`, and run `./verify`. The sync copies and deletes
Git-tracked payload paths. It never edits the canonical checkout.

The overlay allowlist is intentionally narrow. Plugin manifests carry marketplace release
metadata. The Google Ads hub and four link-bearing skill files differ only where this
marketplace's installed-plugin population or path layout requires it. Every overlay has a
reason in `.canonical-sync.json`; all other files in the synced roots must match canonical
in both directions.

CI checks out the private canonical repository and runs `./verify`. Repository settings
must provide `HIVEMIND_MARKETING_SKILLS_TOKEN`, a read-only token that can clone
`Clickt-Digital-Marketing-Inc/HiveMind-Marketing-Skills`. Missing or insufficient access
fails the checkout and therefore fails CI closed.
