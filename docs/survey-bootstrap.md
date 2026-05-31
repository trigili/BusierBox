# Survey Bootstrap

`scripts/grit-server --transport survey-bootstrap` serves a small
architecture-agnostic `/bin/sh` script and accepts the script's result upload.
This is intended for first contact when the operator does not yet know which
griTTYkit artifact to send to the target.

Example:

```sh
scripts/grit-server \
  --transport survey-bootstrap \
  --listen-host 0.0.0.0 \
  --survey-bootstrap-port 22207 \
  --survey-bootstrap-name yourfile.sh
```

The server prints a URL such as:

```text
Survey bootstrap listener. Listening on http://127.0.0.1:22207/yourfile.sh
```

On the target, download and run it with whatever basic tool is available:

```sh
wget -O- http://OPERATOR:22207/yourfile.sh | /bin/sh
```

When a bridge profile is selected, generated target commands use the bridge's
target-visible route instead of the direct survey listener:

```sh
scripts/grit-server \
  --transport survey-bootstrap \
  --survey-bootstrap-port 22207 \
  --bridge-profile rack-chain
```

If `rack-chain` starts at `operator:22206`, the served script posts results
back through `http://OPERATOR:22206/survey-bootstrap/result`, and status JSON
marks the generated survey command with `route_kind=bridge`,
`bridge_profile=rack-chain`, and the profile's `bridge_route_path`.

In line-mode TUI, action `19` previews the exact target command and the
equivalent headless `--transport survey-bootstrap` command. It can also start
the survey bootstrap listener as a workbench-owned service, so quitting the
workbench stops the listener it started.

Status JSON also exposes `survey_bootstrap_workflow_actions`, a stable action
catalog for the current survey bootstrap route. The records cover inspecting the
route, showing the target-side command, starting the listener, and stopping it.
Each record includes the equivalent `headless_command`, the generated
`target_command`, direct or bridged route metadata, current service state,
operator readiness fields, a stable `run_command`, and Enter-key hints for TUI
clients. Operators can run the same records headlessly with
`--run-survey-bootstrap-workflow-action ACTION_OR_NUMBER`; dry runs use
`--survey-bootstrap-workflow-dry-run`, and listener stop requires
`--confirm-survey-bootstrap-workflow-action`.

The script collects `uname -s`, `uname -m`, `uname -r`, word size from
`getconf LONG_BIT` when available, and a simple endian probe using `od` and
`awk` when available. It posts those values back to
`/survey-bootstrap/result` with `wget --post-data` or `curl -d`.

Operator-side records:

- Results are appended to
  `local/operator-session/survey-bootstrap-results.json` unless
  `operator_session_dir` is overridden.
- `--status`, `--json-status`, and `--api-status` include the
  `survey-bootstrap` service.
- Events include `survey_bootstrap_request`, `survey_bootstrap_result`, and
  `survey_bootstrap_error`.

The bootstrap script is not a griTTYkit binary and does not assume a target
architecture. It only requires `/bin/sh`; upload requires either `wget` or
`curl` on the target.
