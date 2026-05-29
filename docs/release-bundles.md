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
- `LICENSE`, `LICENSE.busierbox`, and `NOTICE`: BusierBox GPL license text,
  explicit project grant, and short project license notice.
- `LICENSES/`: repository-maintained third-party notice summaries for named
  integrated components such as BusyBox, Buildroot, doom-ascii, and miniz.
- `manifests/license-policy.json`: machine-readable BusierBox license and
  third-party GPL compatibility policy for repository scanners and release
  consumers, including per-component GPLv2 compatibility flags and distribution
  obligations.
- `sources.lock.json` and `manifests/sources.lock.json`: pinned downloadable
  source metadata for GPL/source-availability review and offline rebuilds.
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
tools, runtime mode, reverse-access defaults, command-queue policy and mode
indexes including `mode_records_by_operator_supplied_command_execution`,
trailer-overridable fields, size, checksum, config path, and the statically
extracted embedded payload manifest path. The JSON manifest contains the same
data in machine-readable form.
Missing or requested-but-unavailable tools are builder-facing negative
inventory and are omitted by default; pass `--include-missing-reports` to emit
`build-report.json` plus per-artifact `*.build-missing.json` files and include
those fields in tuple manifests.

When a matrix includes `version` or `include`, those values are preserved in
`release.json` for reproducibility. Release bundles always copy
`manifests/sources.lock.json` into the bundle as both `sources.lock.json` and
`manifests/sources.lock.json`; older `include.source_lock`,
`include.sources_manifest`, and `--include-sources-manifest` selectors remain
accepted for compatibility.

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
scripts/release-self-test --json
```

`scripts/release-self-test --json` emits machine-readable diagnostics after the
same validation passes. The JSON includes release and index artifact counts,
tuple/device counts, helper checks, checksum verification, manifest sidecar
counts, artifact-config round-trip counts, compatibility and payload-preset
counts, and command-queue safety counters such as
`command_queue_execution_supported_count` and
`command_queue_operator_supplied_command_execution_count`. It also includes
normalized `diagnostic_records` with lookup maps by name, category, and status
plus `api_collections.diagnostic_records`, so release dashboards can render
individual checks without scraping flat summary keys or the human
`release-self-test ok` line.

Use `scripts/release-find` to choose an artifact without reading every
manifest:

```sh
scripts/release-find --device glinet-mt1300
scripts/release-find --arch mipsel --libc musl --kernel 4.x
scripts/release-find --tool tcpdump
scripts/release-find --payload-preset survey-core
scripts/release-find --doom-wad doom.wad
scripts/release-find --survey-json survey.json
scripts/release-find --survey-json survey.json --reality-json reality.json --json
```

`release-find` reports a compatibility label and reasons for the selected
artifact. Labels are `exact`, `likely`, `heuristic`, `unsafe`, and
`incompatible`. Tuple/device arguments produce exact tuple matching; survey and
reality-test JSON add target-specific scoring for arch, endian, libc, kernel
floor, CPU/ABI hints, `/tmp` noexec, read-only rootfs, low storage, failed
runtime execution, failed payload extraction, partial procfs evidence, failed
ptrace checks, unreadable `dmesg` evidence, unavailable `/bin/sh` spawning,
and unavailable PTYs.
JSON output includes a `selection` block with selected artifact, candidate and
eligible counts, threshold-filter count, active filters, max compatibility, and
the selection policy. Plain text output mirrors the counts and policy so an
operator can audit why a release artifact was selected without parsing JSON.
For Doom-enabled payloads, `--doom-wad` and `--doom-wad-sha256` filter by staged
WAD basename or payload-manifest hash without exposing the builder's local
source path.
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
scripts/find-artifact --index local/release-repo-index.json --survey-json local/bringup-runs/latest/survey.json --payload-preset survey-core
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
`artifacts_by_payload_preset`, `artifacts_by_feature`, and
`artifacts_by_compatibility` for TUI/web clients that need to render details
without rescanning every artifact. `compatibility_counts` gives compact badge
counts for exact/likely/heuristic/unsafe/incompatible buckets. Composite maps
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
target compatibility tuple. Command-queue safety maps
`artifacts_by_command_queue_enabled`,
`artifacts_by_command_queue_execution_supported`, and
`artifacts_by_command_queue_operator_supplied_command_execution` let offline
browsers render explicit safety buckets without opening every artifact
manifest. The repository index publishes the same discovery shape used by
server status and bringup JSON: an `api` catalog, `api_resources`,
`api_resources_by_name`, `api_resources_by_records_key`,
`api_resources_by_summary_key`, and `api_resources_by_primary_key`, plus
`api_collections` descriptors for artifacts, release self-tests, release
licenses, dedupe records, devices, tuples, and recommendations. This lets an
offline artifact browser discover record keys, primary keys, summary counters,
and lookup maps without hard-coding the index schema. If a release directory contains
`release-self-test.json` or a supported self-test diagnostics path, the index
records it in `release_self_tests`, groups it by release name and status, and
copies the compact status/path onto each artifact from that release so
`scripts/find-artifact` can report whether the selected bundle passed its own
self-test, including command-queue token-required, token-configured,
execution-supported, and operator-supplied-command execution counts. The index
also publishes normalized
`device_records` and `tuple_records` with release, alias, and tuple-path lookup
maps, plus `api_collections` metadata for artifacts, release self-test records,
release license records, dedupe records, devices, tuples, and precomputed
recommendations. Each collection descriptor includes `count`, `summary_key`,
`count_summary_key`, `primary_key`, and index names. Future TUI/web clients can
use those fields to discover record counts and lookup maps without hard-coding
the JSON shape. It does not download or rebuild anything.
Release license records are normalized from `manifests/license-policy.json` in
each bundle and attached to artifact rows as `release_license`,
`project_license`, and `combined_gplv2_compatible`. The repository index exposes
`release_license_records_by_release`,
`release_license_records_by_project_license`,
`release_license_records_by_combined_gplv2_compatible`,
`release_license_records_by_component`,
`release_license_records_by_component_license`, and
`release_license_records_by_notice_file` so offline browsers can audit GPL
compatibility and notice coverage without opening every release directory.
`scripts/find-artifact` can also filter by that metadata with
`--project-license`, `--gplv2-compatible yes|no`, `--license-component`, and
`--component-license COMPONENT:LICENSE`, and recommendation JSON exposes
matching `matches_by_project_license`, `matches_by_combined_gplv2_compatible`,
`matches_by_license_component`, and `matches_by_component_license` maps.
When `scripts/busierbox-server` is launched from a release bundle, `--status`,
`--json-status`, and the workbench release browser expose the same compact
release license record as `release.release_license`, `release_licenses`, and
`api_collections.release_licenses`, plus summary counters for project license,
GPLv2 compatibility, notice count, and missing notices.
`--recommendation-json` returns the selected artifact plus active filters,
filter provenance records, match count, visible match count, match lookup maps,
an `api` catalog, `api_resources`, `api_resources_by_name`,
`api_resources_by_records_key`, `api_resources_by_summary_key`,
`api_resources_by_primary_key`, `api_collections` metadata with the same
count/primary-key fields, index counts, and the selection policy.
`filter_records`, `filters_by_name`,
`filters_by_source`, and `filters_by_name_source` distinguish explicit
operator filters from filters derived from survey evidence. Lookup maps include
`matches_by_release`, `matches_by_tuple_path`, `matches_by_payload_preset`,
`matches_by_compatibility`, `matches_by_tool`, `matches_by_feature`,
`matches_by_effective_compatibility`, `matches_by_provider_tool`, `matches_by_provider_status`,
`matches_by_doom_wad_filename`, `matches_by_doom_wad_sha256`,
`matches_by_command_queue_enabled`,
`matches_by_command_queue_execution_supported`, and
`matches_by_command_queue_operator_supplied_command_execution` for artifact
browser views. The policy used to prefer lower-risk compatibility labels also prefers newer release metadata. Use
`--max-compatibility exact|likely|heuristic|unsafe|incompatible`
to reject artifacts above an operator-selected risk threshold instead of only
sorting them lower. `--survey-json` derives unset architecture, libc,
kernel-floor, CPU, and ABI filters from `busierbox survey --json` output while
leaving explicit CLI filters authoritative. `--reality-json` includes
normalized reality-test checks, failed checks, and detected constraints in
`--recommendation-json` output, and adds an `effective_compatibility` overlay
that can downgrade the indexed baseline for bad runtime/extraction/storage
evidence before threshold filtering and sorting. The original repository
`compatibility` label remains unchanged for provenance. Plain text output also prints `compatibility_reason=` lines so an
operator can see why the selected artifact was considered exact, likely,
heuristic, unsafe, or incompatible without parsing JSON.

The repository index also includes a `recommendations` object for offline
clients that want one best current artifact without shelling out to
`scripts/find-artifact`. It records the same selection policy and precomputes
recommendations by device alias, tuple path, tool, payload preset, feature, and
common tuple/tool/feature plus preset combinations. The same selections are
also flattened into `recommendation_records` with stable ids such as
`by_device:glinet-mt1300` or `by_tool_payload_preset:tcpdump:survey-core`, plus
lookup maps by id, category, key, category/key, tuple path, payload preset,
compatibility label, and release. `api_collections.recommendations` lists both
the nested recommendation maps and the normalized record indexes so future
offline browsers can render recommendation tables without special-case
traversal logic.

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
reconnect behavior, including policy errors, without parsing prose. It also includes `runtime_decisions`
for representative post-disconnect reconnect attempts, using the same bounded
retry logic as the runtime loop. The human `rshell status` output also prints
the same key booleans, including `stop_after_first_success`,
`reconnect_after_disconnect`, `persistent_lifecycle`,
`fresh_session_on_reconnect`, `session_resume_supported`, and
`would_reconnect_after_success_attempt_N`. Runtime
`rshell.status` files also persist those evaluated fields, retry scope, and
pre/post-disconnect retry counts so postmortem evidence can be read without
reconstructing policy semantics from compiled defaults. SSH reverse-forward
mode runs `dbclient` through a guard-path supervisor so disconnect handling uses
the same `single`, `reconnect`, and `persistent` policy semantics as the direct
shell transports. Release tuple summaries and tuple `MANIFEST.json` records
include the reverse-access `session_policy_valid`, `session_policy_errors`, and
`session_policy_summary` fields, so release browsers can expose reconnect
behavior without opening each target artifact manifest.

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
scripts/busierbox-server --api-status --event-limit 50
scripts/busierbox-server --stage-release-artifact by_device:lab-router --list-staged
scripts/busierbox-server --stage-release-artifact by-tuple/native/host/host/host/bin/busierbox-native-default-full --list-staged
```

