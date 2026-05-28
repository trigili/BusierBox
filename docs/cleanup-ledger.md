# Cleanup Ledger

BusierBox records BusierBox-controlled runtime changes in:

```text
./.busierbox/run/cleanup-ledger.jsonl
```

Each line is JSON. The initial ledger tracks top-level runtime roots, payload
extraction roots, clean operations, explicit persistence hook writes, and explicit
rshell root authorized-key writes. Generated `config-push` and `evidence push`
scratch files are ledgered as runtime writes and removals before upload cleanup.
Extraction tracking is intentionally
coarse-grained: it gives operators a safe cleanup view without pretending every
extracted payload file has a separate audit entry yet.

Inspect the ledger:

```sh
busierbox cleanup-ledger
busierbox cleanup-ledger --json
```

Preview cleanup:

```sh
busierbox clean --dry-run
busierbox clean --dry-run --json
busierbox rshell cleanup --dry-run
```

`clean --dry-run --json` includes a `residue_plan` with intended write paths,
cleanup commands, ledgered BusierBox-owned cleanup paths, external paths that
cannot be cleaned without explicit `--external --apply`, and no-residue features
disabled by policy. In aggressive mode the plan explicitly names disabled
fallback behaviors such as runtime fallback roots and cwd scratch fallback for
generated upload files. `cleanup_limits` lists residue classes outside
BusierBox control, including kernel logs, shell history, filesystem journals,
flash wear-leveling, crash dumps, remote service logs, and operator-side
records. `ledgered_cleanup_paths` records the original ledger operation, path,
scope, detail when available, and the cleanup action that covers the path.
Both dry-run and applied JSON include `writes_attempted`,
`writes_blocked`, `paths_cleaned`, `paths_failed`, `cleanup_complete`, and
`cleanup_warning` so operators and release tooling can distinguish a preview
from a completed cleanup.

Apply runtime cleanup:

```sh
busierbox clean --ledger
busierbox clean --ledger --json
```

External cleanup is opt-in only:

```sh
busierbox clean --external --apply
busierbox rshell cleanup --external --apply
```

Default cleanup removes only the BusierBox runtime root. `clean --ledger` also
considers the configured fallback root when fallback extraction is enabled.
Cleanup skips non-directory runtime-root candidates instead of unlinking an
unexpected file at that path. It does not remove `/root/.ssh` entries or other
external state unless the operator explicitly requests external cleanup.

When rshell is configured for `root-copy`, a successful creation of
`/root/.ssh/authorized_keys` is recorded as an external `write`. When configured
for `root-merge`, BusierBox first records a backup when an existing
`authorized_keys` file is present, then records the marked-block modification.
With `busierbox clean --external --apply`, `root-merge` cleanup removes only the
BusierBox marked block, while `root-copy` cleanup removes the file only when the
ledger says BusierBox created it.

No-residue mode is best-effort ephemeral runtime. `BB_NORESIDUE_LEVEL` controls
how strongly BusierBox tries to minimize its own runtime residue:

- `best-effort`: current behavior; remove the selected runtime root and ledgered
  files where reasonable, while keeping visible logs/status when configured.
- `aggressive`: minimize BusierBox runtime writes and cleanup detail after
  payload commands, while still staying visible, reversible where applicable,
  and auditable. Aggressive mode fails closed instead of using a configured
  fallback runtime root; use `best-effort` when fallback extraction is an
  acceptable operator tradeoff. Generated upload scratch files use the
  configured runtime root only, and are removed after the upload attempt.

Both levels remove only BusierBox-owned runtime roots after foreground payload
commands, forward common interrupt signals to the child process, and still
attempt cleanup after interrupted foreground commands. No-residue cleanup is
not forensic no-trace execution, and aggressive mode cannot guarantee absence
of residue from the kernel, filesystem journal, shell history, payload tools,
or operator-requested external writes.
