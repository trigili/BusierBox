# Release Bundles

`scripts/make-release` builds or assembles a set of BusierBox artifacts into a
reusable release directory and tarball under `dist/releases/`.

Examples:

```sh
scripts/make-release --name lab-router-pack
scripts/make-release --name lab-router-pack --targets glinet-mt7621-openwrt-musl,mipsel-linux-4.x-musl --payload-presets survey-core,ssh-operator
scripts/make-release --name lab-router-pack --reverse-access-profiles builtin,ssh
scripts/make-release --name lab-router-pack --matrix release/matrices/iot-lab.json
scripts/make-release --name lab-router-pack --copy-layout
scripts/make-release --name lab-router-pack --include-missing-reports
scripts/make-release --name lab-router-pack --dry-run
```

Each release contains:

- `bin/`: built artifacts and per-artifact SHA256 files.
- `configs/`: generated per-target/per-preset configs.
- `manifests/`: artifact manifest/config-info output when available.
- `by-tuple/<arch>/<libc>/<kernel-floor>/<cpu-or-abi>/`: canonical
  compatibility tuple views with `README.txt`, `MANIFEST.txt`,
  `MANIFEST.json`, and per-tuple `bin/`, `configs/`, and `manifests/`.
- `devices/<alias>/`: device or exemplar aliases with `target.json`,
  `README.txt`, `notes.md`, and an `artifacts` pointer to the canonical tuple.
- `scripts/`: copied `artifact-config` plus wrapper helpers, release
  self-test, index, and finder tools.
- `docs/`: release, licensing, and runtime override notes.
- `LICENSE` and `NOTICE`: BusierBox GPL license text and short project license
  notice.
- `release.json`: build status, commit, safe build-host metadata, source-lock summary, selected matrix, artifact paths, canonical tuple paths, device aliases, checksums, and failures.
- `release-index.json`: searchable index for artifacts, tuples, devices,
  payload presets, present tools, reverse-access capabilities, and trailer
  support.
- `SHA256SUMS.original`: pristine bundle checksums.

The flat `bin/`, `configs/`, and `manifests/` paths are stable script-facing
paths. The tuple hierarchy is the human-facing layout: artifacts are grouped by
the actual compatibility tuple instead of by device name. For example, a
GL.iNet MT7621 exemplar and a generic `mipsel-linux-4.x-musl` build can both
map to `by-tuple/mipsel/musl/4.x/mips32r2-24kc/` when their tuple fields match.

By default, tuple and device views use symlinks back to the flat files, which
keeps tar releases compact. Use `--copy-layout` when unpacking on platforms
where symlinks are inconvenient; use `--symlink-layout` to request the default
explicitly.

Each per-tuple `MANIFEST.txt` summarizes the payload variants in that tuple:
native applets, BusyBox applets and core extraction behavior, staged heavy
tools, runtime mode, reverse-access defaults, trailer-overridable fields, size,
checksum, config path, and the statically extracted embedded payload manifest
path. The JSON manifest contains the same data in machine-readable form.
Missing or requested-but-unavailable tools are builder-facing negative
inventory and are omitted by default; pass `--include-missing-reports` to emit
`build-report.json` plus per-artifact `*.build-missing.json` files and include
those fields in tuple manifests.

When a matrix includes `version` or `include`, those values are preserved in
`release.json` for reproducibility. Set `include.source_lock` or
`include.sources_manifest` to copy `manifests/sources.lock.json` into the
bundle without relying on the CLI flag.

Matrix files can include a `configs` list. Each listed config is used as a
base config for every selected target/payload/format combination, and
`scripts/make-release` writes generated per-combination configs under
`configs/` without modifying the source config.

Reverse-access profiles are explicit opt-in selectors for existing payload
presets: `builtin` maps to `builtin-core-shell`, `ssh` maps to `ssh-operator`,
and `socat` maps to `socat-rescue`. They can be supplied with
`--reverse-access-profiles` or as `reverse_access_profiles` in a matrix file.

Trailer configuration after packaging:

