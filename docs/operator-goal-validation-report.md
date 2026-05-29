# Operator Goal Validation Report

Date: 2026-05-29
Branch: `main`

This report records current evidence for the operator/server hardening goal in
`local/GOAL.md`. It is a validation snapshot, not a claim that the entire goal is
complete.

## What Changed

- Server lifecycle and status handling now center on structured service/session
  state in `scripts/busierbox-server`, with `--status`, `--stop`,
  `--json-status`, and `--api-status` surfaces for operator and future frontend
  use.
- The workbench exposes services, staged files, uploads, sessions, events,
  generated target commands, build/config fields, background jobs, release
  browsing, and pager-based local path inspection without target execution by
  default. Curses status now badges target attribution and legacy no-target
  activity in the top area, and details panes show target identity for staged
  files, uploads, and sessions when known.
- Reverse shell lifecycle behavior is explicit through
  `BB_RSHELL_SESSION_POLICY=single|reconnect|persistent`, with status, plan,
  manifest, runtime-config, menuconfig, release, and server metadata exposure.
  The workbench guided build config now uses the same target-side transport
  names as the runtime config: `ssh|socat|builtin|none`.
- Structured JSONL events are used for service starts/stops, bind failures,
  connections, uploads, fetches, staged-file changes, command-queue activity,
  jobs, and shutdown-related records.
- `busierbox reality-test` provides local capability, constraint, and explicit
  operator-side upload/fetch probes, with JSON indexes for integration and
  bringup consumers.
- Compatibility scoring now distinguishes exact, likely, heuristic, unsafe, and
  incompatible selections across survey recommendations, release search, release
  indexes, and bringup output.
- No-residue behavior exposes `BB_NORESIDUE_LEVEL=best-effort|aggressive`, dry
  run residue plans, cleanup counters, aggressive-mode log policy boundaries,
  and non-forensic caveats in user-facing status and docs.
- Recovery workflows include visible evidence push, evidence-then-rshell, and
  dmesg-push actions behind explicit apply and external-write gates.
- `scripts/busierbox-bringup` now summarizes the requested ten-step onboarding
  flow through `bringup_flow_steps`, lookup maps, summary counts, and API
  collection metadata.
- Command queue behavior is explicit and opt-in. The current build supports
  visible polling, queue records, delivery/rejection metadata, result upload
  records, daemon status/stop state, target poll-setting headers, operator
  event metadata, API/status indexes, and safety reporting. Target command
  execution remains intentionally unsupported.
- Multi-target status tracks target ids, labels, aliases, identity source and
  confidence, target filters, target-scoped staged records, uploads, fetches,
  sessions, events, command-queue records, generated target commands, capability
  evidence, and compatibility report labels. Status also reports
  target-attributed versus legacy no-target uploads, fetches, and sessions so
  old single-target traffic stays valid but auditable. Target-filter records now
  distinguish generated command activity from observed target activity, mirror
  selected-target capability and compatibility evidence, and expose the same
  compact selected-target summary in JSON/API status, `--status`, fallback
  workbench output, and the curses workbench banner.
- Event-log status distinguishes invalid logs, truncated tails, omitted records,
  and intentionally suppressed tails. JSON/API status, `--status`, and fallback
  workbench output expose whether the event tail has records, has omitted
  records, or is empty only because `--event-limit 0` was requested.
- Local/offline release indexes expose deduplicated artifacts, tuple/device/tool
  lookups, payload preset and feature lookups, provider status, Doom WAD
  metadata, command-queue safety metadata, corresponding-source filters, and
  recommendation records.
- Repository and release metadata now declare BusierBox-maintained code as
  `GPL-2.0-or-later`, preserve third-party component license inventory, and
  document current GPLv2-compatible combined distribution posture and
  corresponding-source requirements for BusyBox, Buildroot, doom-ascii, and
  miniz. The policy records the upstream evidence sources used for that
  assessment, and release status, release indexes, release self-tests, and
  licensing checks expose or validate those evidence records.
- Stale Doom/Dune feature branches have been pruned from the local and remote
  branch lists; `main` is the only remaining branch.

## Evidence Map

Server lifecycle:
- `scripts/busierbox-server --status`
- `scripts/busierbox-server --stop`
- `tests/smoke/busierbox-server.py`

