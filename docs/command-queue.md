# Command Queue

The command queue is an explicit advanced mode where a target can poll an
operator service for queued work. It is separate from file upload, fetch,
evidence push, and reverse shells.

Current behavior is disabled and metadata-only by default, with explicit
target-side execution available only when both the target and operator policies
opt in:

- `BB_COMMAND_QUEUE_ENABLE` defaults to `no`.
- `BB_COMMAND_QUEUE_EXECUTION` defaults to `metadata-only`. Queued command
  metadata may be delivered only during explicit live polling, and the target
  still rejects the execution decision instead of running the command.
- `BB_COMMAND_QUEUE_EXECUTION=execute` permits target-side execution only with
  a valid non-`none` command policy. `busierbox-only` accepts commands whose
  first word is `busierbox` or `./busierbox`; `custom` additionally requires
  `BB_COMMAND_QUEUE_ALLOW_ARBITRARY=yes`. These settings are the only supported
  way to execute queued commands.
- `busierbox command-queue status --json` reports the compiled/effective policy
  and a compact `policy_summary` for frontend/operator tooling.
- Invalid effective policy is reported as `policy_valid=false` with explicit
  `policy_errors`; invalid policy suppresses `would_poll`.
- `busierbox command-queue poll --json`, `once`, and `daemon` report a dry-run
  target polling plan by default. With explicit `--live`, they contact the
  configured operator command-queue endpoint and can append structured poll
  events. Live polling currently requires `BB_COMMAND_QUEUE_TLS=no`; TLS
  command-queue polling is reported as unsupported instead of silently falling
  back to plaintext. Live polls can receive queued command metadata, and
  target-side JSON reports the delivered command id, command text, timeout, and
  maximum-output metadata. Metadata-only policy records an explicit rejected
  execution decision. Execute policy runs the command through `/bin/sh -c`,
  captures merged stdout/stderr output up to the configured maximum and preview
  cap, records exit status or timeout, and uploads the result metadata so the
  operator ledger has a complete decision record.
- Operator status mirrors the same transport boundary:
  `poll_transport_supported=false`, `live_polling_supported=false`, and
  `poll_transport_unsupported_reason` explain the TLS constraint when the
  effective queue config keeps `BB_COMMAND_QUEUE_TLS=yes`.
- When `BB_COMMAND_QUEUE_REQUIRE_TOKEN=yes`, enabled queues require
  `BB_COMMAND_QUEUE_TOKEN` on the target and `command_queue_token` on the
  operator server config. Poll and result requests send/check
  `X-BusierBox-Command-Queue-Token`.
- `scripts/busierbox-server --queue-command ...` records explicit operator
  queue entries in `local/operator-session/command-queue.json` for inspection
  and tooling. The command-queue listener can mark a queued entry delivered to
  a polling target; the target decides whether to execute based on its effective
  command-queue policy.
- `scripts/busierbox-server --json-status` or `--api-status` includes the
  command queue path, counts, entries, `commands_by_id`,
  `commands_by_status`, result lookup maps, queue-time and delivery-time
  policy snapshot lookup maps, latest queue/result timestamps,
  token-required/token-configured booleans, `policy_summary`,
  `mode_semantics`, `mode_summary`, and explicit execution safety boundary.
- Human `--status`, `--list-command-queue`, and the line-oriented workbench
  mirror the structured `policy_summary` token posture, mode lifecycle,
  transport support, and execution flags so operators do not need JSON
  tooling to distinguish default dry-run planning from explicit `--live` metadata polling.
  In line-mode TUI, action `20` prints the equivalent `--list-command-queue`
  output plus target mailbox result records for completed and pending
  target-scoped work.
- `busierbox plan command-queue --json` and `manifest --json` expose the same
  policy validity fields and normalized mode records so release tooling and
  frontends do not treat an inconsistent policy as ready to poll.

Configuration keys:

