# Plan Mode

`grit plan` previews filesystem, process, and network impact before
running operations that can extract payloads, start reverse access, clean
runtime state, or install recovery hooks.

Supported forms:

```sh
grit plan
grit plan --json
grit plan extract
grit plan rshell
grit plan command-queue
grit plan clean
grit plan recovery install --method openwrt-procd --action rshell
grit plan recovery install --method cron-reboot --action command -- 'grit rshell start'
```

The command is read-only. It reports:

- paths it would create, modify, or remove
- processes or transports it would start
- operator endpoints it would connect to
- rshell session policy (`single`, `reconnect`, or `persistent`)
- whether real-root external writes would be required
- runtime root and cleanup ledger paths
- no-residue cleanup policy and limits where relevant
- command-queue polling interval and mode-record implications where relevant
- recovery method/action implications
- trailer override state and effective config source

JSON output is intended for integration harnesses:

```sh
grit plan rshell --json | python3 -m json.tool
```

The `extract`, `clean`, and `rshell` JSON plans include a `noresidue_policy`
object with the active state, configured level, cleanup scope, best-effort
guarantee, aggressive-mode residue-minimization flag, forensic-no-trace
disclaimer, and external-write boundary. Text plans expose the same fields as
`noresidue_policy_*` lines.

The `rshell` JSON plan includes both `session_semantics` and
`session_policy_summary`, matching `rshell status --json` so operator tooling
can render single/reconnect/persistent behavior and policy errors without
duplicating policy logic.
The `command-queue` JSON plan includes flat `mode_records`, lookup maps, a
`mode_summary`, and `api_collections.mode_records` metadata so operator UIs can
show which polling mode would be started without inferring behavior from prose.
The `recovery install` JSON plan includes `action_category`, evidence/dmesg,
rshell-chaining, operator-supplied command, command-queue, hidden-channel, and
self-reinstall booleans, plus an `action_semantics` object with the same fields.
This lets operator tooling distinguish evidence upload hooks from reverse-shell
or operator-command hooks before any `--apply` operation.

Plan mode uses the effective runtime config, so post-build trailer overrides are
reflected in the output. Config precedence remains compiled defaults, trailer
overrides, environment overrides, then explicit CLI flags where a command
supports them.
