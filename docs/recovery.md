# Reboot Recovery

`busierbox recovery` is a deprecated compatibility alias for
`busierbox persistence`.

Use the primary command documented in [persistence.md](persistence.md):

```sh
busierbox persistence --survey
busierbox persistence --plan
busierbox persistence install --method rc-local --dry-run
busierbox persistence install --method openwrt-procd --action rshell --external --apply
busierbox persistence install --method rc-local --action evidence-push --dry-run
busierbox persistence install --method rc-local --action dmesg-push --external --apply
```

The alias remains available so older scripts keep working. New docs, help text,
and examples should prefer `persistence`.

Persistence/recovery is for authorized lab reboot recovery. It is visible and
reversible: survey and plan modes do not modify the target, real-root writes
require explicit `--external --apply`, hook blocks are marked, and uninstall
removes only BusierBox-marked blocks and staged BusierBox files.

Evidence actions (`evidence-push`, `evidence-then-rshell`, and `dmesg-push`)
are explicit crash/reboot workflows. They upload target-initiated evidence to
the configured receive-only operator file service, remain visible in the hook
body and status JSON, and do not add a command queue or hidden control channel.
JSON status also exposes per-action semantics such as evidence upload, `dmesg`
capture, `rshell` chaining, and whether the action executes an
operator-supplied command.
