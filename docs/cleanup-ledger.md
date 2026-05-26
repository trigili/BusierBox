# Cleanup Ledger

BusierBox records BusierBox-controlled runtime changes in:

```text
./.busierbox/run/cleanup-ledger.jsonl
```

Each line is JSON. The initial ledger tracks top-level runtime roots, payload
extraction roots, clean operations, explicit persistence hook writes, and explicit
rshell root authorized-key writes. Extraction tracking is intentionally
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

No-residue mode is best-effort ephemeral runtime. It removes the selected
extraction root after foreground payload commands, forwards common interrupt
signals to the child process, and still attempts cleanup after interrupted
foreground commands. It records top-level paths in the cleanup ledger, but it is
not forensic no-trace execution.
