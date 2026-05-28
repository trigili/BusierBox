# Survey And Bring-Up

BusierBox has two survey paths:

- `busierbox survey --json` runs the native supervisor probe.
- `busierbox survey --shell-script` prints a portable `/bin/sh` probe that can run on targets where a native artifact is not ready yet.
- `busierbox reality-test --json` actively checks runtime behavior such as
  writing/executing under the runtime root, forking, spawning `/bin/sh`, opening
  pipes/PTYs, reading `/proc` and `/sys`, binding localhost, and reaching a
  configured operator endpoint.

The shell survey exists because a working native BusierBox binary only proves the artifact is close enough to execute. The next question is operational: where can BusierBox safely write, whether `/tmp` is executable, which tools already exist, what libc/kernel hints are visible, and whether a no-extraction workflow is safer.
`reality-test` complements that passive survey with active checks. It reports
operator upload/fetch checks as skipped unless those side-effecting services are
explicitly configured for the run.
Its JSON also includes `checks_by_name`, `checks_by_status`,
`checks_by_type`, `checks_by_skipped`, `checks_by_available`,
`checks_by_detected`, and `api_collections.checks` metadata with explicit
`count`, `summary_key`, backward-compatible `count_summary_key`, and
`primary_key: name` fields.
Bringup tools and future UIs can jump directly to failed capabilities, skipped
operator checks, unavailable probes, or detected constraints without scraping
the text view.

Operator file-service checks are opt-in because they create target-initiated
network traffic and upload a small probe file:

```sh
busierbox reality-test --json \
  --operator-host 192.0.2.10 --file-port 22204 --no-tls \
  --check-upload --check-fetch reality-fetch.txt
```

`--check-upload` uploads a generated probe file to the receive-only operator
file-service. `--check-fetch REQUEST` performs a staged-file fetch check for the
given request name and URL-encodes it using the same staged fetch semantics as
`busierbox fetch`, so path components and spaces in staged names are supported.
Fetch probing currently requires `--no-tls`; TLS upload probing follows the
artifact's built-in TLS support.

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
busierbox reality-test --json
busierbox reality-test push
scripts/config-from-survey --format shell survey.json
scripts/config-from-survey --format json survey.json
scripts/config-from-survey --format json --reality-json reality.json survey.json
scripts/config-from-survey --write-config local/recommended.conf survey.json
scripts/preset-from-survey --survey survey.json --name glinet-mt1300-lab
scripts/preset-from-survey --survey survey.json --name glinet-mt1300-lab --write-local
scripts/release-find --release-dir dist/releases/lab --survey-json survey.json --reality-json reality.json
```

`scripts/config-from-survey` is conservative. It emits comments for uncertainty, avoids external writes unless `--allow-external-writes` is set, and keeps `BB_ZERO_ARG_MODE="help"` unless `--allow-network-autorun` is explicitly requested.
Shell output includes `# compatibility=...` and `# compatibility_reason: ...`
comments. JSON output includes a `compatibility` object with `schema`, `label`,
and `reasons` so bringup tooling can show the same risk language used by
release selection before a release artifact is chosen.
When `--reality-json` is supplied, failed active runtime checks can downgrade
payload recommendations to `core-only` and add explicit warnings for noexec
temporary storage, read-only root filesystems, broken procfs, or missing ptrace.
When present, `checks_by_name` is used as the primary check lookup and the raw
`checks` list remains the fallback for older reports.

Release bundle `release-find` can combine passive survey facts with
`reality-test` results and report `exact`, `likely`, `heuristic`, `unsafe`, or
`incompatible` compatibility reasons before you choose a larger payload.

`scripts/preset-from-survey` writes reusable target compatibility presets under
`local/presets/targets/`. Those generated presets intentionally contain only
target tuple metadata such as arch, endian, libc, kernel floor, CPU/ABI, static
policy hints, survey provenance, confidence, and review notes. Runtime mode,
payload preset, reverse-shell transport, operator host/ports, zero-arg behavior,
dotfiles, and overlays remain in normal payload/runtime configs. `scripts/resolve-target`
discovers these local presets automatically, so a generated name can be used
with `TARGET=<name>` after review.

For target-side debugging, prefer the provider-based gdbserver workflow in
[gdbserver-workflow.md](gdbserver-workflow.md). Buildroot gdbserver is kept where
it works, but local drop-ins are the preferred low-friction path for tuples such
as mipsel/musl where static Buildroot GDB is known to fail.
