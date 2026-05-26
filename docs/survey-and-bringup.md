# Survey And Bring-Up

BusierBox has two survey paths:

- `busierbox survey --json` runs the native supervisor probe.
- `busierbox survey --shell-script` prints a portable `/bin/sh` probe that can run on targets where a native artifact is not ready yet.

The shell survey exists because a working native BusierBox binary only proves the artifact is close enough to execute. The next question is operational: where can BusierBox safely write, whether `/tmp` is executable, which tools already exist, what libc/kernel hints are visible, and whether a no-extraction workflow is safer.

The generated shell probe is POSIX-ish and avoids required Python, Perl, awk,
sed, grep, or coreutils dependencies. It uses common target commands only when
they are present and writes probe files only under
`BUSIERBOX_SURVEY_PROBE_DIR` or its chosen temporary probe directory. Output is
conservative JSON: strings that cannot be safely escaped by plain shell are
reported as `unknown` rather than risking invalid JSON.

Safe defaults:

- no external writes by default
- no zero-arg network autorun by default
- passive survey before reverse access
- release bundles can configure operator host/ports later with trailer helpers
  without changing target tuple compatibility or payload contents
- `./.busierbox` preferred when the current directory is writable
- `/tmp/.busierbox` only when the current directory is not suitable

Example workflow:

```sh
make package TARGET=glinet-mt7621-openwrt-musl
scripts/busierbox-bringup --host root@192.168.8.1 --operator-host auto
```

The bring-up script creates `local/bringup-runs/<timestamp>/`, builds a survey artifact, transfers it under `/tmp/busierbox-bringup-<timestamp>/`, captures `survey --json` and `config-info`, runs `scripts/config-from-survey`, and writes `recommended.conf` plus `summary.json`.

See [bringup.md](bringup.md) for the full command reference and safety model.

Useful commands:

```sh
busierbox survey --json --shell-probe
busierbox survey --shell-script
BUSIERBOX_SURVEY_PROBE_DIR=/tmp/bbx-probe /bin/sh ./busierbox-survey.sh
busierbox survey --write-shell-script /tmp/busierbox-survey.sh
scripts/config-from-survey --format shell survey.json
scripts/config-from-survey --format json survey.json
scripts/config-from-survey --write-config local/recommended.conf survey.json
```

`scripts/config-from-survey` is conservative. It emits comments for uncertainty, avoids external writes unless `--allow-external-writes` is set, and keeps `BB_ZERO_ARG_MODE="help"` unless `--allow-network-autorun` is explicitly requested.

For target-side debugging, prefer the provider-based gdbserver workflow in
[gdbserver-workflow.md](gdbserver-workflow.md). Buildroot gdbserver is kept where
it works, but local drop-ins are the preferred low-friction path for tuples such
as mipsel/musl where static Buildroot GDB is known to fail.