```sh
scripts/configure-artifact bin/busierbox-native-default-full \
  --operator-host 192.168.8.241 \
  --transport builtin \
  --shell-port 22203 \
  --zero-arg-mode rshell

scripts/configure-all \
  --operator-host 192.168.8.241 \
  --transport builtin \
  --shell-port 22203
```

The helper scripts wrap the bundled `scripts/artifact-config`. They can show,
clear, import, export, and set allowlisted trailer keys. After a trailer edit,
they write `SHA256SUMS.configured` and update `SHA256SUMS` to match the current
configured bundle.

XOR trailer obfuscation is not encryption. Do not place credentials, private
keys, or other secrets in trailer overrides or release bundles.

Trailer overrides can adjust selected runtime/operator settings such as
operator host, ports, transport, run mode, zero-arg mode, no-residue level, and
log verbosity.
They cannot change target architecture, libc, kernel floor, static policy,
payload tools, heavy tools, dotfiles, overlays, or compiled features.

Release tooling does not enable network autorun or external writes by default.
Use payload presets and trailer overrides deliberately, and verify the resulting
bundle with:

```sh
scripts/verify-checksums --original
scripts/verify-checksums --configured
scripts/release-self-test
```

Use `scripts/release-find` to choose an artifact without reading every
manifest:

```sh
scripts/release-find --device glinet-mt1300
scripts/release-find --arch mipsel --libc musl --kernel 4.x
scripts/release-find --tool tcpdump
scripts/release-find --payload-preset survey-core
scripts/release-find --survey-json survey.json
scripts/release-find --survey-json survey.json --reality-json reality.json --json
```

`release-find` reports a compatibility label and reasons for the selected
artifact. Labels are `exact`, `likely`, `heuristic`, `unsafe`, and
`incompatible`. Tuple/device arguments produce exact tuple matching; survey and
reality-test JSON add target-specific scoring for arch, endian, libc, kernel
floor, CPU/ABI hints, `/tmp` noexec, read-only rootfs, low storage, failed
runtime execution, failed payload extraction, and partial procfs evidence.
JSON output includes a `selection` block with selected artifact, candidate and
eligible counts, threshold-filter count, active filters, max compatibility, and
the selection policy. Plain text output mirrors the counts and policy so an
operator can audit why a release artifact was selected without parsing JSON.
`release-index.json` and tuple `MANIFEST.json` include baseline compatibility
metadata for every artifact.

From a source checkout, the top-level helpers can target a bundle explicitly:

```sh
scripts/release-self-test --release-dir dist/releases/lab-router-pack
scripts/release-find --release-dir dist/releases/lab-router-pack --payload-preset survey-core
scripts/release-index --release-dir dist/releases/lab-router-pack --write
```

Use `scripts/release-index --write` after manual metadata edits to refresh
`release-index.json`.

For a directory containing multiple release bundles, build a local/offline
repository index:

```sh
scripts/index-release-repo dist/releases --write local/release-repo-index.json
scripts/find-artifact --index local/release-repo-index.json --device glinet-mt1300
scripts/find-artifact --index local/release-repo-index.json --tuple-path by-tuple/mipsel/musl/4.x/mips32r2-24kc
scripts/find-artifact --index local/release-repo-index.json --tool tcpdump --payload-preset survey-core
scripts/find-artifact --index local/release-repo-index.json --feature reverse-ssh --json
scripts/find-artifact --index local/release-repo-index.json --doom-wad doom.wad
scripts/find-artifact --index local/release-repo-index.json --device glinet-mt1300 --max-compatibility likely
scripts/find-artifact --index local/release-repo-index.json --device glinet-mt1300 --recommendation-json
```

