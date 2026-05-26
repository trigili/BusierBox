# Reboot Recovery

`busierbox recovery` is a deprecated compatibility alias for
`busierbox persistence`.

Use the primary command documented in [persistence.md](persistence.md):

```sh
busierbox persistence --survey
busierbox persistence --plan
busierbox persistence install --method rc-local --dry-run
busierbox persistence install --method openwrt-procd --action rshell --external --apply
```

The alias remains available so older scripts keep working. New docs, help text,
and examples should prefer `persistence`.

Persistence/recovery is for authorized lab reboot recovery. It is visible and
reversible: survey and plan modes do not modify the target, real-root writes
require explicit `--external --apply`, hook blocks are marked, and uninstall
removes only BusierBox-marked blocks and staged BusierBox files.
