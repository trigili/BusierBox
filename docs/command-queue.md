# Command Queue

The command queue is reserved for a future explicit advanced mode where a target
polls an operator service for queued work. It is separate from file upload,
fetch, evidence push, and reverse shells.

Current behavior is intentionally non-executing:

- `BB_COMMAND_QUEUE_ENABLE` defaults to `no`.
- `busierbox command-queue status --json` reports the compiled/effective policy.
- `busierbox command-queue poll --json`, `once`, and `daemon` do not execute
  queued commands in this build.
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
