# GL.iNet Integration Harness

`scripts/integration-glinet` builds BusierBox artifacts, copies them to a
GL.iNet exemplar, runs selected cases, captures logs, and writes a JSON summary.
Use `scripts/busierbox-bringup` first when onboarding an unknown target; use
this integration harness when validating known cases repeatedly.

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

The safe set includes a `trailer-runtime-override` case. That case copies the
built artifact, applies allowlisted post-build runtime overrides with
`scripts/artifact-config`, and verifies on the target that `runtime-config`,
`config-info`, and `rshell status --json` report the trailer-derived effective
configuration.

The safe set also includes `recovery-fakeroot`, which exercises recovery
install, status, and uninstall against a fake root inside the remote workdir.
It does not write to the target's real `/etc` or `/usr/bin`; real-root recovery
checks remain opt-in through explicit external-write cases.

`no-residue-cleanup` builds a no-residue artifact, runs a normal BusyBox payload
command, then terminates a foreground payload command and verifies that the
temporary runtime root is removed in both paths.
No-residue is best-effort ephemeral runtime cleanup, not forensic no-trace
execution. `BB_NORESIDUE_LEVEL=aggressive` minimizes BusierBox runtime residue
more strongly, but still does not claim stealth.

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
- `busierbox doctor --json`
- `busierbox runtime-config --json`
- `busierbox cleanup-ledger --json`
- `busierbox plan --json`
- `busierbox plan extract --json`
- `busierbox plan rshell --json`
- `busierbox plan clean --json`
- `busierbox plan recovery install --method openwrt-procd --action rshell --json`
- `busierbox plan recovery install --method cron-reboot --action command --json -- 'busierbox rshell start'`
- `busierbox clean --dry-run`
- `busierbox clean --dry-run --json`
- `busierbox clean --dry-run --external --json`
- `busierbox clean --external`
- `busierbox rshell status --json`
- `busierbox recovery status --json`

The harness validates captured `*-json.log` files locally after each command,
so JSON regressions fail the case even when the target does not provide Python
or another JSON parser.

The external clean capture intentionally runs without `--apply` so the harness
records the refusal path without mutating target-owned files. Root-writing
integration coverage remains opt-in behind `--include-root-write-tests`.

The final
machine-readable result is:

```text
local/integration-runs/<timestamp>/summary.json
```

The summary records `pass`, `fail`, or `skip` per case, artifact path, artifact
hash, artifact size, duration, remote workdir, local log directory, aggregate
status counts, and `failure_reasons` entries with the case, status, reason, and
log path.

Each case also records normalized phase status in `phases`:

```json
{
  "build": "pass",
  "transfer": "pass",
  "run": "pass",
  "validation": "pass",
  "cleanup": "pass"
}
```

The allowed phase values are `pass`, `fail`, `skip`, and `pending`. `build`
covers config generation and artifact packaging, `transfer` covers remote
staging and target fact capture, `run` covers the case-specific target workflow,
`validation` covers post-case BusierBox JSON/log captures, and `cleanup` covers
remote teardown.

Render the latest run:

```sh
scripts/integration-report latest
scripts/integration-report local/integration-runs/<timestamp>/summary.json --json
```

Compare two runs:

```sh
scripts/integration-compare \
  local/integration-runs/<old>/summary.json \
  local/integration-runs/<new>/summary.json
```

The report tool prints a compact case table with build, transfer, run,
validation, cleanup, final status, duration, artifact size/hash, log path, and
failure reason. When an operator `events.jsonl` is attached to the run summary,
the report also shows structured event totals, invalid-line count, first/latest
event timestamps, event counts, level counts, service counts, service/event
counts, and a recent-event tail. If the summary includes
`release_self_test_json`, the report also surfaces generated release self-test
diagnostics, including artifact/tuple/device counts and command-queue safety
counters, including operator-supplied command execution counts. When the
self-test JSON includes normalized `diagnostic_records`, the text report also
prints record totals plus status/category counts and highlights the
`command_queue_safety` record; the JSON report exposes the same aggregate fields
plus remote and session count maps for automation. The compare tool classifies
regressions, new failures, fixed cases, new or removed cases, artifact hash
changes, artifact size deltas, and duration deltas when both summaries include
timing data.

When a release bundle is produced as part of an integration run, run the
generated `scripts/release-self-test` inside that bundle before copying
artifacts to the target. That keeps release-helper, checksum, tuple-layout, and
manifest problems visible before target execution starts.

Remote workdirs default to `/tmp/busierbox-itest-<timestamp>-<case>` and are
removed after each case unless `--keep-remote` is passed.
