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

## Workbench Actions

The operator workbench exposes daemon lifecycle controls as normal workflow
actions, with the same headless commands shown in status JSON and TUI output:

- `operator-daemon-start` starts a foreground daemon for selected services.
- `operator-daemon-status` inspects daemon and managed listener state.
- `operator-daemon-stop` stops managed daemon-owned services.
- `systemd-user-print` renders the user service unit.
- `systemd-user-install` installs the user service unit.
- `systemd-user-start`, `systemd-user-stop`, `systemd-user-restart`, and
  `systemd-user-status` mirror the `systemctl --user` lifecycle controls.

These are metadata-backed workflow actions, so automated clients can discover
them from `workbench_actions`, group them through
`workbench_actions_by_category.daemon`, and use each record's `run_command`,
`dry_run_command`, or `start_job_command` without inferring the right invocation
from the lower-level command string.
Foreground-safe actions can also be run through the workbench action API:

```sh
scripts/busierbox-server --run-workbench-action systemd-user-status \
  --workbench-action-dry-run
```

Line-mode TUI action `11` lists the same actions and can preview or run
foreground actions after explicit selection. Long-running/background-capable
actions continue to use TUI action `12` or `--start-workbench-job`.

The curses workbench keeps build and operator configuration visible in a
`Build Config` pane. It lists guided build fields, current values, category,
safety boundary, fixed options, examples, and the equivalent `--set-build-config`
command. Pressing Enter on a field prompts for a new value and applies the same
validated config update used by line-mode action `14`.

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
