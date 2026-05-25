# GL.iNet Integration Harness

`scripts/integration-glinet` builds BusierBox artifacts, copies them to a
GL.iNet exemplar, runs selected cases, captures logs, and writes a JSON summary.

The default target is `root@192.168.8.1` and the default target preset is
`glinet-mt7621-openwrt-musl`. If the target is unreachable, the harness skips
cleanly unless `--require-target` is passed.

## Prerequisites

- SSH access to the router, usually `root@192.168.8.1`.
- Enough free space under `/tmp` for the artifact and extraction tests.
- Buildroot prerequisites already installed for normal BusierBox packaging.
- For reverse shell cases, the operator host must be reachable from the router.
  Use `--operator-host <ip>` if auto-detection picks the wrong address.

## Common Runs

List available cases:

```sh
scripts/integration-glinet --case list
```

Run the default safe survey case:

```sh
scripts/integration-glinet --host root@192.168.8.1 --operator-host auto
```

Run all safe cases:

```sh
scripts/integration-glinet --host root@192.168.8.1 --operator-host auto --all-safe
```

Run one reverse shell case:

```sh
scripts/integration-glinet --host root@192.168.8.1 --operator-host 192.168.8.241 --case builtin-core-shell
```

Reuse an existing artifact instead of rebuilding:

```sh
scripts/integration-glinet --artifact dist/busierbox-mipsel-linux-4.x-musl-full --case survey-core
```

## Cases

- `survey-core`: builds the `survey-core` payload preset, runs
  `survey --json` and `config-info`, and checks that core-only mode does not
  require payload extraction.
- `default-extract-help`: builds the `default` payload preset, verifies zero-arg
  help-like behavior, then runs `extract`, `doctor`, and `config-info`.
- `builtin-core-shell`: builds the builtin TLS shell preset, starts a local
  scripted `tls-shell` listener, and verifies a marker from the target shell.
- `zero-arg-builtin`: verifies zero-arg rshell auto background behavior, status,
  stop, and a scripted TLS shell marker.
- `socat-rescue`: builds the socat preset, verifies staged socat, and proves a
  scripted TLS shell marker when the staged socat supports `OPENSSL:` addresses.
  The harness builds this case in an isolated dynamic Buildroot output tree so
  socat can link with OpenSSL without mutating the static-first default cache.
- `ssh-operator`: starts the SSH reverse-forward listener and validates that
  disabled authkeys mode does not change `/root/.ssh`.

The safe cases avoid persistent router changes and keep work under `/tmp`.
Root-copy/root-merge authkeys tests are intentionally behind
`--include-root-write-tests`; the harness currently reserves that flag and does
not run root-writing cases by default.

## Logs And Summary

Every run writes under:

```text
local/integration-runs/<timestamp>/
```

Each case directory contains build logs, generated config, SSH/SCP transcripts,
target facts, target command output, server logs, cleanup logs, and post-case
captures for:

- `busierbox manifest --json`
- `busierbox doctor --json` when available, falling back to `doctor`
- `busierbox cleanup-ledger --json`
- `busierbox clean --dry-run`
- `busierbox rshell status --json`

The final
machine-readable result is:

```text
local/integration-runs/<timestamp>/summary.json
```

The summary records `pass`, `fail`, or `skip` per case, artifact path and hash,
remote workdir, and the local log directory.

Remote workdirs default to `/tmp/busierbox-itest-<timestamp>-<case>` and are
removed after each case unless `--keep-remote` is passed.
