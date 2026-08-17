# Pyrito Reporting 1.5.0 distribution release

This release makes the private `Pyrito-ai/Pyrito-Reporting` repository the only
maintained source for Pyrito Reporting. The public HiveMind marketplace carries two
source records pinned to the same approved commit: the complete `pyrito-reporting`
plugin and the small `clickt-reporting` migration shim. It does not vendor either
payload, so there is no independently maintained downstream engine.

## Immutable source contract

- Canonical repository: `Pyrito-ai/Pyrito-Reporting`
- Approved commit: `dcb19312a1285bcbf0f2db2d1309919f39789997`
- Canonical Git tree: `ec1b9ff3575f99a5439592ec0625ddf4b5f15248`
- Canonical payload: 66 tracked files
- Canonical engine SHA-256:
  `84613b8c65767f654776e44a316c524920abc3bb5803dd786e213e89b5affdec`
- Legacy-shim Git tree: `fbc99cf2673d8e90dd69a5c83de3ce0e8a52f80f`
- Legacy-shim payload: four tracked files

The values above are machine-readable in
[`pyrito-reporting-1.5.0.json`](pyrito-reporting-1.5.0.json). They were derived with:

```bash
git rev-parse 'dcb19312a1285bcbf0f2db2d1309919f39789997^{tree}'
git ls-tree -r --name-only dcb19312a1285bcbf0f2db2d1309919f39789997 | wc -l
git rev-parse 'dcb19312a1285bcbf0f2db2d1309919f39789997:.claude-plugin/legacy/clickt-reporting'
git ls-tree -r dcb19312a1285bcbf0f2db2d1309919f39789997 .claude-plugin/legacy/clickt-reporting
node scripts/report-engine-integrity.mjs
node scripts/validate-plugin-packaging.mjs
node scripts/scan-release-candidate.mjs
```

The release-candidate scan reported `66 candidate text files, 0 secret or user-path
findings`; that count comes from the final command above. The engine integrity command
reported 38 engine files and the SHA-256 recorded above.

## Sync boundaries

`pyrito-reporting` resolves to the repository root at the approved commit.
`clickt-reporting` resolves only to
`.claude-plugin/legacy/clickt-reporting` at that same commit. The legacy source contains
one manifest and three fail-closed command notices; it contains no skills, templates,
engine, deploy script, client data, or publishing path.

The former local `plugins/clickt-reporting` snapshot remains in Git as a recoverable
historical baseline, but no marketplace entry references it. It is frozen and must not
receive feature or engine updates. This makes the old v1.0.x payload unable to override
the canonical package while preserving non-destructive rollback evidence.

## Install and migration

The primary user-facing source for both hosts is the canonical private repository.
Repository access is required.
The downstream Claude entries use the repository's explicit HTTPS Git URL so Claude
Code can use the credential-helper flow documented for private repositories; both
entries remain pinned to the approved commit above.

Claude Code:

```text
/plugin marketplace add Pyrito-ai/Pyrito-Reporting
/plugin install pyrito-reporting@pyrito-reporting
```

Codex:

```bash
codex plugin marketplace add Pyrito-ai/Pyrito-Reporting --ref main
codex plugin add pyrito-reporting@pyrito-reporting
```

Existing Claude Code users may update `hivemind-plugins` and keep
`clickt-reporting@hivemind-plugins` installed while migrating saved invocations. The
shim tells them to install Pyrito Reporting and maps setup, weekly, and monthly command
names; it never runs a workflow or publishes by itself.

## Compatibility window

The `clickt-reporting` identity remains through the PYR-73 no-stranding audit. Removal
also requires separate human approval and all of the following objective conditions:

- repository and downstream scans find zero live `clickt-reporting` invocations outside
  migration history;
- every known scheduled routine is confirmed migrated by its owner;
- fresh Claude Code and Codex installation tests pass for two consecutive tagged
  releases; and
- retirement is announced at least one tagged release in advance.

No alias or marketplace entry is removed by this release.

## Production and deferred work

The current production hostname is `reports.gethivemind.co`. This release changes no
report, client repository, routine, credential, DNS record, VPS configuration, or
deployment. Domain migration is explicitly deferred to a separate project.

## Rollback

Before merge, delete only the review branch if the release is rejected. After merge,
revert the downstream distribution commit to restore the previous marketplace record;
the historical local snapshot and the canonical private repository remain intact. Do
not delete the legacy identity during rollback. The PYR-60 all-refs recovery bundle is
the deeper source-recovery boundary and is not modified by this release.