```sh
BB_COMMAND_QUEUE_ENABLE="no"
BB_COMMAND_QUEUE_PORT="22205"
BB_COMMAND_QUEUE_TLS="yes"
BB_COMMAND_QUEUE_REQUIRE_TOKEN="yes"
BB_COMMAND_QUEUE_TOKEN_SOURCE="manual"
BB_COMMAND_QUEUE_TOKEN=""
BB_COMMAND_QUEUE_ALLOWED_COMMANDS="none"
BB_COMMAND_QUEUE_EXECUTION="metadata-only"
BB_COMMAND_QUEUE_ALLOW_ARBITRARY="no"
BB_COMMAND_QUEUE_POLL_INTERVAL_SEC="5"
BB_COMMAND_QUEUE_POLL_JITTER_PCT="0"
BB_COMMAND_QUEUE_POLL_BACKOFF="none"
BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC="300"
BB_COMMAND_QUEUE_MAX_POLLS="0"
```

Live polling has additional target-side controls. These can be supplied as
environment variables or CLI flags:

```sh
BB_COMMAND_QUEUE_POLL_INTERVAL_SEC=5
BB_COMMAND_QUEUE_POLL_JITTER_PCT=0
BB_COMMAND_QUEUE_POLL_BACKOFF=none
BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC=300
BB_COMMAND_QUEUE_MAX_POLLS=0

busierbox command-queue daemon --live \
  --operator-host 192.0.2.10 \
  --poll-interval-sec 5 \
  --poll-backoff linear \
  --poll-jitter-pct 10 \
  --poll-max-interval-sec 60 \
  --max-polls 3 \
  --state-file ./command-queue-daemon.state \
  --event-log ./command-queue-events.jsonl
```

`--max-polls 0` means no fixed limit for `daemon`; `poll` and `once` always run
a single live poll attempt. `BB_COMMAND_QUEUE_POLL_BACKOFF` may be `none`,
`linear`, or `exponential`; jitter is applied only to daemon sleeps between
poll attempts, and `BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC` caps the computed
delay. Each live attempt sends a plain HTTP
`GET /command-queue/poll` request when `BB_COMMAND_QUEUE_TLS=no`, records
`command_queue_poll_attempt`, then `command_queue_poll_no_command`,
`command_queue_poll_complete`, or `command_queue_poll_error`. Delivered command
metadata also records `command_queue_execution_decision` with status
`executed` or `rejected`, and the daemon records
`command_queue_poll_shutdown` when the loop exits. Target-side JSONL events use
the same structured event-bus envelope as
operator events: `schema`, `id`, `ts`, `service`, `session`, `event`, `level`,
`remote`, and `details`. In target-side event `details`,
`delivery_supported` and `result_upload_supported` describe whether the live
HTTP polling/result path is available for that event; `status=no-command` means
the queue was empty, not that delivery is unsupported. Delivered-command,
execution-decision, and result-upload events also include `command_id`,
`command_sha256`, `command`, `timeout_sec`, and `max_output_bytes` when the
operator supplied that metadata. JSON output also mirrors the current invocation's structured
target events under `poll_run` with
`event_count`, level counts, and `event_counts_by_event`, so API clients can
show poll attempts, empty polls, delivery decisions, result uploads, errors,
and shutdown outcomes without separately parsing the target-side event log.

The live daemon writes a target-side state file, defaulting to
`$BB_RUNTIME_ROOT/run/command-queue-daemon.state`. `command-queue status`
reports that file, the recorded PID, whether the process is currently alive,
whether the state is stale, and whether `/proc/<pid>/cmdline` verifies it as a
command-queue process. `command-queue stop` reads the same state file and sends
SIGTERM only when the state is valid and the recorded PID is verified as a
BusierBox command-queue process. Use `--state-file PATH` to put this state in a
specific runtime-owned location. `manifest --json` and
`plan command-queue --json` expose the default state path and booleans for
daemon state-file, status, and stop support so release and frontend tooling can
surface this lifecycle without probing target status first.

