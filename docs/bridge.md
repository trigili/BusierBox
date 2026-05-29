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
- `--one-shot` exits after one bridged connection, matching other listener
  workflows.

The bridge does not authenticate or inspect the forwarded protocol. Bind it to
the narrowest practical listener address and use existing network controls when
exposing it beyond a local lab interface.
