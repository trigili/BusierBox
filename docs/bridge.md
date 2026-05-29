# Server Bridge

`scripts/busierbox-server --transport bridge` starts an explicit TCP relay. It
listens on the operator host and forwards each accepted client connection to a
configured destination host and port.

Example:

```sh
scripts/busierbox-server \
  --transport bridge \
  --listen-host 127.0.0.1 \
  --bridge-port 22206 \
  --bridge-dest-host 10.10.40.8 \
  --bridge-dest-port 80
```

This is useful when a target, lab host, or jump point can reach a device or
service that the operator workstation cannot route to directly. The bridge is
off unless selected with `--transport bridge`, and `--bridge-dest-port` is
required.

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
  TUI/status views can explain why a bridge path is not currently usable.
- `--one-shot` exits after one bridged connection, matching other listener
  workflows.

The bridge does not authenticate or inspect the forwarded protocol. Bind it to
the narrowest practical listener address and use existing network controls when
exposing it beyond a local lab interface.

## Named Profiles

Bridge profiles store repeatable bridge routes for CLI, status JSON, and the
operator console. A profile without explicit hops is a simple one-hop route:

```sh
scripts/busierbox-server \
  --save-bridge-profile lab-http \
  --bridge-port 22206 \
  --bridge-dest-host 10.10.40.8 \
  --bridge-dest-port 80 \
  --bridge-profile-purpose web-admin

scripts/busierbox-server --list-bridge-profiles
scripts/busierbox-server --json-bridge-profiles
scripts/busierbox-server --inspect-bridge-profile lab-http
scripts/busierbox-server --transport bridge --bridge-profile lab-http
```

Profiles can also carry explicit multi-hop chain metadata. Repeat `--bridge-hop`
when saving the profile:

```sh
scripts/busierbox-server \
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

In line-mode TUI, action `17` opens bridge profile management. It lists saved
profiles, can create or update a profile from prompts, inspect a profile, start
or stop the bridge listener, and delete a profile. Each TUI path prints the
equivalent `scripts/busierbox-server ...` command before or after applying the
action.

Profiles live in `bridge-profiles.json` under the operator session directory by
default. Each record includes the listen endpoint, destination endpoint,
explicit hops, hop count, multi-hop flag, optional target id/label, purpose,
notes, state, route path, start/stop commands, and whether the profile requires
a target to be online. `--json-status` exposes `bridge_profiles` plus indexes
such as `bridge_profiles_by_name`, `bridge_profiles_by_target_id`,
`bridge_profiles_by_current_state`, `bridge_profiles_by_active`,
`bridge_profiles_by_multi_hop`, `bridge_profiles_by_hop_count`, and
`bridge_profiles_by_route_path` for TUI and automation clients. The simple
direct `--bridge-*` flags remain the easy one-hop path.

When `--bridge-profile` is selected for other operator workflows, generated
target commands are route-aware. File fetch/upload commands and survey bootstrap
commands use the profile's target-visible first hop, while their status records
carry `route_kind`, `bridge_profile`, `bridge_route_path`, and `target_route`
metadata so a TUI can show whether the operator is using a direct or bridged
route.