Policy values for `BB_COMMAND_QUEUE_ALLOWED_COMMANDS` are `none`,
`busierbox-only`, `allowlist`, and `custom`. `BB_COMMAND_QUEUE_ALLOW_ARBITRARY`
is only valid with `custom`; disabled queues must keep `allowed_commands=none`
`execution=metadata-only`, and `allow_arbitrary=no`. `BB_COMMAND_QUEUE_EXECUTION`
may be `metadata-only` or `execute`; `execute` reports
`execution_supported=true` only for valid `busierbox-only` or explicit
`custom`/`allow_arbitrary=yes` policy.

Safety boundary:

- The command queue is disabled by default.
- Metadata-only execution mode is the default.
- It is not required for normal file transfer or reverse shell workflows.
- It is visible in `config-info`, `runtime-config --json`, `manifest --json`,
  and `plan command-queue`.
- `config-info` and `runtime-config --json` expose token posture and policy
  validity alongside the raw effective settings so operators do not need to
  infer safety state.
- Trailer overrides alone are not an execution capability; execution requires
  explicit live polling plus valid execute policy on the target.
- Target-side `poll`, `once`, and `daemon` expose `would_poll`,
  live-mode `poll_transport_supported`, `delivery_supported`,
  `result_upload_supported`, `execution_supported`, and a
  `policy_summary` so frontend and integration tooling can distinguish
  policy/planning from explicit live polling. Live `delivery_supported=true`
  means the target can receive queued metadata; command execution is separate
  and reflected by `execution_supported=true` plus an executed decision in the
  poll result. Live `result_upload_supported=true` means the target can upload
  structured rejection/result metadata to the operator endpoint. Disabled or
  invalid policy keeps `would_contact_operator=false`
  and `active_control_channel=false` even when a user passes `--live`. They
  also expose a compact `poll_plan` object with mode, status, endpoint,
  explicit-target-action, dry-run-only, would-contact-operator, queued-command
  availability, delivery support, result-upload support, execution support, and
  active-control-channel posture.

Operator `scripts/busierbox-server --json-status` mirrors the mode records for
future TUI/web clients. The `command_queue_modes` API collection includes
indexes by lifecycle, polling posture, live support, delivery support,
result-upload support, execution support, active-control-channel posture, and
operator-supplied-command execution posture.
- `command-queue --json` also includes `mode_semantics` for `status`, `poll`,
  `once`, `daemon`, and `stop`. Each entry declares whether the mode is selected,
  whether it needs an operator host, its lifecycle label (`inspect`,
  `single-poll`, `single-cycle`, `long-running`, or `stop`), and the same
  execution safety booleans so UIs do not infer mode behavior from strings.
- The same mode data is exposed as flat `mode_records`, with lookup maps by
  mode, lifecycle, polling behavior, live-support status, delivery support,
  result-upload support, execution support, active-control-channel state, and
  operator-supplied command execution state.
  `api_collections.mode_records` publishes
  count, summary-key, count-summary-key, primary-key, and index metadata for
  frontend discovery.
- `plan command-queue --json` exposes the planned polling mode with the same
  flat record/index/API pattern, plus `mode_records_by_planned`, so dashboards
  can show that a valid enabled policy would start explicit `command-queue
  poll` without implying command execution.
- Plan mode records also expose target-polling support, delivery support,
  result-upload support, execution support, active-control-channel posture, and
  operator-supplied-command execution posture. Delivery remains false in plan
  output because delivery only happens during explicit target-side `--live`
  polling; result-upload support is advertised so frontends can prepare the
  rejection/result metadata workflow.
- `mode_summary` mirrors those mode records into compact counts for polling
  modes, operator-host-required modes, transport-supported live modes,
  delivery-capable live modes, active control-channel modes, result-upload
  modes, and execution-capable modes.
- `command-queue --json` includes `daemon_state` and `stop_result` objects so
  operator tooling can show whether a live polling loop is visible, stale,
  stopped, or skipped because ownership could not be verified.
- Delivered live poll metadata is exposed as `queued_command` and mirrored in
  `poll_run.last_command*` fields, so clients can show what the target received
  without scraping the operator-side queue ledger.
- Operator JSON queue/status output also indexes delivered commands by
  `execution_decision` and mirrors `execution_decision_counts`, so dashboards
  can audit rejected delivery decisions without scanning every command record.
