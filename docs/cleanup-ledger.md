# Cleanup Ledger

BusierBox records BusierBox-controlled runtime changes in:

```text
./.busierbox/run/cleanup-ledger.jsonl
```

Each line is JSON. The initial ledger tracks top-level runtime roots, payload extraction roots, and clean operations. That is intentionally coarse-grained: it gives operators a safe cleanup view without pretending every extracted payload file has a separate audit entry yet.

Inspect the ledger:

```sh
busierbox cleanup-ledger
busierbox cleanup-ledger --json
```

Preview cleanup:

```sh
busierbox clean --dry-run
busierbox rshell cleanup --dry-run
```

Apply runtime cleanup:

```sh
busierbox clean --ledger
```

External cleanup is opt-in only:

```sh
busierbox clean --external --apply
busierbox rshell cleanup --external --apply
```

Default cleanup removes only the BusierBox runtime root. It does not remove `/root/.ssh` entries or other external state unless the operator explicitly requests external cleanup.

No-residue mode is best-effort ephemeral runtime. It removes the selected extraction root after foreground payload commands and records top-level paths in the cleanup ledger, but it is not forensic no-trace execution.