The repository index reuses each bundle's `release-index.json`, records the
release name and directory for every artifact, deduplicates artifacts by sha256,
and indexes tuple, device, tool, payload preset, feature, artifact sha256,
release name, and tuple-path keys. The index preserves compatibility path maps
such as `tools_present`, `payload_presets`, and `features`, and also provides
full artifact-record maps named `artifacts_by_tool`,
`artifacts_by_payload_preset`, and `artifacts_by_feature` for TUI/web clients
that need to render details without rescanning every artifact. Composite maps
`artifacts_by_tool_payload_preset`, `artifacts_by_feature_payload_preset`, and
`artifacts_by_tuple_payload_preset` let clients jump directly to combinations
such as `tcpdump:survey-core`, `reverse-ssh:ssh-operator`, or
`by-tuple/mipsel/musl/4.x/mips32r2-24kc:full-debug` without intersecting
separate indexes. Provider audit maps `artifacts_by_provider_tool` and
`artifacts_by_provider_status` expose payload-manifest provider checks such as
`gdbserver` or `gdbserver:found` so offline pickers can surface local drop-in
status without opening each payload manifest. Doom audit maps
`artifacts_by_doom_wad_filename` and `artifacts_by_doom_wad_sha256` index
artifacts by staged WAD basename/hash, and `scripts/find-artifact` exposes the
same lookup through `--doom-wad` and `--doom-wad-sha256`. You can search by canonical tuple path directly with
`--tuple-path` when a survey or release manifest has already resolved the
target compatibility tuple. It does not download or rebuild anything.
`--recommendation-json` returns the selected artifact plus active filters,
match count, index counts, and the selection policy. The policy used to prefer lower-risk compatibility labels also prefers newer release metadata. Use
`--max-compatibility exact|likely|heuristic|unsafe|incompatible`
to reject artifacts above an operator-selected risk threshold instead of only
sorting them lower. Plain text output also prints `compatibility_reason=` lines so an
operator can see why the selected artifact was considered exact, likely,
heuristic, unsafe, or incompatible without parsing JSON.

## Operator Examples

First contact:

```sh
bin/busierbox-native-survey-core-full survey --json > survey.json
bin/busierbox-native-default-full config-info
bin/busierbox-native-default-full doctor
bin/busierbox-native-default-full manifest --json
```

Choose a GL.iNet exemplar artifact:

```sh
scripts/release-find --device glinet-mt1300
devices/glinet-mt1300/artifacts/README.txt
```

Configure a bundle for an operator endpoint after release:

```sh
scripts/verify-checksums --original
scripts/configure-all \
  --operator-host 192.168.8.241 \
  --transport ssh \
  --session-policy single \
  --ssh-port 2222 \
  --remote-forward-port 2200
scripts/verify-checksums --configured
```

Start explicit reverse access on the target:

```sh
./busierbox rshell status --json
./busierbox rshell start
```

`single` stops after the first successful shell session exits. `reconnect`
starts fresh sessions after disconnect up to the configured retry count, and
`persistent` keeps trying indefinitely; neither mode claims session resume.
`rshell status --json` includes `session_semantics` and
`session_policy_summary` so operator tooling can distinguish first-connect
retry, post-disconnect reconnects, persistent lifecycle, and fresh-session
reconnect behavior without parsing prose. The human `rshell status` output
also prints the same key booleans, including `stop_after_first_success`,
`reconnect_after_disconnect`, `persistent_lifecycle`,
`fresh_session_on_reconnect`, and `session_resume_supported`.

For the builtin TLS shell preset, prepare the operator listener and then run the
artifact explicitly:

```sh
scripts/busierbox-server --transport tls-shell --shell-port 22203
./busierbox rshell start
```

For the SSH operator preset, listen for the reverse SSH forward and connect
through the forwarded port:

```sh
scripts/busierbox-server --transport ssh --ssh-port 22
ssh -p 2200 root@127.0.0.1
```

For receive-only evidence uploads, start the operator file service. It accepts
target-initiated HTTP PUT/POST uploads over TLS by default, stores files under
`local/sessions/<timestamp>-file-service/files/`, and writes per-file metadata
JSON with source path, size, sha256, timestamp, and transfer status. It does
not send artifacts, execute commands, or provide callback RPC.

```sh
scripts/busierbox-server --file-service --file-port 22204
./busierbox put /tmp/evidence.txt
./busierbox survey push
./busierbox reality-test push
./busierbox manifest push
./busierbox config-push
./busierbox evidence push
```

When launched from a release bundle, the operator workbench and JSON status can
also browse release artifacts, device aliases, and tuple directories:

