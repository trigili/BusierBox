# Command Queue

The command queue is reserved for a future explicit advanced mode where a target
polls an operator service for queued work. It is separate from file upload,
fetch, evidence push, and reverse shells.

Current behavior is intentionally non-executing:

- `BB_COMMAND_QUEUE_ENABLE` defaults to `no`.
- `busierbox command-queue status --json` reports the compiled/effective policy.
- `busierbox command-queue poll --json`, `once`, and `daemon` report a dry-run
  target polling plan. They do not contact the operator service, fetch queue
  entries, upload results, or execute queued commands in this build.
- `scripts/busierbox-server --queue-command ...` records explicit operator
  queue entries in `local/operator-session/command-queue.json` for inspection
  and future tooling. The current server does not deliver or execute them.
- `scripts/busierbox-server --json-status` or `--api-status` includes the
  command queue path, counts, entries, and non-execution safety boundary.
- `busierbox plan command-queue --json` reports the safety boundary and whether
  polling would be configured.

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
- Trailer overrides alone are not an execution capability; this build does not
  execute queued commands.
- Target-side `poll`, `once`, and `daemon` expose `would_poll`,
  `poll_transport_supported=false`, `delivery_supported=false`,
  `result_upload_supported=false`, and `execution_supported=false` so frontend
  and integration tooling can distinguish policy/planning from active control.

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
existing queued command and logs `command_result_received`. This is still
operator-side bookkeeping; it does not poll, deliver, or execute commands.
