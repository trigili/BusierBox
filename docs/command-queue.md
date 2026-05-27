# Command Queue

The command queue is reserved for a future explicit advanced mode where a target
polls an operator service for queued work. It is separate from file upload,
fetch, evidence push, and reverse shells.

Current behavior is intentionally non-executing:

- `BB_COMMAND_QUEUE_ENABLE` defaults to `no`.
- `busierbox command-queue status --json` reports the compiled/effective policy
  and a compact `policy_summary` for frontend/operator tooling.
- Invalid effective policy is reported as `policy_valid=false` with explicit
  `policy_errors`; invalid policy suppresses `would_poll`.
- `busierbox command-queue poll --json`, `once`, and `daemon` report a dry-run
  target polling plan. They do not contact the operator service, fetch queue
  entries, upload results, or execute queued commands in this build.
- `scripts/busierbox-server --queue-command ...` records explicit operator
  queue entries in `local/operator-session/command-queue.json` for inspection
  and future tooling. The current server does not deliver or execute them.
- `scripts/busierbox-server --json-status` or `--api-status` includes the
  command queue path, counts, entries, `commands_by_id`,
  `commands_by_status`, latest queue/result timestamps, `policy_summary`, and
  non-execution safety boundary.
- `busierbox plan command-queue --json` and `manifest --json` expose the same
  policy validity fields so release tooling and frontends do not treat an
  inconsistent policy as ready to poll.

Configuration keys:

```sh
BB_COMMAND_QUEUE_ENABLE="no"
BB_COMMAND_QUEUE_PORT="22205"
BB_COMMAND_QUEUE_TLS="yes"
BB_COMMAND_QUEUE_REQUIRE_TOKEN="yes"
BB_COMMAND_QUEUE_TOKEN_SOURCE="manual"
BB_COMMAND_QUEUE_ALLOWED_COMMANDS="none"
BB_COMMAND_QUEUE_ALLOW_ARBITRARY="no"
```

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
  `poll_transport_supported=false`, `delivery_supported=false`,
  `result_upload_supported=false`, `execution_supported=false`, and a
  `policy_summary` so frontend and integration tooling can distinguish
  policy/planning from active control. They also expose a compact `poll_plan`
  object with mode, status, endpoint, explicit-target-action, dry-run-only,
  would-contact-operator, queued-command availability, delivery/result upload,
  execution, and hidden-control-channel fields.
- `allow_arbitrary=yes` is reported as an explicit policy request, not an
  execution grant; `arbitrary_execution_allowed=false` remains false while this
  build has `execution_supported=false`.

Operator queue inspection:

```sh
scripts/busierbox-server --queue-command 'busierbox reality-test --json'
scripts/busierbox-server --list-command-queue
scripts/busierbox-server --json-command-queue
scripts/busierbox-server --record-command-result cq-id --result-json result.json
scripts/busierbox-server --clear-command-queue
```

Queue entries include an id, timestamp, literal command text, timeout metadata,
maximum output metadata, status, and explicit `execution_supported=false` /
`delivery_supported=false` fields. They are operator-visible records only until
a later explicitly enabled command-queue transport and target execution policy
are implemented.

`--record-command-result` attaches a structured JSON result object to an
existing queued command, records `result_command_id`, `result_received_at`,
`result_source_path`, result stdout/stderr byte counts, the queued
`max_output_bytes` limit, and whether the result exceeded that limit. It also
logs `command_result_received` with the command id and output-limit metadata.
This is still operator-side bookkeeping; it does not poll, deliver, or execute
commands.