```sh
scripts/busierbox-server --tui
scripts/busierbox-server --json-status
scripts/busierbox-server --api-status
scripts/busierbox-server --stage-release-artifact by-tuple/native/host/host/host/bin/busierbox-native-default-full --list-staged
```

`--json-status` and `--api-status` include top-level `summary` and `warnings`
objects for frontend and automation consumers. Stale server-state records,
service errors, listener counts, command queue counts, command queue policy
validity, and release artifact/device/tuple counts can be read without
re-parsing the human status view. Service rows remain available in `services`,
and the same records are indexed by service name, actual state, configured
state, and port in `services_by_name`, `services_by_actual`,
`services_by_configured`, `services_by_port`, `services_by_pid`, and
`services_by_listener_pid` for frontend clients that need direct lookup without
reconstructing their own maps. Listener ports are exposed as `ports`,
`ports_by_number`, `ports_by_service`, and `ports_by_actual`. `summary` also
includes `service_actual_counts`, `service_configured_counts`, `port_count`,
and `port_actual_counts` for compact service and port dashboards.
The same document includes `generated_at` and a `paths` object for stable
discovery of server state, staged files, event logs, command queue records, and
the session root. `server_state` exposes the managed `server-state.json` path,
validity, service records, session records, and compact record counts for
frontends that need the persisted manager view. `path_status` mirrors those
paths with existence, parent-existence, expected-kind, readability, and
writability fields; compact path health counts are mirrored into `summary` as
`path_status_count`, `path_missing_count`, `path_parent_missing_count`, and
`path_not_writable_count`. `browser_paths` provides a normalized operator file
browser list for future TUI/web clients, covering operator ledgers, session
directories, upload/fetch metadata, staged sources, event logs, TLS files, and
release bundle files. The same records are grouped in `browser_paths_by_kind`,
`browser_paths_by_path`, `browser_paths_by_source_id`, and
`browser_paths_by_kind_source_id`. The composite kind/source map lets TUI and
future web clients jump directly to records such as
`upload-metadata:<session-id>` or `release-artifact:<release-path>` without
filtering the broader source-id group. Compact counts are exposed in
`browser_path_summary` and mirrored into `summary` as `browser_path_count`,
existence/readability/writability counts, and `browser_path_kind_counts`.
`staged_files_state` exposes the staged-files ledger
path, validity, request names, and raw staged-entry count. `command_queue_state`
exposes the command queue ledger path, validity, command ids, status counts,
and raw command count. Staged files are exposed as the existing `staged`
request map, an ordered `staged_records`
browser list, and lookup maps
`staged_by_request`, `staged_by_sha256`, and `staged_by_source_path`;
`summary` includes `staged_total_size`, `staged_source_exists_count`, and
`staged_source_missing_count` for staged-file health, plus `latest_staged_at`
for compact recency displays. Recent
upload and staged-fetch activity is exposed through top-level `uploads` and
`fetches` arrays plus lookup maps: `uploads_by_session`,
`uploads_by_filename`, `uploads_by_sha256`, `uploads_by_source_path`,
`uploads_by_stored_path`, `uploads_by_remote_addr`, `uploads_by_status`,
`fetches_by_session`, `fetches_by_request`, `fetches_by_sha256`,
`fetches_by_source_path`, `fetches_by_status`, `fetches_by_http_status`, and
`fetches_by_remote_addr`;
session browser records are exposed as `sessions`, `sessions_by_id`,
`sessions_by_service`, `sessions_by_state`, and
`sessions_by_exit_reason`, and `sessions_by_remote`. `session_root_state`
summarizes the session directory, recent session ids, service counts, and state
counts for file-browser views; aggregate counts remain in `summary`, including
`upload_total_size`, `fetch_total_size`, `upload_stored_exists_count`,
`upload_stored_missing_count`, `fetch_source_exists_count`,
`fetch_source_missing_count`, `upload_status_counts`, `fetch_status_counts`,
`fetch_http_status_counts`, `upload_remote_counts`, `fetch_remote_counts`,
`session_service_counts`, `session_state_counts`,
`session_exit_reason_counts`, and `session_remote_counts` for compact
dashboards.
`latest_upload_at`, `latest_fetch_at`, and `latest_session_updated_at` expose
recent activity timestamps without requiring clients to scan the full browser
records.
When running inside a release bundle, `release` includes artifact, device, and
tuple browser lists plus `artifacts_by_release_path`, `artifacts_by_name`,
`artifacts_by_sha256`, `artifacts_by_payload_preset`,
`artifacts_by_compatibility`, `artifacts_by_source`, `artifacts_by_tool`,
`artifacts_by_provider_tool`, `artifacts_by_provider_status`,
`devices_by_name`, and `tuples_by_path` lookup maps. Release artifact
state is exposed separately as `release_state` with release directory,
`release.json` and `release-index.json` paths, presence, validity, parse
health, `bin`/`scripts` directory health, browser counts, release name, and
errors. Compact booleans are mirrored into `summary` as `release_present`,
`release_valid`, `release_json_valid`, and `release_index_valid` so API
clients can distinguish "not in a bundle" from "bundle-like directory with a
broken manifest". Release artifact aggregates are exposed as
`release.artifact_stats` and mirrored into `summary`
as `release_artifact_total_size`, `release_artifact_compatibility_counts`,
`release_artifact_payload_preset_counts`, `release_artifact_source_counts`,
`release_artifact_tool_counts`, `release_artifact_provider_tool_counts`, and
`release_artifact_provider_status_counts`. Doom WAD references are counted as
`release_artifact_doom_wad_count`.
Device and tuple artifact reference totals are mirrored as
`release_device_artifact_reference_count` and
`release_tuple_artifact_reference_count`.
Release `tuple_summary` records and generated `release-index` artifact rows
also carry `tool_provider_status`, which mirrors payload-manifest provider
checks such as the effective gdbserver local drop-in search path, executable
state, and checker output. Doom-enabled payloads also carry `doom_wads`
records with the staged WAD basename, size, and sha256 so release consumers can
audit bundled game data without unpacking the payload manifest or seeing the
builder's local source path.
Generated target commands are exposed both as legacy strings in
`target_commands` and as structured `target_command_records` entries with
purpose, service, side, network, explicit-target-action, and
operator-supplied-command execution metadata. The generated `rshell` command
record also carries `metadata.session_policy`, validity, errors, and
`session_semantics` so operator UIs can distinguish single-shot, reconnect,
and persistent fresh-session behavior next to the command itself.
`target_commands_by_service`,
`target_commands_by_request`, `target_commands_by_side`, and
`target_commands_by_purpose` index those records for service panes, staged
fetch rows, and command-category views. Composite indexes
`target_commands_by_service_purpose` and `target_commands_by_side_purpose`
support direct lookups such as `file-service:explicitly fetch an
operator-staged file` or `target:start the configured reverse shell transport
from the target` without scanning every generated command. `target_command_summary` reports total,
network, explicit-target action, and operator-supplied-command execution
counts, with side and purpose counts mirrored into `summary` as
`target_command_side_counts` and `target_command_purpose_counts`. This lets
future frontends show the same commands without guessing whether a command is a
safe explicit fetch/upload helper or control-like behavior.
Command queue entries remain explicit operator records only; `command_queue`
includes `commands_by_status` and `status_counts`, mirrored into `summary` as
`command_queue_status_counts`. Recorded results are grouped as full records in
`commands_by_result_status`, `commands_by_result_exit_code`, and
`commands_by_result_output_exceeded` so operator UIs can inspect received
results without scanning all queued commands. Result status and exit-code
aggregates are exposed as `command_queue.result_status_counts`,
`command_queue.result_exit_code_counts`, and mirrored into `summary` as
`command_queue_result_status_counts` and
`command_queue_result_exit_code_counts`. It also exposes latest
command-created and result-received timestamps, mirrored into `summary`, so
dashboards can show queue recency without recomputing it. Compact safety booleans such as
`command_queue_enabled`, `command_queue_configured_for_polling`,
`command_queue_active_control_channel`, `command_queue_execution_supported`,
`command_queue_arbitrary_policy_requested`,
`command_queue_arbitrary_execution_allowed`, and
`command_queue_safe_disabled_default` are also mirrored for UI badges that must
not scan the full queue policy object. `command_queue.mode_semantics` and
`command_queue.mode_summary` expose the same target-side `status`, `poll`,
`once`, and `daemon` lifecycle labels and non-execution booleans used by the
target applet; compact counts are mirrored into `summary` as
`command_queue_mode_count`, `command_queue_polling_mode_count`,
`command_queue_operator_host_required_mode_count`,
`command_queue_execution_supported_mode_count`,
`command_queue_active_control_channel_mode_count`, and
`command_queue_operator_supplied_command_execution_mode_count`.
Event log entries include stable `id`, `session`, and `session_path` fields so
frontend and integration tooling can correlate global operator events with
per-session logs. File-service `connection_close` entries include the observed
request operation, status, HTTP status, and request/file identifier when known,
so timelines can show the final request outcome without scraping upload or fetch
metadata separately. The `events` array is a bounded recent tail;
`events_by_id` maps stable event ids to tail records, while
`events_by_session`, `events_by_service`, `events_by_event`, `events_by_level`, and
`events_by_remote` group those tail records for direct frontend lookups.
Composite maps `events_by_service_event` and `events_by_session_event` support
direct timeline lookups such as `file-service:upload_complete` or
`<session-id>:connection_close` without filtering broader event groups.
`event_log_state` reports the event log path, existence, validity, size, total
valid event count, invalid JSONL line count, tail count, tail limit, and
first/latest event timestamps. `event_log_stats` reports the event log path,
total valid event count, tail count, invalid JSONL line count, tail limit,
first/latest event timestamps, and
aggregate counters by service, event, level, and remote endpoint so API
consumers can tell whether there is more history to page or inspect from disk
while still rendering compact diagnostics.
Those aggregate maps are also mirrored into `summary` as
`event_service_counts`, `event_type_counts`, `event_level_counts`, and
`event_remote_counts`; `first_event_at` and `latest_event_at` are mirrored for
dashboard clients that only need compact status counters and event recency.

