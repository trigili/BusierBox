# Cleanup Ledger

griTTYkit records griTTYkit-controlled runtime changes in:

```text
./.grit/run/cleanup-ledger.jsonl
```

Each line is JSON. The initial ledger tracks top-level runtime roots, payload
extraction roots, clean operations, explicit persistence hook writes, and explicit
rshell root authorized-key writes. Generated `config-push` and `evidence push`
scratch files are ledgered as runtime writes and removals before upload cleanup.
When `GRIT_TARGET_ID` or `GRIT_TARGET_ID` is set, new ledger entries also
record `target_id`, optional `target_label`, and environment-sourced identity
metadata so operator tooling can keep cleanup evidence scoped to a known target
without requiring a target id for simple single-target workflows.
Extraction tracking is intentionally
coarse-grained: it gives operators a safe cleanup view without pretending every
extracted payload file has a separate audit entry yet.

Inspect the ledger:

```sh
grit cleanup-ledger
grit cleanup-ledger --json
```

Preview cleanup:

```sh
grit clean --dry-run
grit clean --dry-run --json
grit rshell cleanup --dry-run
```

`clean --dry-run --json` includes a `residue_plan` with intended write paths,
cleanup commands, ledgered griTTYkit-owned cleanup paths, external paths that
cannot be cleaned without explicit `--external --apply`, and no-residue features
disabled by policy. In aggressive mode the plan explicitly names disabled
fallback behaviors such as runtime fallback roots and cwd scratch fallback for
generated upload files. `cleanup_limits` lists residue classes outside
griTTYkit control, including kernel logs, shell history, filesystem journals,
flash wear-leveling, crash dumps, remote service logs, and operator-side
records. `ledgered_cleanup_paths` records the original ledger operation, path,
scope, detail when available, and the cleanup action that covers the path.
The plan also publishes frontend-oriented lookup maps:
`intended_write_path_records_by_name`, `intended_write_path_records_by_path`,
`ledgered_cleanup_paths_by_path`, `ledgered_cleanup_paths_by_scope`,
`ledgered_cleanup_paths_by_op`, and
`ledgered_cleanup_paths_by_target_id`,
`ledgered_cleanup_paths_by_target_label`, and
`ledgered_cleanup_paths_by_cleanup_action`, plus `api_collections` and
`api_resources` metadata for the `intended_write_path_records` and
`ledgered_cleanup_paths` collections.
Both dry-run and applied JSON include `writes_attempted`, `writes_blocked`,
`paths_cleaned`, `paths_failed`, `cleanup_complete`, and `cleanup_warning`.
The human text output mirrors those result fields as
`cleanup_writes_attempted`, `cleanup_writes_blocked`,
`cleanup_paths_cleaned`, `cleanup_paths_failed`, `cleanup_complete`, and
`cleanup_warning` so operators and release tooling can distinguish a preview
from a completed cleanup without parsing JSON.

Apply runtime cleanup:

```sh
grit clean --ledger
grit clean --ledger --json
```

External cleanup is opt-in only:

```sh
grit clean --external --apply
grit rshell cleanup --external --apply
```

Default cleanup removes only the griTTYkit runtime root. `clean --ledger` also
considers the configured fallback root when fallback extraction is enabled.
Cleanup skips non-directory runtime-root candidates instead of unlinking an
unexpected file at that path. It does not remove `/root/.ssh` entries or other
external state unless the operator explicitly requests external cleanup.

When rshell is configured for `root-copy`, a successful creation of
`/root/.ssh/authorized_keys` is recorded as an external `write`. When configured
for `root-merge`, griTTYkit first records a backup when an existing
`authorized_keys` file is present, then records the marked-block modification.
With `grit clean --external --apply`, `root-merge` cleanup removes only the
griTTYkit marked block, while `root-copy` cleanup removes the file only when the
ledger says griTTYkit created it.

No-residue mode is best-effort ephemeral runtime. `GRIT_NORESIDUE_LEVEL` controls
how strongly griTTYkit tries to minimize its own runtime residue:

- `best-effort`: current behavior; remove the selected runtime root and ledgered
  files where reasonable, while keeping visible logs/status when configured.
- `aggressive`: minimize griTTYkit runtime writes and cleanup detail after
  payload commands, while still staying visible, reversible where applicable,
  and auditable. Aggressive mode fails closed instead of using a configured
  fallback runtime root; use `best-effort` when fallback extraction is an
  acceptable operator tradeoff. Generated upload scratch files use the
  configured runtime root only, and are removed after the upload attempt.
  Policy JSON and text also make the log boundary explicit: aggressive mode
  does not create persistent target logs by default, and `GRIT_ZERO_ARG_LOG_MODE=none`
  is the supported stdout/stderr suppression path for zero-arg autorun where
  practical.

Both levels remove only griTTYkit-owned runtime roots after foreground payload
commands, forward common interrupt signals to the child process, and still
attempt cleanup after interrupted foreground commands. No-residue cleanup is
not forensic no-trace execution, and aggressive mode cannot guarantee absence
of residue from the kernel, filesystem journal, shell history, payload tools,
or operator-requested external writes.
