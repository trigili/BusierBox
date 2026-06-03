# Operator Daemon

`scripts/grit-console --daemon` runs a foreground operator control-plane
process that owns selected listener child processes. Direct one-service commands
still work; daemon mode is an explicit lifecycle wrapper around those same
headless transports.

Select services with repeatable `--daemon-service` flags:

```sh
scripts/grit-console --daemon \
  --daemon-service file-service \
  --daemon-service command-queue
```

Without explicit services, daemon mode uses config opt-ins such as
`file_service_enable=yes`, `command_queue_enable=yes`,
`bridge_enable=yes`, `probe_enable=yes`, and `rshell_enable=yes`.

The daemon writes normal service state into the configured server state file.
It also records an `operator-daemon` state entry with child PIDs, selected
services, and process-log paths under `operator_session_dir/daemon-logs/`.
Existing `--status`, `--json-status`, and `--stop` continue to work:

```sh
scripts/grit-console --status
scripts/grit-console --json-status
scripts/grit-console --stop
```

`--stop` uses the same managed-process ownership checks as direct listeners and
terminates daemon-owned child listeners through the recorded state. This keeps
foreground/headless operation and daemon operation on the same status and event
surface for line-console, API, and systemd-user integration.

## Workbench Actions

The operator workbench exposes daemon lifecycle controls as normal workflow
actions, with the same headless commands available in status JSON, verbose line
console views, and the event log:

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
Workbench action records also expose `operator_action_state`,
`operator_action_reason`, `can_run_from_curses_enter`, and
`curses_enter_action` so line-console and API clients can distinguish
background-ready jobs, foreground-safe actions, confirmation-gated actions, and
prompted placeholder commands without parsing command text. The curses-named
fields are retained as compatibility metadata; the active interactive frontend
is the line-oriented `grit[...]>` REPL.
Status JSON also exposes the daemon subset as
`operator_daemon_workflow_actions`. These records keep the workbench action id
but add daemon-specific fields such as `workflow`,
`daemon_status`, `daemon_attached`, selected daemon services, child PIDs,
alive child count, systemd user action, and the daemon-specific Enter action.
Each record also exposes stable `run_command` and `dry_run_command` fields for
`--run-operator-daemon-workflow-action ACTION_OR_NUMBER`; confirmation-gated
daemon/systemd actions use `--confirm-operator-daemon-workflow-action`, and
previews use `--operator-daemon-workflow-dry-run`.
Indexes such as `operator_daemon_workflow_actions_by_workflow`,
`operator_daemon_workflow_actions_by_daemon_attached`,
`operator_daemon_workflow_actions_by_systemd_user_action`, and
`operator_daemon_workflow_actions_by_operator_action_state` let console and API
clients render daemon lifecycle controls without special-casing the broader
`workbench_actions` list.
Individual listener controls are also exposed through `service_workflow_actions`.
Each service has `inspect-status`, `start-service`, and `stop-service` records
with the generated headless command, current listener state, confirmation
requirements, and interactive readiness. API clients can group these through
`service_workflow_actions_by_service` or
`service_workflow_actions_by_operator_action_state` to render service controls
without inferring start/stop state from command text.
The same records include selector-based `run_command` and `dry_run_command`
values for headless parity:

```sh
scripts/grit-console --run-service-workflow-action file-service:start-service \
  --service-workflow-dry-run
```

Foreground-safe actions can also be run through the workbench action API:

```sh
scripts/grit-console --run-workbench-action systemd-user-status \
  --workbench-action-dry-run
```

The line-oriented console lists the same actions under `daemon` and module views
and can preview or run foreground actions after explicit selection.
Long-running/background-capable actions continue to use managed jobs through
the REPL or `--start-workbench-job`.

The line-oriented console keeps build and operator configuration visible through
`options`, `show options`, and build/config actions. These list guided build
fields, current values, category, safety boundary, fixed options, examples, and
the equivalent `--set-build-config` command. Setting a field applies the same
validated config update used by noninteractive build-config commands.
It also keeps managed background workflow state visible through `jobs` and
`jobs -v`. These list job ids, effective state, action id, cancel support,
process ownership, outcome, exit status, timestamps, log path, output tail, and
command. `job cancel ID|N` cancels a selected managed job when the same ownership
checks used by noninteractive job cancellation say cancellation is supported.

The line-oriented console action catalog shows action ids, categories,
background support, confirmation requirements, and the equivalent
dry-run/run/start-job commands. Background-safe actions can be started as managed
jobs; foreground or confirmation-sensitive actions remain routed through
explicit preview and confirmation commands.

Operator daemon commands make attach-style operation visible in the line console.
They read daemon and daemon-owned child listener state from the same status files
as headless `--json-status`, show the equivalent daemon start/status/stop
commands, and can start the daemon as a managed job or stop the currently
attached daemon when it is already running.

## Systemd User Service

The same daemon command can be rendered or installed as a systemd user service:

```sh
scripts/grit-console --systemd-user-action print \
  --daemon-service file-service \
  --daemon-service command-queue

scripts/grit-console --systemd-user-action install \
  --daemon-service file-service \
  --systemd-user-unit-name grit-operator.service
```

`install` writes the unit to `~/.config/systemd/user` by default and prints the
follow-up `systemctl --user daemon-reload` / `enable --now` commands. Service
control actions are also available:

```sh
scripts/grit-console --systemd-user-action start
scripts/grit-console --systemd-user-action stop
scripts/grit-console --systemd-user-action restart
scripts/grit-console --systemd-user-action status
```

Use `--systemd-user-dry-run` to print the `systemctl --user ...` command without
executing it. Root/system-wide units are intentionally not installed by this
flow; keep those explicit and separate if needed.