`--json-status` and `--api-status` include top-level `summary` and `warnings`
objects for frontend and automation consumers. Stale server-state records,
service errors, listener counts, command queue counts, command queue policy
validity, and release artifact/device/tuple counts can be read without
re-parsing the human status view. The same document includes an `api` catalog,
`api_resources`, and `api_collections` for frontend clients. `api_resources`
maps each reusable collection to its record location, collection metadata key,
primary key field, `summary_key`, `count_summary_key`, and available lookup maps
such as `services_by_name` or `browser_paths_by_kind_source_id`; lookup maps
such as `api_resources_by_name`, `api_resources_by_records_key`, and
`api_resources_by_summary_key` let a client discover those records without
hard-coding every top-level key. Warning-aware collections also publish
`has_warning_indexes` and `warning_indexes`, and
`api_resources_by_has_warning_indexes` groups resources that can be health
badged directly. Use `--event-limit N` to tune the structured event tail
included in the status document; `0` keeps aggregate event counts and indexes
but omits event records.
Service rows remain available in `services`,
and the same records are indexed by service name, actual state, configured
state, and port in `services_by_name`, `services_by_actual`,
`services_by_configured`, `services_by_bind_address`, `services_by_port`,
`services_by_pid`, and `services_by_listener_pid`. Additional lifecycle indexes
`services_by_tls`, `services_by_stale`, `services_by_pid_alive`,
`services_by_pid_managed`, `services_by_listener_bind_mismatch`, and
`services_by_has_error` let frontend clients filter operator rows without
reconstructing their own maps. `services_by_stopped_reason` and
`summary.service_stopped_reason_counts` let clients summarize clean exits,
signals, and operator stop actions without rescanning every service row.
Human `--status` mirrors the same stopped-reason counts in its service
lifecycle summary.
Listener ports are exposed as `ports`,
`ports_by_number`, `ports_by_service`, and `ports_by_actual`. Service and port
records carry `warning_count` and `warning_types` fields, and are grouped in
`services_by_has_warnings`, `services_by_warning_type`,
`ports_by_has_warnings`, and `ports_by_warning_type`, so service panes can
badge bind errors, stale state, and PID ownership warnings without scanning or
joining the full warning maps first. Human `--status` service rows print the
same compact warning badge as `warnings=N:type,type` when a service has
warnings. `summary` also
includes `service_actual_counts`, `service_configured_counts`, `port_count`,
`port_actual_counts`, `service_warning_count`, `service_warning_type_counts`,
`port_warning_count`, and `port_warning_type_counts` for compact service and
port dashboards.
The same document includes `generated_at` and a `paths` object for stable
discovery of server state, staged files, event logs, command queue records, and
the session root. `server_state` exposes the managed `server-state.json` path,
validity, service records, session records, and compact record counts for
frontends that need the persisted manager view. `path_status` mirrors those
paths with existence, parent-existence, expected-kind, expected-kind match,
readability, and writability fields; compact path health counts are mirrored
into `summary` as `path_status_count`, `path_missing_count`,
`path_parent_missing_count`, `path_not_writable_count`, and
`path_kind_mismatch_count`. `path_status_records` is the normalized list form
of the same path health data, with lookup maps such as `path_status_by_name`,
`path_status_by_path`, `path_status_by_expected_kind`, `path_status_by_exists`,
`path_status_by_parent_exists`, `path_status_by_writable`, and
`path_status_by_expected_kind_mismatch`, plus warning-health maps
`path_status_by_has_warnings` and `path_status_by_warning_type`.
`api_collections.path_status_records` lists those indexes for clients that
render every operator path as a table. `operator_state_records` provides a
content-health table for the main operator state surfaces: server state,
staged-files ledger, command queue ledger, last copied command, workbench jobs,
event log, and session root. Those records carry `status=ok|missing|invalid|error`,
`exists`, `valid`, `record_count`, and `error`, with lookup maps such as
`operator_state_records_by_name`, `operator_state_records_by_kind`,
`operator_state_records_by_status`, `operator_state_records_by_exists`,
`operator_state_records_by_valid`, `operator_state_records_by_path`, and
`operator_state_records_by_kind_status`. Summary mirrors the state status,
kind, existence, validity, and kind/status counts, plus direct
`operator_state_ok_count`, `operator_state_missing_count`,
`operator_state_invalid_count`, `operator_state_error_count`, and
`operator_state_unhealthy_count` fields, so clients can show corrupt or missing
operator ledgers without re-reading JSON files. Human `--status`
prints the same normalized operator state records as an `Operator state:`
section, including status, kind, existence, validity, record count, path, and
any parse/read error. `browser_paths`
provides a normalized operator file
browser list for future TUI/web clients, covering operator ledgers, session
directories, upload/fetch metadata, staged sources, event logs, TLS files,
release bundle files, and release recommendation artifact targets. The same records are grouped in `browser_paths_by_kind`,
`browser_paths_by_path`, `browser_paths_by_source_id`, and
`browser_paths_by_kind_source_id`, with direct health lookups in
`browser_paths_by_exists`, `browser_paths_by_readable`,
`browser_paths_by_writable`, and `browser_paths_by_expected_kind_mismatch`.
The composite kind/source map lets TUI and
future web clients jump directly to records such as
`upload-metadata:<session-id>`, `release-artifact:<release-path>`, or
`release-recommendation-artifact:<scope:key>` without
filtering the broader source-id group. Compact counts are exposed in
`browser_path_summary` and mirrored into `summary` as `browser_path_count`,
existence/readability/writability counts, `browser_path_kind_counts`, and
per-kind health counters such as `browser_path_exists_kind_counts` and
`browser_path_missing_kind_counts`. The browser summary also exposes
`browser_path_kind_mismatch_count` and `browser_path_kind_mismatch_counts` so
frontends can flag a path that exists as a file where a directory was expected,
or the reverse, without reimplementing path-kind inference. Operator path kind
mismatches also emit an `operator_path_kind_mismatch` warning in `warnings` and
the human `--status` output. `path_status` and `browser_paths` records carry
`warning_count` and `warning_types` fields after status warnings are indexed, so
they are also grouped in `browser_paths_by_has_warnings` and
`browser_paths_by_warning_type`. Summary fields `path_warning_count`,
`path_warning_type_counts`, `browser_path_warning_count`, and
`browser_path_warning_type_counts` let path browsers render health badges
without rescanning the full warning list.
path and file-browser panes can show warning badges without joining separate
maps first. The same warning annotations are aggregated in
`browser_path_summary.warning_count`, `browser_path_summary.warning_by_kind`,
`browser_path_summary.warning_by_type`, and mirrored into `summary` as
`browser_path_warning_count`, `browser_path_warning_kind_counts`, and
`browser_path_warning_type_counts`.
`staged_files_state` exposes the staged-files ledger
path, validity, request names, and raw staged-entry count. `command_queue_state`
exposes the command queue ledger path, validity, command ids, status counts,
and raw command count. Staged files are exposed as the existing `staged`
request map, an ordered `staged_records`
browser list, and lookup maps
`staged_by_request`, `staged_by_kind`, `staged_by_sha256`, and
`staged_by_source_path`, command lookup maps `staged_by_fetch_command` and
`staged_by_fetch_command_force`, plus `staged_by_source_exists` and
`staged_by_kind_source_exists` for clients that need to separate ready staged
files from stale ledger entries without rechecking operator filesystem state;
release artifacts staged through the workbench keep
their `release_path`, `tuple_path`, `payload_preset`, and `compatibility`
metadata so file-browser panes can distinguish release artifacts from arbitrary
local files.
`summary` includes `staged_total_size`, `staged_source_exists_count`, and
`staged_source_missing_count` for staged-file health, generated fetch-command
counts for copy/show command panes, `staged_kind_counts` for
file/release-artifact grouping, `staged_source_exists_kind_counts` and
`staged_source_missing_kind_counts` for per-kind health badges, plus
`latest_staged_at` for compact recency displays. Recent
upload and staged-fetch activity is exposed through top-level `uploads` and
`fetches` arrays plus lookup maps: `uploads_by_session`,
`uploads_by_filename`, `uploads_by_kind`, `uploads_by_sha256`,
`uploads_by_source_path`, `uploads_by_stored_path`,
`uploads_by_stored_exists`, `uploads_by_remote_addr`, `uploads_by_status`,
`uploads_by_kind_status`, `uploads_by_filename_status`,
`uploads_by_status_stored_exists`, `uploads_by_status_remote_addr`,
`uploads_by_metadata_exists`, `uploads_by_event_log_exists`,
`fetches_by_session`, `fetches_by_request`, `fetches_by_sha256`,
`fetches_by_source_path`, `fetches_by_source_exists`, `fetches_by_status`,
`fetches_by_http_status`, and `fetches_by_remote_addr`, plus
`fetches_by_request_status`, `fetches_by_status_source_exists`,
`fetches_by_status_remote_addr`, `fetches_by_http_status_remote_addr`,
`fetches_by_metadata_exists`, and `fetches_by_event_log_exists`;
session browser records are exposed as `sessions`, `sessions_by_id`,
`sessions_by_service`, `sessions_by_state`, and
`sessions_by_exit_reason`, `sessions_by_remote`, `sessions_by_service_state`,
`sessions_by_service_exit_reason`, `sessions_by_service_remote`,
`sessions_by_has_uploads`, `sessions_by_has_fetches`,
`sessions_by_has_events`, `sessions_by_has_artifacts`, and
`sessions_by_duration_known` for separating timed sessions from records that
do not have enough timestamps yet. `sessions_by_metadata_exists` and
`sessions_by_event_log_exists` let session/file browsers show only records
whose local metadata or per-session event logs can be opened without probing
the filesystem again.
`session_root_state`
summarizes the session directory, recent session ids, service/state counts,
session activity totals, and counts of sessions with uploads, fetches, events,
artifacts, metadata files, or event logs for file-browser views. Completed session metadata includes
`duration_sec`, and `session_root_state` plus `summary` expose total, average,
maximum, and known-duration counts for dashboards. Aggregate counts remain in
`summary`, including
`upload_total_size`, `fetch_total_size`, `upload_stored_exists_count`,
`upload_stored_missing_count`, `fetch_source_exists_count`,
`fetch_source_missing_count`, `upload_kind_counts`, `upload_status_counts`,
`fetch_status_counts`,
`fetch_http_status_counts`, `upload_remote_counts`, `fetch_remote_counts`,
`upload_metadata_exists_counts`, `upload_event_log_exists_counts`,
`fetch_metadata_exists_counts`, `fetch_event_log_exists_counts`,
`session_service_counts`, `session_state_counts`,
`session_exit_reason_counts`, `session_remote_counts`,
`upload_kind_status_counts`, `upload_filename_status_counts`,
`upload_status_stored_exists_counts`, `upload_status_remote_counts`,
`fetch_request_status_counts`, `fetch_status_source_exists_counts`,
`fetch_status_remote_counts`,
`fetch_http_status_remote_counts`, `session_service_state_counts`,
`session_service_exit_reason_counts`, `session_service_remote_counts`,
`session_duration_known_counts`, `session_duration_known_count`,
`session_metadata_exists_counts`, `session_event_log_exists_counts`,
`session_total_duration_sec`, `session_average_duration_sec`, and
`session_max_duration_sec` for
compact dashboards.
`latest_upload_at`, `latest_fetch_at`, and `latest_session_updated_at` expose
recent activity timestamps without requiring clients to scan the full browser
records. Human `--status` mirrors the same operator essentials through a compact
activity summary plus recent upload/fetch details, including source path,
remote address, timestamp, session correlation, and metadata/event-log paths
when available.
When running inside a release bundle, `release` includes artifact, device, and
tuple browser lists plus `artifacts_by_release_path`, `artifacts_by_name`,
`artifacts_by_sha256`, `artifacts_by_payload_preset`,
`artifacts_by_compatibility`, `artifacts_by_source`,
`artifacts_by_tuple_path`, `artifacts_by_tool`,
`artifacts_by_feature`, `artifacts_by_provider_tool`, `artifacts_by_provider_status`,
`artifacts_by_tool_payload_preset`, `artifacts_by_feature_payload_preset`,
`artifacts_by_tuple_payload_preset`,
`artifacts_by_doom_wad_filename`, `artifacts_by_doom_wad_sha256`,
`artifacts_by_command_queue_enabled`,
`artifacts_by_command_queue_execution_supported`,
`artifacts_by_command_queue_operator_supplied_command_execution`,
`devices_by_name`, and `tuples_by_path` lookup maps. It also includes
`recommendations`, flattened `recommendation_records`, and recommendation
lookup maps by id, scope, artifact, payload preset, and compatibility label so
TUI/API clients can present the best current artifact for a device, tuple path,
tool, payload preset, feature, or combined key without rerunning release search
logic. Release artifact
state is exposed separately as `release_state` with release directory,
`release.json` and `release-index.json` paths, presence, validity, parse
health, `bin`/`scripts` directory health, browser counts, release name, and
errors. Compact booleans are mirrored into `summary` as `release_present`,
`release_valid`, `release_json_valid`, and `release_index_valid` so API
clients can distinguish "not in a bundle" from "bundle-like directory with a
broken manifest". Invalid bundle-like directories also emit an
`invalid_release_state` warning with the release directory, manifest paths, and
release-state errors. Human `--status` and the line-oriented fallback print a
compact release summary with validity, artifact/device/tuple counts, total
artifact size, release directory, and release name before listing release
browser entries. They also print compact release recommendation rows such as
`by_device:lab-router -> bin/busierbox-target-full`, keeping the same safety
boundary: staging remains explicit through `--stage-release-artifact`, the
curses action, or the line-oriented fallback release staging action, and
nothing is pushed to or executed on the target automatically.
The curses workbench mirrors those rows in the release devices/tuples pane.
Pressing `Enter` or `s` on a release artifact, recommendation, device alias, or
tuple row stages the selected/recommended artifact for target-side
`busierbox fetch`; `v` inspects the selected local path. Staging still does not
push the artifact or run it on the target.
Release artifact aggregates are exposed as
`release.artifact_stats` and mirrored into `summary`
as `release_artifact_total_size`, `release_artifact_compatibility_counts`,
`release_artifact_payload_preset_counts`, `release_artifact_source_counts`,
`release_artifact_tool_counts`, `release_artifact_feature_counts`,
`release_artifact_provider_tool_counts`, and
`release_artifact_provider_status_counts`,
`release_artifact_command_queue_enabled_counts`,
`release_artifact_command_queue_execution_supported_counts`, and
`release_artifact_command_queue_operator_supplied_command_execution_counts`.
Composite lookup counts are
mirrored as `release_artifact_tool_payload_preset_combo_count`,
`release_artifact_feature_payload_preset_combo_count`, and
`release_artifact_tuple_payload_preset_combo_count`. Doom WAD references are grouped by
basename/hash in `release_artifact_doom_wad_filename_counts` and
`release_artifact_doom_wad_sha256_counts`, and counted as
`release_artifact_doom_wad_count`.
Device and tuple artifact reference totals are mirrored as
`release_device_artifact_reference_count` and
`release_tuple_artifact_reference_count`. Release devices are grouped in
`devices_by_name`, `devices_by_tuple_path`, and `devices_by_artifact`; release
tuples are grouped in `tuples_by_path` and `tuples_by_artifact`. The summary
mirrors those browser counts in `release_device_tuple_path_counts`,
`release_device_artifact_counts`, and `release_tuple_artifact_counts`.
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
operator-supplied-command execution metadata. Each record also carries a
1-based `ordinal`, `copy_selector`, `copy_command`, `copy_supported`, and
`command_sha256`, letting operator UIs copy or de-duplicate generated commands
without relying on array position alone. The generated `rshell` command record
also carries `metadata.session_policy`, validity, errors, and
`session_semantics`, plus `metadata.retry` and `metadata.retry_timing`, so
operator UIs can distinguish single-shot, reconnect, and persistent
fresh-session behavior and show the configured retry schedule next to the
command itself.
`target_commands_by_service`,
`target_commands_by_request`, `target_commands_by_side`, and
`target_commands_by_purpose` index those records for service panes, staged
fetch rows, and command-category views. Safety indexes
`target_commands_by_network`,
`target_commands_by_requires_explicit_target_action`, and
`target_commands_by_executes_operator_supplied_commands` let clients separate
network helpers, manual target actions, and command-like behavior without
rescanning the records. `target_commands_by_ordinal`,
`target_commands_by_command_sha256`, and `target_commands_by_copy_supported`
make command copy/export views stable and directly addressable. Composite indexes
`target_commands_by_service_purpose` and `target_commands_by_side_purpose`
support direct lookups such as `file-service:explicitly fetch an
operator-staged file` or `target:start the configured reverse shell transport
from the target` without scanning every generated command. Rshell-specific
indexes such as `target_commands_by_session_policy`,
`target_commands_by_retry_backoff`, `target_commands_by_retry_interval_sec`,
and `target_commands_by_retry_post_disconnect_count` let clients badge
single/reconnect/persistent behavior and retry timing directly.
`target_command_summary` reports total, network, explicit-target action,
operator-supplied-command execution, session-policy, session-policy validity,
session-policy error, and retry-backoff counts,
with matching fields mirrored into `summary`. This lets future frontends show
the same commands without guessing whether a command is a safe explicit
fetch/upload helper or control-like behavior. Human `--status` and the
line-oriented fallback print the same target-command safety summary, including
rshell policy validity and policy error counts, before listing generated
commands.
Command queue entries remain explicit operator records only; `command_queue`
includes `commands_by_status` and `status_counts`, mirrored into `summary` as
`command_queue_status_counts`. Queue records are also indexed by
`commands_by_command_sha256`, `commands_by_created_at`, `commands_by_delivered_at`,
`commands_by_result_received_at`, `commands_by_result_source_path`,
`commands_by_timeout_sec`, and `commands_by_max_output_bytes`, with mirrored
`command_queue_timeout_sec_counts` and
`command_queue_max_output_bytes_counts`, so operator UIs can audit queued
command limits and jump from result source files or timestamps without scanning
all records. Recorded results are grouped as full records in
`commands_by_result_status`, `commands_by_result_exit_code`, and
`commands_by_result_output_exceeded`, plus
`commands_by_result_output_size_bucket` (`zero`, `small`, `medium`, `large`)
so operator UIs can inspect received results without scanning all queued
commands. Result status, exit-code, and output-size
aggregates are exposed as `command_queue.result_status_counts`,
`command_queue.result_exit_code_counts`,
`command_queue.result_output_size_bucket_counts`, and mirrored into `summary` as
`command_queue_result_status_counts` and
`command_queue_result_exit_code_counts` plus
`command_queue_result_output_size_bucket_counts`. It also exposes latest
command-created and result-received timestamps, mirrored into `summary`, so
dashboards can show queue recency without recomputing it. Delivered command
counts are mirrored as `command_queue_delivered_count` alongside queued and
result counts. Compact safety booleans such as
`command_queue_enabled`, `command_queue_configured_for_polling`,
`command_queue_active_control_channel`, `command_queue_execution_supported`,
`command_queue_delivery_supported`, `command_queue_result_upload_supported`,
`command_queue_poll_transport_supported`, `command_queue_live_polling_supported`,
`command_queue_arbitrary_policy_requested`,
`command_queue_arbitrary_execution_allowed`, and
`command_queue_safe_disabled_default` are also mirrored for UI badges that must
not scan the full queue policy object. The configured
`command_queue_poll_interval_sec`, `command_queue_poll_jitter_pct`,
`command_queue_poll_backoff`, `command_queue_poll_max_interval_sec`, and
`command_queue_max_polls` are mirrored for interval-polling controls.
`command_queue.token_required` and `command_queue.token_configured` are also
preserved in tuple summaries so release browsers can show whether polling
requires a token without exposing the token value.
Target manifests, tuple summaries, release manifests, and
`plan command-queue --json` also expose
`daemon_state_file`, `daemon_state_file_supported`,
`daemon_status_supported`, and `daemon_stop_supported` so operator tooling can
show the target-side daemon lifecycle contract without starting a poll loop.
`command_queue.mode_semantics`, `command_queue.mode_records`, tuple-summary
`command_queue.mode_records`, and top-level `command_queue_mode_records` expose
the same target-side `status`, `poll`, `once`, `daemon`, and `stop` lifecycle
labels, polling support flags, and non-execution booleans used by the target
applet. The top-level API view also includes lookup maps such as
`command_queue_modes_by_mode`, `command_queue_modes_by_lifecycle`,
`command_queue_modes_by_would_poll_if_configured`,
`command_queue_modes_by_live_supported`, and
`command_queue_modes_by_execution_supported` for frontend mode badges; target
manifest and plan JSON also expose `mode_records_by_operator_supplied_command_execution`
so clients can verify the non-execution boundary directly. Compact
counts are mirrored into `summary` as
`command_queue_mode_count`, `command_queue_polling_mode_count`,
`command_queue_operator_host_required_mode_count`,
`command_queue_live_supported_mode_count`,
`command_queue_result_upload_supported_mode_count`,
`command_queue_execution_supported_mode_count`,
`command_queue_active_control_channel_mode_count`, and
`command_queue_operator_supplied_command_execution_mode_count`.
Target-side `command-queue --json` also summarizes the current live poll run's
structured target events in `poll_run.event_count`,
`poll_run.event_counts_by_event`, and `poll_run.event_counts_by_level`, plus the
last delivered command id and command SHA-256, letting frontends show poll
attempts, no-command responses, rejected execution decisions, result uploads,
errors, and shutdown without parsing the target event JSONL first.
Event log entries include stable `id`, `session`, and `session_path` fields so
frontend and integration tooling can correlate global operator events with
per-session logs. File-service `connection_close` entries include the observed
request operation, status, HTTP status, and request/file identifier when known,
so timelines can show the final request outcome without scraping upload or fetch
metadata separately. The `events` array is a bounded recent tail;
`events_by_id` maps stable event ids to tail records, while
`events_by_session`, `events_by_service`, `events_by_event`, `events_by_level`, and
`events_by_remote` group those tail records for direct frontend lookups.
Composite maps `events_by_service_event`, `events_by_session_event`,
`events_by_service_level`, `events_by_event_level`, `events_by_session_level`,
`events_by_remote_event`, `events_by_remote_level`, `events_by_detail_status`,
`events_by_detail_operation`, `events_by_detail_http_status`,
`events_by_detail_request_name`, `events_by_detail_filename`,
`events_by_detail_reason`, `events_by_detail_sha256`, `events_by_detail_command_id`,
`events_by_detail_command_sha256`, `events_by_detail_job_id`, `events_by_detail_action_id`,
`events_by_detail_key`, `events_by_detail_config_path`,
`events_by_event_detail_status`, `events_by_service_detail_status`,
`events_by_event_detail_operation`, `events_by_service_detail_operation`,
`events_by_event_detail_http_status`, `events_by_service_detail_http_status`,
`events_by_event_detail_request_name`, `events_by_service_detail_request_name`,
`events_by_event_detail_filename`, `events_by_service_detail_filename`,
`events_by_event_detail_reason`, `events_by_service_detail_reason`,
`events_by_event_detail_sha256`, `events_by_service_detail_sha256`,
`events_by_event_detail_command_id`, `events_by_service_detail_command_id`,
`events_by_event_detail_command_sha256`, and
`events_by_service_detail_command_sha256`, plus
`events_by_event_detail_job_id`, `events_by_service_detail_job_id`,
`events_by_event_detail_action_id`, and `events_by_service_detail_action_id`
plus `events_by_event_detail_key`, `events_by_service_detail_key`,
`events_by_event_detail_config_path`, and `events_by_service_detail_config_path`
support direct timeline and outcome
lookups such as `file-service:upload_complete`, `<session-id>:connection_close`,
`file-service:error`, `bind_error:error`, `<remote>:upload_complete`,
`upload`, `200`, `clean shutdown`, `cq-...`, `upload_complete:ok`,
`file-service:ok`, `upload_complete:upload`, `file-service:200`,
`fetch_complete:/tmp/myfile`, `file-service:evidence.txt`,
`upload_complete:<file-sha256>`, `file-service:<file-sha256>`,
`service_stop:clean shutdown`, `command_result_received:cq-...`,
`command_queue_poll_delivered:<command-sha256>`,
`command_queue_poll_no_command:info`,
`command_queue_result_upload_received:<command-sha256>`,
`command_queue_result_upload_rejected:rejected`,
`command_result_received:<command-sha256>`,
`workbench_job_completed:job-...`, or
`workbench:job-...`, `workbench_job_completed:bringup-recommend`, or
`workbench:package-artifact`, `workbench_config_updated:BB_NORESIDUE_LEVEL`, or
`workbench:/path/to/busierbox.conf` without filtering broader event groups or
parsing each event detail payload.
`event_log_state` reports the event log path, existence, validity, size, total
valid event count, invalid JSONL line count, tail count, tail limit, and
first/latest event timestamps. It also reports whether the recent tail is
truncated and how many older valid events are omitted from the bounded status
response. `event_log_stats` reports the event log path, total valid event count,
tail count, invalid JSONL line count, tail limit, truncation state, omitted
count, first/latest event timestamps, and
aggregate counters by service, event, level, remote endpoint, service/event,
session/event, service/level, event/level, session/level, remote/event,
remote/level, detail status, detail operation,
detail HTTP status, detail request name, detail filename, detail reason,
detail command id, event/status,
service/status, event/reason, service/reason, event/command id, and
service/command id, plus event/request name, service/request name,
event/filename, service/filename, file detail SHA-256, event/file SHA-256,
service/file SHA-256, detail job id, event/job id, and service/job id so API
consumers can tell whether there is more history to page or inspect from disk
while still rendering compact diagnostics. Workbench action ids get the same
detail/action id, event/action id, and service/action id counters. Workbench
configuration updates are also counted by detail key, detail config path,
event/key, service/key, event/config path, and service/config path.
Those aggregate maps are also mirrored into `summary` as
`event_service_counts`, `event_type_counts`, `event_level_counts`, and
`event_remote_counts`, plus `event_service_event_counts` and
`event_session_event_counts`, `event_service_level_counts`,
`event_type_level_counts`, `event_session_level_counts`,
`event_detail_status_counts`,
`event_detail_operation_counts`, `event_detail_http_status_counts`,
`event_detail_request_name_counts`, `event_detail_filename_counts`,
`event_detail_reason_counts`, `event_detail_sha256_counts`,
`event_detail_command_id_counts`,
`event_detail_job_id_counts`, `event_detail_action_id_counts`,
`event_detail_key_counts`, `event_detail_config_path_counts`,
`event_type_detail_status_counts`, `event_service_detail_status_counts`,
`event_type_detail_reason_counts`, `event_service_detail_reason_counts`,
`event_type_detail_request_name_counts`, `event_service_detail_request_name_counts`,
`event_type_detail_filename_counts`, `event_service_detail_filename_counts`,
`event_type_detail_sha256_counts`, `event_service_detail_sha256_counts`,
`event_type_detail_command_id_counts`, and
`event_service_detail_command_id_counts`, plus
`event_type_detail_job_id_counts`, `event_service_detail_job_id_counts`,
`event_type_detail_action_id_counts`, and
`event_service_detail_action_id_counts`, plus `event_type_detail_key_counts`,
`event_service_detail_key_counts`, `event_type_detail_config_path_counts`, and
`event_service_detail_config_path_counts`;
`first_event_at` and
`latest_event_at` are mirrored for dashboard clients that only need compact
status counters and event recency. The human `--status` event summary prints
both `detail_sha256` and `detail_command_sha256` count lines.