- `allow_arbitrary=yes` is reported as an explicit policy request.
  `arbitrary_execution_allowed=true` only when the queue is enabled, execution
  mode is `execute`, policy is `custom`, and arbitrary execution is explicitly
  allowed.

Operator queue inspection:

```sh
scripts/busierbox-server --queue-command 'busierbox reality-test --json'
scripts/busierbox-server --queue-command 'busierbox survey --json' --queue-expire-sec 3600
scripts/busierbox-server --transport command-queue --config local/server-config.json
scripts/busierbox-server --list-command-queue
scripts/busierbox-server --json-command-queue
scripts/busierbox-server --record-command-result cq-id --result-json result.json
scripts/busierbox-server --clear-command-queue
```

Queue entries include an id, timestamp, literal command text, command SHA-256,
timeout metadata, maximum output metadata, optional expiration metadata, status, and explicit
`execution_supported` / `delivery_supported=false` fields at queue time.
Each entry also stores a `queue_policy_snapshot` so old queue records remain
auditable if the operator configuration changes later. The
`command_queue_queued` operator event records the command id, command SHA-256,
timeout, maximum output limit, optional expiration, delivery/execution support flags, and the queue
policy snapshot. Live target polling responses and operator poll metadata include
the same command SHA-256. A poll can mark a queued entry `delivered`, attach a
`delivery_policy_snapshot`, return its command metadata to the target, and record
`execution_decision=pending` when policy permits execution, or `rejected` when
policy does not. The target later uploads the final `executed` or `rejected`
decision with result metadata. The operator event log keeps the stable
`command_queue_poll` event and also emits outcome-specific
`command_queue_poll_delivered`, `command_queue_poll_no_command`,
`command_queue_poll_rejected`, or `command_queue_poll_error` records for direct
timeline filtering. The `command_delivered` operator event includes the command
SHA-256, queue limits, and the same delivery policy snapshot.

The operator JSON status API indexes queue records by snapshot posture with
`commands_by_command_sha256`, `commands_by_created_at`, `commands_by_delivered_at`,
`commands_by_result_received_at`, `commands_by_result_source_path`,
`commands_by_timeout_sec`, `commands_by_max_output_bytes`,
`commands_by_expire_sec`, `commands_by_expires_at`, `commands_by_expired`,
`commands_by_queue_policy_enabled`, `commands_by_queue_policy_valid`,
`commands_by_queue_policy_execution_mode`,
`commands_by_queue_policy_allowed_commands`,
`commands_by_delivery_policy_enabled`, `commands_by_delivery_policy_valid`,
and `commands_by_delivery_policy_execution_mode`. Matching compact counts are
mirrored under `summary.command_queue_*_counts`, and the indexes are listed in
`api_collections.command_queue_commands` for frontend discovery. Timeout and
maximum-output counts let operator UIs show queued command limits without
rescanning every command. Expired queued work appears with status `expired`, no
longer counts as pending mailbox work, is skipped by target polls, and rejects
late result uploads. Result uploads are also grouped by
`commands_by_result_output_size_bucket` (`zero`, `small`, `medium`, `large`)
with matching `command_queue_result_output_size_bucket_counts` for dashboards
that need to highlight unexpectedly large output.

When the command-queue listener is running with `command_queue_tls=no`, it also
accepts structured result JSON with `POST /command-queue/result`. The JSON must
include `command_id`; the listener updates the matching command record, computes
stdout/stderr byte totals against the queued `max_output_bytes`, and logs both
`command_result_received` and the stable `command_queue_result_upload` event.
The operator log also emits outcome-specific
`command_queue_result_upload_received`, `command_queue_result_upload_rejected`,
or `command_queue_result_upload_error` records for direct result-upload timeline
filtering.