Workbench and future API status:
- `scripts/busierbox-server --json-status`
- `scripts/busierbox-server --api-status`
- `docs/release-bundles.md`
- `tests/smoke/busierbox-server.py`

Reverse shell policy:
- `src/applet_rshell.c`
- `src/runtime_config.c`
- `src/applet_manifest.c`
- `tests/smoke/rshell-lifecycle.sh`
- `tests/smoke/manifest-metadata.sh`

Reality test and compatibility:
- `src/applet_reality_test.c`
- `scripts/config-from-survey`
- `scripts/find-artifact`
- `tests/smoke/reality-test.sh`
- `tests/smoke/config-from-survey.sh`
- `tests/smoke/release-repo-index.sh`

No-residue cleanup:
- `src/applet_clean.c`
- `src/runtime_paths.c`
- `docs/cleanup-ledger.md`
- `tests/smoke/clean-json.sh`
- `tests/smoke/runtime-modes.sh`

Recovery and persistence:
- `src/applet_recovery.c`
- `docs/recovery.md`
- `docs/persistence.md`
- `tests/smoke/recovery.sh`

Bringup:
- `scripts/busierbox-bringup`
- `docs/bringup.md`
- `docs/survey-and-bringup.md`
- `tests/smoke/integration-glinet-harness.sh`

Command queue:
- `src/applet_command_queue.c`
- `scripts/busierbox-server`
- `docs/command-queue.md`
- `docs/release-bundles.md`
- `tests/smoke/command-queue.sh`
- `tests/smoke/busierbox-server.py`

Multi-target status:
- `scripts/busierbox-server`
- `docs/release-bundles.md`
- `tests/smoke/busierbox-server.py`

Release and offline artifact browsing:
- `scripts/make-release`
- `scripts/index-release-repo`
- `scripts/find-artifact`
- `scripts/release-self-test`
- `scripts/busierbox-server --status`
- `tests/smoke/release-bundles.sh`
- `tests/smoke/release-repo-index.sh`
- `tests/smoke/busierbox-server.py`

Licensing:
- `LICENSE`
- `LICENSE.busierbox`
- `NOTICE`
- `docs/licensing.md`
- `manifests/license-policy.json`
- `scripts/check-licensing`
- `scripts/release-self-test --json`
- `scripts/index-release-repo`
- `scripts/find-artifact`
- `scripts/busierbox-server --status`
- `tests/smoke/licensing.sh`
- `tests/smoke/release-bundles.sh`
- `tests/smoke/release-repo-index.sh`
- `tests/smoke/busierbox-server.py`

## Verification Run

Commands run for the most recent committed slices:

```sh
python3 -m py_compile scripts/busierbox-server tests/smoke/busierbox-server.py
tests/smoke/rshell-transport-names.sh
git diff --check
tests/smoke/busierbox-server.py
```

Result:

- The server smoke test passed after target-filter state records were expanded
  with filtered/unfiltered activity counts, observed-activity counts that
  exclude generated target commands, selected-target capability/compatibility
  evidence, and lookup indexes for future API clients.
- The server smoke test passed after `--status`, fallback workbench output, and
  the curses workbench banner were aligned on the same target-filter summary,
  including observed target activity and selected-target evidence.
- The server smoke test passed after event-log state records gained
  `tail_has_records`, `tail_has_omitted_records`, and
  `tail_empty_due_to_limit`, with the same state visible in human operator
  views for `--event-limit 0`.
- The server smoke test passed after target records were extended to retain
  compatibility evidence from uploaded target reports, including lookup maps and
  summary counts by compatibility label, baseline label, release, and payload
  preset.
- The server smoke test passed after guided workbench config examples were
  aligned with the accepted `BB_RSHELL_TRANSPORT=ssh|socat|builtin|none`
  values. This keeps target-side transport settings separate from operator
  listener names such as `tls-shell` and `plain-shell`.
- The server smoke test passed after the release summary text was extended to
  expose corresponding-source posture.
- `scripts/busierbox-server --status` and the TUI release browser now render
  `corresponding_source` with required/status/input-count/package-audit fields
  alongside the existing release license summary.