Structured `warnings` use stable `type` values such as `service_error`,
`stale_state`, `unexpected_listener`, `listener_bind_mismatch`, `unmanaged_recorded_pid`,
`operator_path_kind_mismatch`, `invalid_server_state`,
`invalid_staged_files_state`, `invalid_command_queue_state`,
`invalid_release_state`, `invalid_event_log`, and
`invalid_command_queue_policy`, and `invalid_rshell_session_policy`. Each
warning also carries `severity`, `remediation_class`, and
`requires_operator_action`, so clients can badge warning rows by urgency and
next-action class without parsing prose messages.
`warning_stats`
summarizes warnings by type, severity, remediation class, type/severity,
service, port, recorded PID, listener PID, and possible owner PID.
`warnings_by_type`, `warnings_by_severity`, `warnings_by_remediation_class`,
`warnings_by_type_severity`, `warnings_by_service`,
`warnings_by_port`, `warnings_by_pid`, `warnings_by_listener_pid`, and
`warnings_by_owner_pid` provide full warning records grouped for direct
frontend lookups. `warnings_by_service_port` and
`warnings_by_type_service_port` provide composite keys such as
`file-service:22204` and `service_error:file-service:22204` for direct service
grid lookups. Path-carrying warnings are also grouped in
`warnings_by_path` and `warnings_by_type_path`, with matching compact counters
in `warning_path_counts` and `warning_type_path_counts`, so browser panes can
jump from a state file, event log, release manifest, or operator path directly
to relevant warnings. The same compact warning counters are mirrored into `summary`
as `warning_count`, `warning_type_counts`, `warning_severity_counts`,
`warning_remediation_class_counts`, `warning_type_severity_counts`,
`warning_service_counts`, `warning_port_counts`, `warning_pid_counts`,
`warning_listener_pid_counts`, and
`warning_owner_pid_counts`, plus `warning_service_port_counts` and
`warning_type_service_port_counts`; summary
fields also include `command_queue_policy_valid` and
`command_queue_policy_error_count` so clients can distinguish a disabled queue
from an invalid policy. Human `--status` and the line-oriented fallback print a
compact warning summary by total, type, service, and port before the detailed
warning records. Service-related
warnings include the configured and actual states, bind address, port, PID,
PID ownership evidence, listener PIDs, possible bind owners, error text, and
process/session log paths when those fields are available. This lets a TUI, future web UI, or
automation client show actionable cleanup guidance without scraping the
human-readable `--status` output. Actual service state is bind-address aware:
a listener on the same port but a different address is reported as listener
evidence with `listener_bind_mismatch`, not as proof that the configured service
is listening. Status JSON also includes a `service_manager` runtime snapshot
with shutdown state and currently registered sockets, Paramiko transports,
service threads, and child processes for the current server process; `summary`
mirrors the manager counts so clients can show lifecycle cleanup state without
parsing implementation internals. The same resources are flattened into
`service_manager_resources` with lookup maps such as
`service_manager_resources_by_kind`, `service_manager_resources_by_state`,
`service_manager_resources_by_active`, `service_manager_resources_by_pid`,
`service_manager_resources_by_kind_state`, and
`service_manager_resources_by_kind_active` so API clients can filter sockets,
transports, threads, and child processes like other status collections. Human
`--status` prints the same manager counts as a compact `runtime_manager` line.