`--record-command-result` attaches a structured JSON result object to an
existing queued command, records `result_command_id`, `result_received_at`,
`result_source_path`, result stdout/stderr byte counts, the queued
`max_output_bytes` limit, and whether the result exceeded that limit. It also
logs `command_result_received` with the command id and output-limit metadata.
Status JSON exposes those event records through `events_by_detail_command_id`,
`events_by_detail_command_sha256`, `events_by_event_detail_command_id`,
`events_by_event_detail_command_sha256`, `events_by_service_detail_command_id`,
and `events_by_service_detail_command_sha256` so an operator UI can jump from a
command record or digest to its audit events without scanning the full event
tail. Result uploads also participate in operation and HTTP-status composites
such as `events_by_event_detail_operation`,
`events_by_service_detail_operation`, `events_by_event_detail_http_status`, and
`events_by_service_detail_http_status`, allowing direct lookup of accepted or
rejected result submissions by endpoint operation and response code. Poll
events also expose target-reported callback settings through
`events_by_detail_poll_mode`, `events_by_detail_poll_interval_sec`,
`events_by_detail_poll_jitter_pct`, `events_by_detail_poll_backoff`,
`events_by_detail_poll_max_interval_sec`, and `events_by_detail_max_polls`,
with mirrored `summary.event_detail_*_counts` counters for dashboards that need
to group live polls by interval policy without parsing every event payload.
The same event detail indexing also includes `details.sha256` for file-transfer
events, so file-service uploads and fetches can be correlated by content digest
separately from command text digests.
This is still operator-side bookkeeping; it does not poll, deliver, or execute
commands.

## Intermittent Target Mailboxes

Target-scoped command queue records now act as an operator-side mailbox for
devices that can only phone home briefly. A command queued for `target_id`
remains pending while the target is offline, is delivered on the next matching
`/command-queue/poll`, and stays auditable through delivery and result upload.

Status JSON derives heartbeat and mailbox fields from the target registry and
queue records:

- `targets[].last_seen`, `last_seen_via`, `offline_for_sec`, and
  `connectivity_state` (`online`, `recent`, `stale`, `offline`, or `unknown`)
  show when and how the target last contacted the operator.
- `targets[].next_expected_poll` is populated when the latest command-queue poll
  reported a polling interval.
- `targets[].mailbox_queued_command_count`,
  `mailbox_delivered_command_count`, `mailbox_result_received_command_count`,
  and `mailbox_pending_work_count` summarize queued work per target.
- `targets[].latest_command_result_at` and `latest_command_result_id` point to
  the latest received command result for that target.
- `targets[].latest_file_transfer_*`, `latest_survey_result_*`, and
  `latest_bridge_*` fields show the latest per-target file workflow, survey
  evidence, and bridge activity alongside the command mailbox. File-transfer
  and survey-result fields include route fields such as `*_route_kind`,
  `*_bridge_profile`, and `*_bridge_route_path` when available, so target detail
  views can distinguish direct workflows from bridged routes.

The status API also exposes a `target_mailbox_records` collection with one
record per target-scoped queued command. Each record includes the command id,
target id/label, command text, command digest, queue status, created/delivered
timestamps, result timestamp, result status, exit code, output-size metadata,
booleans for pending work and result availability, and ready-to-render wait
metadata such as `waiting_for`, `age_sec`, `pending_delivery_for_sec`,
`delivered_without_result_for_sec`, `result_latency_sec`, and corresponding
age buckets. `pending_reason` gives an operator-facing reason such as
`target-poll-overdue`, `target-offline`, `awaiting-result-upload`, or
`waiting-for-next-poll`, so headless clients and the TUI can explain why work is
still waiting. Expired records expose `expired=true`, `status=expired`, and
`waiting_for=none`. Indexes such as
`target_mailbox_records_by_target_id`,
`target_mailbox_records_by_status`,
`target_mailbox_records_by_waiting_for`,
`target_mailbox_records_by_pending_reason`,
`target_mailbox_records_by_expired`,
`target_mailbox_records_by_age_bucket`,
`target_mailbox_records_by_pending_work`, and
`target_mailbox_records_by_has_result` let TUI or API clients build per-target
mailbox panes without scraping the raw command queue.