Structured `warnings` use stable `type` values such as `service_error`,
`stale_state`, `unexpected_listener`, `unmanaged_recorded_pid`,
`invalid_event_log`, and `invalid_command_queue_policy`. `warning_stats`
summarizes warnings by type, service, port, recorded PID, listener PID, and
possible owner PID. `warnings_by_type`, `warnings_by_service`,
`warnings_by_port`, `warnings_by_pid`, `warnings_by_listener_pid`, and
`warnings_by_owner_pid` provide full warning records grouped for direct
frontend lookups. The same compact warning counters are mirrored into `summary`
as `warning_count`, `warning_type_counts`, `warning_service_counts`,
`warning_port_counts`, `warning_pid_counts`, `warning_listener_pid_counts`, and
`warning_owner_pid_counts`; summary
fields also include `command_queue_policy_valid` and
`command_queue_policy_error_count` so clients can distinguish a disabled queue
from an invalid policy. Service-related
warnings include the configured and actual states, bind address, port, PID,
PID ownership evidence, listener PIDs, possible bind owners, error text, and
process/session log paths when those fields are available. This lets a TUI, future web UI, or
automation client show actionable cleanup guidance without scraping the
human-readable `--status` output.

`--stage-release-artifact` stages the selected artifact for explicit
target-side `busierbox fetch`; it does not push the artifact or run it. In the
curses workbench, the Event Log pane can be selected like the other browser
panes; the details pane shows the event id, session correlation fields, remote,
and compact outcome details from the structured event record. `v` opens the
selected local metadata/log/artifact/event-log path in the operator's pager when
one is available, and `c` copies the selected generated target command to the
local clipboard when possible plus
`local/operator-session/last-command.txt`. The line-oriented fallback exposes
the same operator path health, compact service summary, event aggregate counts,
and compact event outcome details so non-curses or non-TTY runs still show
whether listener state, logs, staged files, session roots, and recent event
outcomes are usable.

Inspect and clean BusierBox-controlled runtime state:

```sh
./busierbox cleanup-ledger --json
./busierbox clean --dry-run
./busierbox clean --dry-run --json
```
