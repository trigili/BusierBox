# Command Queue

The command queue is an explicit advanced mode where a target can poll an
operator service for queued work. It is separate from file upload, fetch,
evidence push, and reverse shells.

Current behavior is intentionally non-executing:

- `BB_COMMAND_QUEUE_ENABLE` defaults to `no`.
- `busierbox command-queue status --json` reports the compiled/effective policy
  and a compact `policy_summary` for frontend/operator tooling.
- Invalid effective policy is reported as `policy_valid=false` with explicit
  `policy_errors`; invalid policy suppresses `would_poll`.
- `busierbox command-queue poll --json`, `once`, and `daemon` report a dry-run
  target polling plan by default. With explicit `--live`, they contact the
  configured operator command-queue endpoint and can append structured poll
  events. Live polling currently requires `BB_COMMAND_QUEUE_TLS=no`; TLS
  command-queue polling is reported as unsupported instead of silently falling
  back to plaintext. Live polls can receive queued command metadata, but the
  target records an explicit rejected execution decision and never executes
  queued commands in this build. It can upload the rejected-result metadata so
  the operator ledger has a complete decision record.
- When `BB_COMMAND_QUEUE_REQUIRE_TOKEN=yes`, enabled queues require
  `BB_COMMAND_QUEUE_TOKEN` on the target and `command_queue_token` on the
  operator server config. Poll and result requests send/check
  `X-BusierBox-Command-Queue-Token`.
- `scripts/busierbox-server --queue-command ...` records explicit operator
  queue entries in `local/operator-session/command-queue.json` for inspection
  and tooling. The command-queue listener can mark a queued entry delivered to
  a polling target, but execution remains unsupported.
- `scripts/busierbox-server --json-status` or `--api-status` includes the
  command queue path, counts, entries, `commands_by_id`,
  `commands_by_status`, result lookup maps, latest queue/result timestamps,
  `policy_summary`, `mode_semantics`, `mode_summary`, and non-execution safety
  boundary.
- Human `--status`, `--list-command-queue`, and the line-oriented workbench
  print the same mode lifecycle and non-execution flags so operators do not
  need JSON tooling to distinguish default dry-run planning from explicit
  `--live` metadata polling.
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
`rejected`, and the daemon records `command_queue_poll_shutdown` when the loop
exits. Target-side JSONL events use the same structured event-bus envelope as
operator events: `schema`, `id`, `ts`, `service`, `session`, `event`, `level`,
`remote`, and `details`.

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
and `allow_arbitrary=no`.

Safety boundary:

- The command queue is disabled by default.
- It is not required for normal file transfer or reverse shell workflows.
- It is visible in `config-info`, `runtime-config --json`, `manifest --json`,
  and `plan command-queue`.
- `config-info` and `runtime-config --json` expose policy validity alongside
  the raw effective settings so operators do not need to infer safety state.
- Trailer overrides alone are not an execution capability; this build does not
  execute queued commands.
- Target-side `poll`, `once`, and `daemon` expose `would_poll`,
  live-mode `poll_transport_supported`, `delivery_supported`,
  `result_upload_supported`, `execution_supported=false`, and a
  `policy_summary` so frontend and integration tooling can distinguish
  policy/planning from explicit live polling. Live `delivery_supported=true`
  means the target can receive queued metadata; it does not imply command
  execution. Live `result_upload_supported=true` means the target can upload
  structured rejection/result metadata to the operator endpoint; it still does
  not imply command execution. Disabled or invalid policy keeps `would_contact_operator=false`
  and `active_control_channel=false` even when a user passes `--live`. They
  also expose a compact `poll_plan` object with mode, status, endpoint,
  explicit-target-action, dry-run-only, would-contact-operator, queued-command
  availability, delivery/result upload, execution, and hidden-control-channel
  fields.
- `command-queue --json` also includes `mode_semantics` for `status`, `poll`,
  `once`, `daemon`, and `stop`. Each entry declares whether the mode is selected,
  whether it needs an operator host, its lifecycle label (`inspect`,
  `single-poll`, `single-cycle`, `long-running`, or `stop`), and the same
  non-execution safety booleans so UIs do not infer mode behavior from strings.
- The same mode data is exposed as flat `mode_records`, with lookup maps by
  mode, lifecycle, polling behavior, live-support status, execution support,
  and active-control-channel state. `api_collections.mode_records` publishes
  count, summary-key, count-summary-key, primary-key, and index metadata for
  frontend discovery.
- `plan command-queue --json` exposes the planned polling mode with the same
  flat record/index/API pattern, plus `mode_records_by_planned`, so dashboards
  can show that a valid enabled policy would start explicit `command-queue
  poll` without implying command execution.
- `mode_summary` mirrors those mode records into compact counts for polling
  modes, operator-host-required modes, delivery-capable live modes, active
  control-channel modes, result-upload modes, and execution-capable modes.
- `command-queue --json` includes `daemon_state` and `stop_result` objects so
  operator tooling can show whether a live polling loop is visible, stale,
  stopped, or skipped because ownership could not be verified.
- `allow_arbitrary=yes` is reported as an explicit policy request, not an
  execution grant; `arbitrary_execution_allowed=false` remains false while this
  build has `execution_supported=false`.

Operator queue inspection:

```sh
scripts/busierbox-server --queue-command 'busierbox reality-test --json'
scripts/busierbox-server --transport command-queue --config local/server-config.json
scripts/busierbox-server --list-command-queue
scripts/busierbox-server --json-command-queue
scripts/busierbox-server --record-command-result cq-id --result-json result.json
scripts/busierbox-server --clear-command-queue
```

Queue entries include an id, timestamp, literal command text, timeout metadata,
maximum output metadata, status, and explicit `execution_supported=false` /
`delivery_supported=false` fields at queue time. Live target polling can mark a
queued entry `delivered`, return its command metadata to the target, and record
`execution_decision=rejected`; the target does not execute it.

When the command-queue listener is running with `command_queue_tls=no`, it also
accepts structured result JSON with `POST /command-queue/result`. The JSON must
include `command_id`; the listener updates the matching command record, computes
stdout/stderr byte totals against the queued `max_output_bytes`, and logs both
`command_result_received` and `command_queue_result_upload`.

`--record-command-result` attaches a structured JSON result object to an
existing queued command, records `result_command_id`, `result_received_at`,
`result_source_path`, result stdout/stderr byte counts, the queued
`max_output_bytes` limit, and whether the result exceeded that limit. It also
logs `command_result_received` with the command id and output-limit metadata.
This is still operator-side bookkeeping; it does not poll, deliver, or execute
commands.