Status JSON also exposes `command_queue_workflow_actions`, a small action
catalog for the command-queue/mailbox workflow itself. The records cover
inspect, list, queue command, clear queue, start listener, and stop listener
actions. Each record includes the equivalent `headless_command`, current queue
and mailbox counts, policy/support booleans, input or confirmation
requirements, offline queueability, and `operator_action_state` /
`operator_action_reason`. The `queue-command` action is explicitly marked
`queues_offline_work=true` and `target_phone_home_required=true`, while the
list action is marked as runnable from curses Enter. Indexes such as
`command_queue_workflow_actions_by_action_id`,
`command_queue_workflow_actions_by_category`,
`command_queue_workflow_actions_by_requires_input`,
`command_queue_workflow_actions_by_requires_confirmation`,
`command_queue_workflow_actions_by_queues_offline_work`, and
`command_queue_workflow_actions_by_can_run_from_curses_enter` let the TUI,
scripts, and future API clients render command-queue controls from the same
contract. Line-mode action `20` and the curses Mailbox pane use these records
to show what can be run now, what needs input, and what will wait for a later
phone-home window.

For file workflows, status JSON exposes `target_file_transfer_records`, a
unified target-scoped collection spanning staged target fetches, received
uploads, and completed fetch attempts. Each record includes `operation`,
`source_collection`, target id/label, request name or filename, source/stored
paths, status, digest, session metadata when available, and direct/bridged route
fields. Indexes such as `target_file_transfer_records_by_target_id`,
`target_file_transfer_records_by_operation`,
`target_file_transfer_records_by_status`,
`target_file_transfer_records_by_route_kind`, and
`target_file_transfer_records_by_request_name` let the TUI render a per-target
files pane without stitching together `staged_records`, `uploads`, and
`fetches` itself.

Status JSON also exposes `staged_file_workflow_actions`, a per-request action
catalog for staged files and staged release artifacts. Each staged request gets
records to inspect the staged entry, show the target-side fetch command, queue a
staged fetch for a known target through the mailbox, and unstage the request.
The records include `headless_command`, target/route fields, source existence,
release tuple metadata, offline queueability, confirmation requirements, and
`operator_action_state` / `operator_action_reason`. Indexes such as
`staged_file_workflow_actions_by_request_name`,
`staged_file_workflow_actions_by_target_id`,
`staged_file_workflow_actions_by_queues_offline_work`, and
`staged_file_workflow_actions_by_can_run_from_curses_enter` let the TUI render
the staged-files pane and Enter behavior from the same API contract used by
headless operators.

The file-service workflow itself is exposed as `file_service_workflow_actions`.
Those top-level records cover inspecting file workflow state, listing staged
files, staging a local file, showing a target upload command template, starting
the file-service listener, and stopping it. Records include the equivalent
`headless_command`, current listener state, route/bridge fields, staged/upload/
fetch/target-file counts, input and confirmation requirements, Enter behavior,
and a `target_command_template` for upload prompts. Indexes such as
`file_service_workflow_actions_by_action_id`,
`file_service_workflow_actions_by_route_kind`,
`file_service_workflow_actions_by_requires_input`, and
`file_service_workflow_actions_by_operator_action_state` let the TUI and API
clients render file-service controls without scraping `staged_records`,
`uploads`, or `fetches`.

Status JSON also exposes `target_activity_records`, a combined per-target feed
derived from heartbeat target records, mailbox records, phone-home attempts,
file transfers, bridge records, sessions, and latest survey results. The feed is
indexed by target id, category, source collection, operation, status, pending
work, waiting reason, command id, request name, filename, route, bridge profile,
and session id. This gives TUI and API clients one stable target-detail activity
source while preserving the more detailed source collections.

Target status also exposes `targets_by_connectivity_state`,
`targets_by_last_seen_via`, `targets_by_has_next_expected_poll`, and
`targets_by_mailbox_pending_work`, plus workflow indexes such as
`targets_by_latest_file_transfer_operation`,
`targets_by_latest_file_transfer_route_kind`,
`targets_by_latest_file_transfer_bridge_profile`,
`targets_by_latest_survey_result_kind`,
`targets_by_latest_survey_result_route_kind`,
`targets_by_latest_survey_result_bridge_profile`, and
`targets_by_latest_bridge_profile`. Text status and the noninteractive
workbench print each target's recent mailbox items, recent phone-home attempts,
and latest workflow activity below the heartbeat and mailbox counts, so an
operator can queue work while a target is gone, see the last successful
phone-home path, inspect pending work, see how much queued work remained after a
poll, and confirm delivery when the target reconnects.

