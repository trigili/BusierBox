# Operator Daemon

`scripts/busierbox-server --daemon` runs a foreground operator control-plane
process that owns selected listener child processes. Direct one-service commands
still work; daemon mode is an explicit lifecycle wrapper around those same
headless transports.

Select services with repeatable `--daemon-service` flags:

```sh
scripts/busierbox-server --daemon \
  --daemon-service file-service \
  --daemon-service command-queue
```

Without explicit services, daemon mode uses config opt-ins such as
`file_service_enable=yes`, `command_queue_enable=yes`,
`bridge_enable=yes`, `survey_bootstrap_enable=yes`, and `rshell_enable=yes`.

The daemon writes normal service state into the configured server state file.
It also records an `operator-daemon` state entry with child PIDs, selected
services, and process-log paths under `operator_session_dir/daemon-logs/`.
Existing `--status`, `--json-status`, and `--stop` continue to work:

```sh
scripts/busierbox-server --status
scripts/busierbox-server --json-status
scripts/busierbox-server --stop
```

`--stop` uses the same managed-process ownership checks as direct listeners and
terminates daemon-owned child listeners through the recorded state. This keeps
foreground/headless operation and daemon operation on the same status and event
surface for future TUI and systemd-user integration.

## Systemd User Service

The same daemon command can be rendered or installed as a systemd user service:

```sh
scripts/busierbox-server --systemd-user-action print \
  --daemon-service file-service \
  --daemon-service command-queue

scripts/busierbox-server --systemd-user-action install \
  --daemon-service file-service \
  --systemd-user-unit-name busierbox-operator.service
```

`install` writes the unit to `~/.config/systemd/user` by default and prints the
follow-up `systemctl --user daemon-reload` / `enable --now` commands. Service
control actions are also available:

```sh
scripts/busierbox-server --systemd-user-action start
scripts/busierbox-server --systemd-user-action stop
scripts/busierbox-server --systemd-user-action restart
scripts/busierbox-server --systemd-user-action status
```

Use `--systemd-user-dry-run` to print the `systemctl --user ...` command without
executing it. Root/system-wide units are intentionally not installed by this
flow; keep those explicit and separate if needed.
