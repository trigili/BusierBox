# Probe Bootstrap

The first-contact bootstrap workflow is now exposed as the `probe` transport:

```sh
scripts/grit-server \
  --transport probe \
  --listen-host 0.0.0.0 \
  --probe-port 22207 \
  --probe-name probe.sh
```

`scripts/grit-server --transport probe` serves a small architecture-agnostic
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
```

The line-oriented console wraps the same workflow:

```text
grit[all]> probe --start
grit[all]> probe results
grit[all]> probe config --write-config configs/grit.conf
grit[all]> probe serve --start
```

`probe serve --start` stages the matching release artifact and prints target
fetch options. On a target that does not have griTTYkit yet, use the printed
plain `wget` or `curl` command against `/fetch?name=...`, then run the printed
`chmod +x ./grit... && ./grit... --help` hint. On a target that already has
griTTYkit, use the printed `grit fetch ...` command instead.

`probe config` converts the newest probe result into a generated config. The
probe only captures basic platform evidence, so a later full `grit survey push`
can refine the recommendation after a payload is deployed.

When a bridge profile is selected, generated target commands use the bridge's
target-visible route instead of the direct probe listener:

```sh
scripts/grit-server \
  --transport probe \
  --probe-port 22207 \
  --bridge-profile rack-chain
```

Status JSON exposes `probe_workflow_actions`, a stable action catalog for the
current probe route. Records cover inspecting the route, showing the target-side
command, starting the listener, and stopping it. Each record includes the
equivalent `headless_command`, generated `target_command`, direct or bridged
route metadata, current service state, operator readiness fields, a stable
`run_command`, and Enter-key hints for TUI clients.

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
architecture. It only requires `/bin/sh`; upload requires either `wget` or
`curl` on the target.
