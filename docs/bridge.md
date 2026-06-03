# Server Bridge

`scripts/grit-console --transport bridge` starts an explicit TCP relay. It
listens on the operator host and forwards each accepted client connection to a
configured destination host and port that is visible from the operator/server
running `grit-console`.

Example:

```sh
scripts/grit-console \
  --transport bridge \
  --listen-host 127.0.0.1 \
  --bridge-port 22206 \
  --bridge-dest-host 10.10.40.8 \
  --bridge-dest-port 80
```

This is useful when a target, lab host, or jump point can reach the operator
listener and you want the operator/server to relay that connection to a known
endpoint. The bridge is off unless selected with `--transport bridge`, and
`--bridge-dest-port` is required.

Status and audit behavior:

- `--status`, `--json-status`, and `--api-status` include the `bridge` service
  alongside `ssh`, shell, file-service, and command-queue listeners.
- Bridge sessions are stored under the normal session root with
  `bridge-result.json`, including byte counts in both directions and the relay
  close reason.
- Operator events include `bridge_connected`, `bridge_closed`, and
  `bridge_error` with destination host/port and byte counts.
- Named profiles persist the latest successful relay timestamp and byte counts,
  and failed upstream connections persist `last_failure_at`,
  `last_failure_reason`, destination endpoint, and remote client address so the
  console/status views can explain why a bridge path is not currently usable.
- `--one-shot` exits after one bridged connection, matching other listener
  workflows.

The bridge does not authenticate or inspect the forwarded protocol. Bind it to
the narrowest practical listener address and use existing network controls when
exposing it beyond a local lab interface.

## Named Profiles

Bridge profiles store repeatable bridge routes for CLI, status JSON, and the
operator console. `route add NAME LISTEN_PORT DEST_HOST DEST_PORT [FROM=TO ...]`
means "the target connects to `LISTEN_PORT` on the operator, and the operator
forwards to `DEST_HOST:DEST_PORT`." A profile without explicit hops is a simple
one-hop route:

```sh
scripts/grit-console \
  --save-bridge-profile lab-http \
  --bridge-port 22206 \
  --bridge-dest-host 10.10.40.8 \
  --bridge-dest-port 80 \
  --bridge-profile-purpose web-admin

scripts/grit-console --list-bridge-profiles
scripts/grit-console --json-bridge-profiles
scripts/grit-console --inspect-bridge-profile lab-http
scripts/grit-console --transport bridge --bridge-profile lab-http
```

Profiles can also carry explicit multi-hop chain metadata. Hops document the
path a target uses to reach the operator listener; they do not change the TCP
relay destination. Repeat `--bridge-hop` when saving the profile:

```sh
scripts/grit-console \
  --save-bridge-profile rack-chain \
  --bridge-port 22206 \
  --bridge-dest-host 10.10.40.8 \
  --bridge-dest-port 80 \
  --bridge-hop operator:22206=rack-host:9001 \
  --bridge-hop rack-host:9001=target-lan-device:80
```

The stored path is rendered as:

```text
operator:22206 -> rack-host:9001 -> target-lan-device:80
```

Use `--delete-bridge-profile NAME` to remove a stored profile. Deletion records
a `bridge_profile_deleted` event and does not kill an already-running bridge
listener; stop listeners explicitly with `--stop --transport bridge`.

In line-mode console, action `17` opens bridge profile management. It lists saved
profiles, can create or update a profile from prompts, inspect a profile, start
or stop the bridge listener, and delete a profile. Each console path prints the
equivalent `scripts/grit-console ...` command before or after applying the
action.
The line-oriented console's route views list saved profiles/chains with state,
target association, hop count, and failure state. Route detail shows route path,
listen/destination endpoints, last relay success, byte counters, last failure
reason, and the equivalent start/stop commands from
`bridge_profile_workflow_actions`. `route start NAME|N` starts an inactive
profile, and `route stop NAME|N` stops the active bridge listener for that
profile.

Profiles live in `bridge-profiles.json` under the operator session directory by
default. Each record includes the listen endpoint, destination endpoint,
explicit hops, hop count, multi-hop flag, optional target id/label, purpose,
notes, state, route path, start/stop commands, and whether the profile requires
a target to be online. `--json-status` exposes `bridge_profiles` plus indexes
such as `bridge_profiles_by_name`, `bridge_profiles_by_target_id`,
`bridge_profiles_by_current_state`, `bridge_profiles_by_active`,
`bridge_profiles_by_multi_hop`, `bridge_profiles_by_hop_count`, and
`bridge_profiles_by_route_path` for console and automation clients. Successful and
failed relay lifecycle is indexed with
`bridge_profiles_by_has_last_successful_relay` and
`bridge_profiles_by_has_last_failure`, and the text list/inspect commands show
the latest success/failure fields directly. The simple direct `--bridge-*`
flags remain the easy one-hop path.

Status JSON also exposes `bridge_profile_workflow_actions`, with
`inspect-profile`, `start-profile`, `stop-profile`, and `delete-profile`
records for each saved bridge profile. These records include generated
headless commands, stable `run_command` / `dry_run_command` fields, route
metadata, current profile state, confirmation requirements, and interactive
readiness. Operators can execute the same records with
`--run-bridge-profile-workflow-action ACTION_OR_NUMBER`; previews use
`--bridge-profile-workflow-dry-run`, and stop/delete actions can require
`--confirm-bridge-profile-workflow-action`. Automation clients can group them
through `bridge_profile_workflow_actions_by_bridge_profile` or
`bridge_profile_workflow_actions_by_operator_action_state` instead of deriving
actions from bridge profile text.

Status JSON also exposes normalized `bridge_hop_records`, one record per
profile hop. Each hop records its profile name, ordinal, source/destination
endpoint, parsed host/port fields, route path, target association, profile
state, and first/last-hop flags. Indexes such as `bridge_hops_by_profile`,
`bridge_hops_by_from`, `bridge_hops_by_to`, `bridge_hops_by_route_path`, and
`bridge_hops_by_profile_has_last_failure` let operator consoles render and
filter chain segments without reparsing embedded profile data.

When `--bridge-profile` is selected for other operator workflows, generated
target commands are route-aware. File fetch/upload commands and probe bootstrap
commands use the profile's target-visible first hop, while their status records
carry `route_kind`, `bridge_profile`, `bridge_route_path`, and `target_route`
metadata so a console can show whether the operator is using a direct or bridged
route.
