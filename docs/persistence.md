# Persistence

`busierbox persistence` surveys and manages explicit, authorized lab
persistence/recovery hooks. It is not stealth persistence: survey and plan modes
never modify the target, and writes require an explicit method plus `--apply`.

```sh
busierbox persistence --survey
busierbox persistence --plan
busierbox persistence --survey --json
```

The survey reports likely persistent storage (`/overlay`, `/root`, `/etc`,
`/usr/bin`) separately from volatile locations (`/tmp`, `/dev/shm`) and shows
whether each candidate path exists and appears writable.

The method table covers reboot hook families such as OpenWrt/procd init
scripts, SysV/rcS, systemd units, cron `@reboot`, at jobs, `rc.local`,
hotplug.d, and shell profile hooks. Each method reports its target path,
intrusiveness, reversibility, and whether the hook is present.

Installation requires `--method` and either `--dry-run` or `--apply`:

```sh
busierbox persistence install --method rc-local --name busierbox_recovery --dry-run
busierbox persistence install --method rc-local --name busierbox_recovery --external --apply
busierbox persistence status --name busierbox_recovery
busierbox persistence uninstall --method rc-local --name busierbox_recovery --external --apply
```

Real-root changes require `--external --apply`. Fake-root tests can use
`--root local/fake-root` without `--external`. Created or modified paths are
recorded in the cleanup ledger. Existing hook files are backed up before a
marked BusierBox block is appended.

`busierbox recovery` remains as a deprecated compatibility alias. Internal hook
markers still use `BUSIERBOX RECOVERY` so older cleanup/status checks keep
working, but new help and docs prefer `persistence`.
