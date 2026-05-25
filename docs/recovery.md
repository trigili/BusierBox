# Reboot Recovery

`busierbox recovery` is for authorized lab recovery, not stealth persistence.
Survey and plan modes never modify the target:

```sh
busierbox recovery --survey
busierbox recovery --plan
busierbox recovery --survey --json
```

The survey enumerates reboot hook families such as OpenWrt/procd init scripts,
SysV/rcS, systemd units, cron `@reboot`, at jobs, `rc.local`, hotplug.d, and
shell profile hooks. Each method reports intrusiveness, reversibility, external
write requirements, and whether it normally survives reboot.

The survey also separates likely persistent storage (`/overlay`, `/root`,
`/etc`, `/usr/bin`) from volatile locations (`/tmp`, `/dev/shm`) and reports
whether each candidate path exists and appears writable.

Installation requires an explicit method and either `--dry-run` or `--apply`:

```sh
busierbox recovery install --method rc-local --name busierbox_recovery --dry-run
busierbox recovery install --method rc-local --name busierbox_recovery --external --apply
busierbox recovery status --name busierbox_recovery
busierbox recovery uninstall --method rc-local --name busierbox_recovery --external --apply
```

Real-root changes require `--external --apply`. Fake-root tests can use
`--root local/fake-root` without `--external`. Created or modified recovery
paths are recorded in the cleanup ledger. Existing hook files are backed up
before a marked BusierBox block is appended.
