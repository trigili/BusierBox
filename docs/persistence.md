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
`persistence --survey --json` also includes `summary` counts,
`api_collections` metadata with explicit `count`, `summary_key`, and
backward-compatible `count_summary_key` fields, stable `primary_key` names for
the storage, method, and action records, plus index maps such as
`storage_by_class`, `storage_by_survives_reboot`, `methods_by_name`,
`methods_by_intrusiveness`, and `methods_by_requires_external_write` so
operator UIs can filter survey results without scraping the human table.
It also publishes an `actions` collection with `actions_by_name`,
`actions_by_category`, `actions_by_uploads_evidence`,
`actions_by_collects_dmesg`, `actions_by_starts_rshell`,
`actions_by_executes_operator_supplied_command`,
`actions_by_command_queue_enabled`, and
`actions_by_hidden_control_channel` indexes. These records describe available
recovery actions and their safety semantics before any hook is installed.

The method table covers reboot hook families such as OpenWrt/procd init
scripts, SysV/rcS, systemd units, cron `@reboot`, at jobs, `rc.local`,
hotplug.d, and shell profile hooks. Each method reports its target path,
intrusiveness, reversibility, and whether the hook is present.

Installation requires `--method` and either `--dry-run` or `--apply`.
The default action is `status-only`, which installs a visible no-op health
check. Explicit recovery actions are also available:

```sh
busierbox persistence install --method rc-local --name busierbox_recovery --dry-run
busierbox persistence install --method openwrt-procd --action rshell --external --apply
busierbox persistence install --method rc-local --action evidence-push --dry-run
busierbox persistence install --method rc-local --action evidence-then-rshell --external --apply
busierbox persistence install --method rc-local --action dmesg-push --external --apply
busierbox persistence install --method cron-reboot --action command --dry-run -- 'busierbox rshell start'
busierbox persistence install --method rc-local --action script --file ./recover.sh --external --apply
busierbox persistence install --method rc-local --name busierbox_recovery --external --apply
busierbox persistence status --name busierbox_recovery
busierbox persistence status --json --name busierbox_recovery
busierbox persistence uninstall --method rc-local --name busierbox_recovery --external --apply
```

Actions:

- `status-only`: run `busierbox persistence status`; this is the conservative default.
- `rshell`: run `busierbox rshell start` with the artifact's effective runtime config.
- `evidence-push`: upload a generated BusierBox evidence summary to the configured receive-only file service.
- `evidence-then-rshell`: upload generated evidence, then start `rshell` only if the upload command succeeds.
- `dmesg-push`: capture `dmesg` to a temporary file under the BusierBox runtime root, upload it as evidence, then remove the temporary file.
- `command`: run the explicit command provided after `--`.
- `script`: copy `--file` to `/usr/bin/<name>.recovery.sh` and run it from the hook.

Real-root changes require `--external --apply`. Fake-root tests can use
`--root local/fake-root` without `--external`. Created or modified paths are
recorded in the cleanup ledger. Existing hook files are backed up before a
marked BusierBox block is appended. Hook blocks include action metadata and the
generated command between `BEGIN BUSIERBOX RECOVERY` and `END BUSIERBOX
RECOVERY` markers. Uninstall removes only those marked blocks and staged
BusierBox files.

Evidence actions are explicit crash/reboot workflows for lab targets that panic
or reboot during testing. They do not add a hidden control channel, do not
execute operator-supplied commands, and still require the target artifact to be
configured with an operator host/file-service before upload can succeed.
`persistence --survey --json` reports all available action semantics, while
`persistence status --json` reports each installed action's category and
semantics, including whether it uploads evidence, captures `dmesg`, starts
`rshell` after evidence upload, executes an operator-supplied command, enables
a command queue, or creates a hidden control channel. The summary mirrors compact
counts such as available/installed evidence uploads, `dmesg` actions, `rshell` actions, and
operator-supplied command actions for audits. The JSON also includes
`api_collections.installations` with the same count and summary-key metadata,
`primary_key: method`, `installations_by_method`, `installations_by_action`, and
`installations_by_category` maps whose values are indexes into the
`installations` array, plus composite `installations_by_method_action` and
`installations_by_category_action` maps for direct lookups such as
`rc-local:evidence-push` or `evidence:dmesg-push`. This lets operator UIs jump
directly to evidence, reverse-shell, command, or status hooks without
rescanning the full list. Summary booleans also state whether every installed
hook requires an external write and whether any hook executes an
operator-supplied command.

`busierbox recovery` remains as a deprecated compatibility alias. Internal hook
markers still use `BUSIERBOX RECOVERY` so older cleanup/status checks keep
working, but new help and docs prefer `persistence`.