`--stage-release-artifact` stages the selected artifact for explicit
target-side `busierbox fetch`; it accepts an artifact basename, release path,
local path, or recommendation id such as `by_device:lab-router`, and does not
push the artifact or run it. In the curses workbench, the Event Log pane can be
selected like the other browser
panes; the details pane shows the event id, session correlation fields, remote,
and compact outcome details from the structured event record. `v` opens the
selected local metadata/log/artifact/event-log path in the operator's pager when
one is available, and `c` copies the selected generated target command to the
local clipboard when possible plus
`local/operator-session/last-command.txt`. Status JSON exposes that file as a
bounded `command_copy` record plus `command_copy_records_by_has_command` and
related lookup maps, so clients can show the last copied target command without
opening the file separately. The `r` refresh action updates
workbench refresh counters and records a structured `workbench_refreshed` event
instead of being only an incidental redraw. The curses workbench top bar also
badges normalized operator-state health as `operator_state_unhealthy=N`, and
the generic details view lists missing, invalid, or error state records when no
selected pane item has more specific details. Status JSON and both workbench views
also expose `workbench_actions` records for operator-side configuration and
build workflows such as `scripts/menuconfig`, `make package`,
`scripts/busierbox-bringup --recommend-only --json`,
`scripts/artifact-config set ARTIFACT KEY=VALUE`, and release self-tests. These
records are show-command descriptors by default, include confirmation,
background-job, and target-execution flags, and are indexed through
`workbench_actions_by_id`, `workbench_actions_by_category`,
`workbench_actions_by_script`, `workbench_actions_by_requires_confirmation`,
`workbench_actions_by_execution_default`, and
`workbench_actions_by_target_execution`, plus audit/config lookups
`workbench_actions_by_event` and `workbench_actions_by_config_path`, so
future TUI/web clients can render workflow screens and verify that default
workbench actions do not execute on the target without inventing a second
configuration format. Workbench state records
also keep `workbench_mode` (`curses`, `line`, or `noninteractive`) so status
consumers can distinguish the active operator surface after shutdown. The same
status output also exposes `workbench_config_fields` for guided edits of the existing
`configs/busierbox.conf` shell assignment file, grouped by target, payload,
build/static policy, runtime/trailer defaults, recovery, reverse shell policy,
command queue policy, command queue transport/token settings, command queue
interval polling settings, and no-residue behavior. Operators can inspect
those fields with `--list-build-config`; field records include examples and
structured fixed `options` where the underlying config accepts a bounded choice.
They are indexed by category, configured state, fixed-option state, write
behavior, target-execution behavior, source format, safety boundary, reverse
access relevance, command queue relevance, control-like behavior, and explicit
operator-choice requirements so operator UIs can render guided edits, badge
control-like settings, and verify those edits only update the shared shell
assignment config.
Operators can update supported keys with `--set-build-config KEY=VALUE`; fixed
choice values are validated before writing. The line-oriented workbench shows
the exact underlying command before writing the same config file that
`scripts/menuconfig` and noninteractive builds consume. Background-capable
workflow tasks are represented in `workbench_jobs` with start time, command, PID
ownership metadata, log path, effective state, managed exit-status sidecars,
finish time, outcome, log size, and a bounded last-output tail with explicit
line/byte limits and truncation status. Job indexes such as
`workbench_jobs_by_id`,
`workbench_jobs_by_action`, `workbench_jobs_by_effective_state`, and
`workbench_jobs_by_cancel_supported` let operator UIs show or cancel only jobs
that are clearly owned by the workbench/runtime manager. Job health and safety
maps such as `workbench_jobs_by_pid_managed`, `workbench_jobs_by_log_exists`,
`workbench_jobs_by_exit_status_known`, `workbench_jobs_by_started_at_known`,
`workbench_jobs_by_finished_at_known`, `workbench_jobs_by_duration_known`,
`workbench_jobs_by_elapsed_known`,
`workbench_jobs_by_background_supported`, and
`workbench_jobs_by_long_running` let clients filter stale, completed, logless,
timed, or background-capable work without scanning every record. Completed
managed jobs are also indexed by outcome, exit status, duration availability,
and whether the displayed output tail is truncated. `--start-workbench-job ACTION`
starts a background-capable operator workflow action, records the exact command
and log path, and marks the spawned process with workbench environment ownership
tokens. `--cancel-workbench-job JOB` only requests cancellation when
those process environment tokens still match the ledger entry; a forged or stale
ledger record is visible in status but is not cancellable. Human status prints
each job's managed/cancellable state and the ownership evidence or cancellation
skip reason beside the command and log path. The line-oriented
fallback exposes the same operator path health, normalized operator state
records, compact service and activity summaries, recent upload/fetch activity,
event aggregate counts, refresh state, and compact event outcome details so
non-curses or non-TTY runs still show whether listener state, logs, staged
files, session roots, transfer activity, and recent event outcomes are usable.
To keep interactive pty sessions responsive, the line menu prints that full
dashboard on entry and explicit refresh, then uses a compact workbench summary
between actions. It can also list the same operator
workflow actions and their exact underlying commands, start background-capable
jobs, and request cancellation for owned jobs. Its release staging action accepts
a displayed release row number, recommendation id, artifact path,
`by_device:NAME`, or `by_tuple_path:PATH` and stages the same explicit
target-side fetch record as the curses browser.

Inspect and clean BusierBox-controlled runtime state:

```sh
./busierbox cleanup-ledger --json
./busierbox clean --dry-run
./busierbox clean --dry-run --json
```
