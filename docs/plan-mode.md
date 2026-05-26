# Plan Mode

`busierbox plan` previews filesystem, process, and network impact before
running operations that can extract payloads, start reverse access, clean
runtime state, or install recovery hooks.

Supported forms:

```sh
busierbox plan
busierbox plan --json
busierbox plan extract
busierbox plan rshell
busierbox plan clean
busierbox plan recovery install --method openwrt-procd --action rshell
busierbox plan recovery install --method cron-reboot --action command -- 'busierbox rshell start'
```

The command is read-only. It reports:

- paths it would create, modify, or remove
- processes or transports it would start
- operator endpoints it would connect to
- rshell session policy (`single`, `reconnect`, or `persistent`)
- whether real-root external writes would be required
- runtime root and cleanup ledger paths
- no-residue cleanup implications where relevant
- recovery method/action implications
- trailer override state and effective config source

JSON output is intended for integration harnesses:

```sh
busierbox plan rshell --json | python3 -m json.tool
```

Plan mode uses the effective runtime config, so post-build trailer overrides are
reflected in the output. Config precedence remains compiled defaults, trailer
overrides, environment overrides, then explicit CLI flags where a command
supports them.