For target-centered operator UX, status JSON also includes
`target_workflow_actions`. These records are generated per target and expose the
same workflows a TUI should offer: inspect scoped status, open a scoped
workbench, queue mailbox work, queue a survey bootstrap command, serve survey
bootstrap, stage a file for target fetch, stage a release artifact for target
fetch when a release bundle is available, queue a staged fetch command, show a
target upload command, start the file service, start any bridge profile tied to
that target, and queue a bridge-related reverse-access start command for the
target mailbox.
Each action carries a `headless_command` so the TUI can show the exact CLI path
instead of hiding automation behind an interactive-only flow. Action records
also expose `offline_supported`, `requires_target_online`,
`queues_offline_work`, `target_phone_home_required`, `operator_action_state`,
`operator_action_reason`, and `can_run_from_curses_enter`, with matching status
summary counts and lookup maps. TUI and API clients can use those fields to show
which target workflows can be prepared while a target is offline, which actions
need prompted input, which bridge actions need the target online now, and which
actions leave mailbox work waiting for the next phone-home window.

Status JSON also exposes `operator_console_workflows`, a top-level catalog for
frontends that want the console organized around workflows instead of raw
collections. Each record groups the related source/action collections for target
fleet, target actions, mailbox, bridges, files, survey, daemon, release
artifacts, build config, jobs, events, and target activity. Records include the
primary collection, matching TUI shortcut and line-mode action, `headless_command`,
target-scoping flags, multi-target/offline-queue support, action counts,
enter-runnable counts, pending-work counts, warning counts, and an
`operator_action_state`. Indexes such as `operator_console_workflows_by_group`,
`operator_console_workflows_by_primary_collection`,
`operator_console_workflows_by_offline_queue_supported`, and
`operator_console_workflows_by_operator_action_state` let TUI, API, and future
web clients render the same operator workflow map without reverse-engineering
the lower-level action catalogs.

The same actions can be run headlessly or from the line-oriented TUI. For
automation, use the stable action id:

```sh
scripts/busierbox-server --run-target-workflow-action target-alpha:queue-command \
  --target-workflow-command 'busierbox survey --json'

scripts/busierbox-server --run-target-workflow-action target-alpha:queue-survey-bootstrap

scripts/busierbox-server --run-target-workflow-action target-alpha:stage-file-fetch \
  --target-workflow-local-file ./dist/busierbox-target-full \
  --target-workflow-request-name busierbox

scripts/busierbox-server --run-target-workflow-action target-alpha:stage-release-artifact \
  --target-workflow-command by_device:lab-router

scripts/busierbox-server --run-target-workflow-action target-alpha:queue-staged-fetch \
  --target-workflow-request-name busierbox

scripts/busierbox-server --run-target-workflow-action target-alpha:show-upload-command \
  --target-workflow-command /etc/config/network

scripts/busierbox-server --run-target-workflow-action target-alpha:queue-bridge-start:lab-http
```