- JSON/API status already exposes the same fields in `release.release_license`,
  release license records, and release license indexes.

Recent release corresponding-source verification also included:

```sh
python3 -m py_compile scripts/make-release scripts/index-release-repo scripts/find-artifact
sh -n tests/smoke/release-bundles.sh
sh -n tests/smoke/release-repo-index.sh
git diff --check
tests/smoke/release-bundles.sh
tests/smoke/release-repo-index.sh
```

Result:

- `scripts/release-self-test --json` now includes `api`, `api_resources`,
  resource lookup maps, and `api_collections.diagnostic_records`, matching the
  API discovery shape used by other operator-facing JSON surfaces.
- `scripts/release-self-test --json` now validates and reports
  `corresponding_source_required`, `corresponding_source_status`,
  corresponding-source input counts, and package license audit requirements in
  both flat diagnostics and the normalized `license_inventory` record.
- `scripts/find-artifact` can filter release artifacts by corresponding-source
  requirement/status and package-audit requirement, and recommendation JSON
  exposes matching lookup maps for future operator/UI clients.

Recent GPL/license evidence verification also included:

```sh
python3 -m json.tool manifests/license-policy.json
scripts/check-licensing
make check-licensing
tests/smoke/licensing.sh
python3 -m py_compile scripts/find-artifact scripts/index-release-repo scripts/busierbox-server tests/smoke/busierbox-server.py
tests/smoke/release-repo-index.sh
python3 tests/smoke/busierbox-server.py
python3 -m py_compile scripts/make-release
sh -n tests/smoke/release-bundles.sh
tests/smoke/release-bundles.sh
```

Result:

- `manifests/license-policy.json` records checked evidence sources for BusyBox,
  Buildroot, doom-ascii, and miniz, including URLs, license identifiers, and a
  verification date.
- `scripts/check-licensing`, `make check-licensing`, and
  `tests/smoke/licensing.sh` validate that the repository declares
  `GPL-2.0-or-later`, preserves the current GPLv2-compatible stack assessment,
  and keeps the expected evidence references.
- `scripts/busierbox-server --status`, `--json-status`, and API status expose
  release license evidence counts, verification date, evidence-source lookup
  maps, and evidence-source/license lookup maps.
- `scripts/index-release-repo` and `scripts/find-artifact --recommendation-json`
  surface evidence-source indexes and summary counts for offline release
  browsers.
- `scripts/release-self-test --json` includes license evidence fields in both
  flat diagnostics and the normalized `license_inventory` diagnostic record.

Recent no-residue verification also included:

```sh
make
tests/smoke/plan-json.sh dist/busierbox.core
tests/smoke/runtime-modes.sh
tests/smoke/clean-json.sh dist/busierbox-native-full
git diff --check
make smoke-test
```

Result:

- `make smoke-test` passed after the latest no-residue policy surface update.
- `tests/smoke/plan-json.sh dist/busierbox.core` passed, covering no-residue
  policy JSON/text output from plan surfaces.
- `tests/smoke/runtime-modes.sh` passed, covering aggressive no-residue
  `config-info`, `doctor`, manifest, plan, residue-plan, fallback fail-closed,
  and signal cleanup behavior.
- `tests/smoke/clean-json.sh dist/busierbox-native-full` passed, covering dry
  run residue plans, cleanup counters, ledgered paths, external cleanup gating,
  and invalid ledger handling.

The latest no-residue policy surfaces explicitly report:

- `persistent_target_logs_default`
- `stdout_stderr_log_suppression`
- `in_memory_log_guarantee=false`

These fields are exposed in policy JSON/text without claiming forensic
in-memory execution or guaranteed no-trace behavior.

Recent branch cleanup evidence:

```sh
git fetch --prune origin
git branch -a --verbose --no-abbrev
git remote prune origin --dry-run
git ls-remote --heads origin
```

Result:

- The stale Doom/Dune feature branches were absent locally and remotely; only
  `main`/`origin/main` remained.

Earlier full-goal verification also included:

```sh
sh -n scripts/busierbox-bringup tests/smoke/integration-glinet-harness.sh
tests/smoke/integration-glinet-harness.sh
git diff --check
make smoke-test
make test-qemu-user
make test-qemu-system
scripts/make-release --name smoke-goal --targets native --payload-presets survey-core,default
scripts/release-self-test --release-dir dist/releases/smoke-goal-20260529-051526
scripts/release-self-test --release-dir dist/releases/smoke-goal-20260529-051526 --json
```

Earlier result:

- `make smoke-test` passed.
- `make test-qemu-user` passed for `native`; cross-target rows skipped because
  the corresponding cross artifacts or qemu interpreters were not present.
- `make test-qemu-system` completed with every matrix row skipped because the
  example environments are disabled by default.
- `scripts/make-release --name smoke-goal --targets native --payload-presets
  survey-core,default` built a native release at
  `dist/releases/smoke-goal-20260529-051526`.
- `scripts/release-self-test --release-dir
  dist/releases/smoke-goal-20260529-051526` passed, and the `--json` output
  parsed with `python3 -m json.tool`.

Recent full smoke coverage included:

- server lifecycle, status, stop, bind failure, stale state, TUI fallback, and
  workbench status checks
- event log writing and API indexes
- rshell policy validation and single/reconnect/persistent behavior
- reality-test JSON and active operator upload/fetch checks
- compatibility scoring fixtures, including old uClibc MIPS, big-endian MIPS,
  non-OpenWrt, low storage, noexec, read-only rootfs, and broken procfs inputs
- no-residue level config, dry-run residue plans, and cleanup counters
- no-residue aggressive log-policy boundaries
- recovery evidence-push fake-root behavior
- bringup recommend-only and release-selection paths
- command queue disabled-by-default, schema/status, polling, result upload, and
  no-execution safety boundaries
- command queue poll interval, jitter, backoff, max interval, and max poll
  settings surfaced through target state, target events, live poll request
  headers, server poll metadata, status maps, API indexes, and docs
- release bundle generation, release self-test, and release repository indexes

## Examples

Server lifecycle:

```sh
scripts/busierbox-server --status
scripts/busierbox-server --stop
```

Expected evidence includes configured versus actual service state, listener
PIDs, stale-state warnings, session root, staged-files path, and recent
sessions/uploads/fetches.

Reverse shell policy:

```sh
./busierbox rshell status --json
./busierbox plan rshell --json
```

Expected evidence includes `session_policy`, `session_semantics`,
`session_policy_summary`, retry timing, and no claim of session resume for
`reconnect` or `persistent`.

Event log:

```json
{"schema":1,"service":"file-service","event":"upload_complete","level":"info","details":{"target_id":"target-alpha","status":"stored"}}
```

Status surfaces expose event tails plus indexes by service, event, level,
remote, status, target id, target label, expected target id, command id, and
command hash.

Reality and compatibility:

```sh
./busierbox reality-test --json
scripts/config-from-survey --survey-json survey.json --reality-json reality.json --json
scripts/find-artifact --index release-index.json --survey-json survey.json --reality-json reality.json --recommendation-json
```

Expected evidence includes capability pass/fail/skipped counts, constraints
such as `/tmp` noexec or read-only rootfs, and compatibility labels from
`exact` through `incompatible` with reasons.

Command queue safety:

```sh
./busierbox command-queue status
./busierbox command-queue poll --json
scripts/busierbox-server --json-command-queue
```

Expected evidence shows disabled-by-default policy, metadata-only default,
explicit polling state, result upload records, and `execution_supported=false`
unless a future explicit execution implementation is added.

## Caveats

- `command-queue` execution is intentionally not implemented. Metadata delivery,
  rejection decisions, result upload, daemon status, poll-setting state, and
  server queue records are present; executing target-side operator commands
  remains a later explicit feature.
- Builtin TLS/plain shell transports do not claim PTY-backed interactive
  sessions where the implementation is pipe-backed.
- No-residue mode is operational cleanup hygiene, not forensic erasure.
- QEMU user/system and GL.iNet hardware gates are environment-dependent. The
  local qemu-user gate currently proves the native row and records skips for
  unavailable cross artifacts/interpreters. The qemu-system matrix is disabled
  by default, so it records skips until local kernels/root filesystems and
  enabled environment entries are supplied. GL.iNet hardware validation still
  requires a reachable target.
