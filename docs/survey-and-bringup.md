# Survey And Bring-Up

BusierBox has two survey paths:

- `busierbox survey --json` runs the native supervisor probe.
- `busierbox survey --shell-script` prints a portable `/bin/sh` probe that can run on targets where a native artifact is not ready yet.

The shell survey exists because a working native BusierBox binary only proves the artifact is close enough to execute. The next question is operational: where can BusierBox safely write, whether `/tmp` is executable, which tools already exist, what libc/kernel hints are visible, and whether a no-extraction workflow is safer.

Safe defaults:

- no external writes by default
- no zero-arg network autorun by default
- passive survey before reverse access
- `./.busierbox` preferred when the current directory is writable
- `/tmp/.busierbox` only when the current directory is not suitable

Example workflow:

```sh
make package TARGET=glinet-mt7621-openwrt-musl
scripts/busierbox-bringup --host root@192.168.8.1 --operator-host auto
```

The bring-up script creates `local/bringup-runs/<timestamp>/`, builds a survey artifact, transfers it under `/tmp/busierbox-bringup-<timestamp>/`, captures `survey --json` and `config-info`, runs `scripts/config-from-survey`, and writes `recommended.conf` plus `summary.json`.

Useful commands:

```sh
busierbox survey --json --shell-probe
busierbox survey --shell-script
busierbox survey --write-shell-script /tmp/busierbox-survey.sh
scripts/config-from-survey --format shell survey.json
scripts/config-from-survey --format json survey.json
scripts/config-from-survey --write-config local/recommended.conf survey.json
```

`scripts/config-from-survey` is conservative. It emits comments for uncertainty, avoids external writes unless `--allow-external-writes` is set, and keeps `BB_ZERO_ARG_MODE="help"` unless `--allow-network-autorun` is explicitly requested.