In line-mode TUI, action `15` lists the target workflow actions and prompts for
the required command/path fields before applying the same target-scoped queue or
staging operation. After a target action runs, the TUI prints the action return
code and a refreshed target activity summary so the operator can immediately see
queued mailbox work and last-contact state. No action changes the safety
boundary: target execution still requires an explicit target-side fetch, upload,
poll, or bridge connection.
The line-mode TUI also keeps a persistent status bar above its action menu with
service, warning, target, connectivity-state, pending-mailbox, poll-overdue,
selected-target, and event counts. Its menu is grouped into Services, Targets,
Bridges, Files and releases, and Automation/config sections so multi-device
workflows stay centered on target selection, target detail, and mailbox actions
without hiding the existing numeric shortcuts.
The curses TUI keeps the same fleet context visible through a `Target Fleet`
pane. It lists known targets with connectivity state, pending mailbox work,
poll-overdue state, and last-seen time; selecting a target and pressing Enter
sets the current target filter, while the details pane shows heartbeat, mailbox,
latest result, latest survey/file activity, and bridge context for that device.
The target detail also shows recent `target_activity_records`, and the dedicated
`Target Activity` pane lists the same combined feed so the operator can scan
mailbox, phone-home, file, survey, bridge, and session events without switching
panes for each source collection.
The adjacent `Target Files` pane is backed by `target_file_transfer_records`, so
staged fetches, received uploads, and fetch attempts appear together with their
target id, operation, status, route, digest, session metadata, and local paths.
It keeps a persistent group navigation row above the main panes, with shortcuts
for targets, target actions, mailbox, bridges, daemon, files, workflows, events,
and activity; the files shortcut opens the unified `Target Files` view and the
activity shortcut opens the unified `Target Activity` feed. This makes the
curses view behave more like target/workflow submenus
while keeping all panes backed by the same status JSON records.
The header also keeps fleet connectivity visible across panes: online, recent,
stale, offline, and unknown target counts, pending mailbox work, overdue polls,
and the latest phone-home timestamp.
The adjacent `Target Actions` pane lists the per-target workflow actions exposed
by status JSON, including whether each action queues offline work, requires
input, can run from curses Enter, or needs a later phone-home. Pressing Enter
runs no-input actions whose `operator_action_state` is ready or
queueable-offline, such as queueing survey bootstrap work or starting
target-scoped services; actions that need operator input keep pointing at
line-mode action `15` and the shown headless command.
It also includes a persistent `Mailbox` pane for target-scoped queued work. The
pane shows command id, target, delivery/result status, pending state, and the
current pending reason; the details view expands the selected mailbox record
with connectivity state, timestamps, result status/exit code, last phone-home
path, next expected poll, pending reason, and the queued command. Use line-mode
action `20` for the full command queue and result listing.
Mutating target workflow actions record `target_workflow_action_completed`
events with the target id, action id, headless command, and result-specific
metadata such as queued command id or staged request name, so headless and TUI
runs leave the same operator audit trail.
Action `16` selects the current target filter for the workbench session by
target number, id, label, or alias; enter `all` to clear the filter and return
to the fleet view. The selector shows mailbox-pending and poll-overdue state so
the operator can choose the right offline target without opening each detail
view first. The selected target is recorded in workbench state and subsequent
generated commands, staging operations, and target workflow actions use that
target context. Action `18` opens a target detail view for the current target, a
selected target, or all targets; it prints heartbeat/mailbox/activity state,
latest file/survey/bridge route evidence, recent mailbox records, target
workflow actions, a `Target activity records` section backed by
`target_activity_records`, and the equivalent `--target-id TARGET --status`
command. Action `21` opens the same activity feed directly for the current
target, a selected target, or all targets, using `--json-status` as the
equivalent headless source for automation.

The smoke suite includes a deterministic intermittent-connectivity harness for
this path. It queues target-scoped work while targets are offline, proves an
anonymous poll cannot drain target mailboxes, simulates a stale/offline
heartbeat, delivers the selected target's work on a later poll, rejects missing
or mismatched target result uploads without mutating the command, rejects a
dropped/truncated result upload while leaving the delivered command awaiting a
valid result, accepts the matching target result, and verifies status JSON plus text status show
`last_seen`, `last_seen_via`, `offline_for_sec`, `connectivity_state`,
`next_expected_poll`, mailbox pending counts, and latest command result
metadata. Phone-home records include `queued_remaining_count` and
`pending_work_remaining` for poll attempts, with matching status indexes and
summary counts for dashboards and TUI panes.
The harness also writes `topology.json` alongside its status and HTTP
transcript artifacts. That topology artifact records operator service ports,
known target ids, scripted link states such as short reconnect windows and
interrupted transfers, representative operator commands, and the mapping needed
for a future networked-QEMU lab to replay the same mailbox scenarios across
virtual network boundaries.
