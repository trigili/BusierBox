# Bringup

`scripts/busierbox-bringup` is a guided onboarding flow for a target that is not
fully characterized yet. It is meant to answer: can a conservative BusierBox
artifact run, what did the target survey report, and what config should be tried
next?

It is different from `scripts/integration-glinet`: bringup is exploratory and
creates a recommendation, while integration is the repeatable validation
harness for known cases.

## What It Does

- Creates `local/bringup-runs/<timestamp>-<pid>/`.
- Builds a conservative survey artifact unless `--survey-json` is supplied.
- Copies that artifact to `/tmp/busierbox-bringup-<timestamp>-<pid>/` on the target.
- Runs `./busierbox survey --json` and `./busierbox config-info`.
- Runs `./busierbox reality-test --json` when the survey artifact includes the
  applet.
- Runs `scripts/config-from-survey`.
- Writes `survey.json`, `recommendation.json`, `recommended.conf`, logs, and
  `summary.json`.
- Can write a local generated target preset from the survey.
- Can ask a release bundle to select a compatible artifact and report the
  compatibility label/reasons.
- Runs a release bundle's `scripts/release-self-test --json` before release
  artifact selection when the helper exists, then records the diagnostics in
  the bringup summary.
- Can print the exact trailer override, operator, target, and staged fetch
  commands to run next.
- Builds the recommended artifact unless stopped with `--survey-only` or
  `--recommend-only`.
- Optionally runs one integration case with `--run-integration CASE`.

## What It Does Not Do

- It does not start `scripts/busierbox-server`.
- It does not start reverse access.
- It does not enable network autorun.
- It does not install persistence.
- It does not write outside the target temp directory unless the generated
  artifact is later run with explicit external-write options.

## Common Commands

Survey a reachable target and build a recommended artifact:

```sh
scripts/busierbox-bringup --host root@192.168.8.1 --operator-host auto
```

Stop after survey and recommendation:

```sh
scripts/busierbox-bringup --host root@192.168.8.1 --survey-only
```

Generate a recommendation from an existing survey without touching a target:

```sh
scripts/busierbox-bringup \
  --recommend-only \
  --survey-json local/survey.json \
  --target-preset glinet-mt7621-openwrt-musl
```

Generate a reusable local target preset from a survey:

```sh
scripts/busierbox-bringup \
  --recommend-only \
  --survey-json local/survey.json \
  --write-target-preset lab-router \
  --json
```

Select a compatible artifact from a release bundle and print the trailer
override command without executing it:

```sh
scripts/busierbox-bringup \
  --recommend-only \
  --survey-json local/survey.json \
  --release-dir dist/releases/smoke \
  --max-compatibility likely \
  --operator-host 192.0.2.10 \
  --configure-trailer
```

Stage the selected release artifact, or `recommended.conf` when no artifact is
available yet, for explicit target-side fetch:

```sh
scripts/busierbox-bringup \
  --recommend-only \
  --survey-json local/survey.json \
  --release-dir dist/releases/smoke \
  --stage-recommended-artifact
```

Preview the local plan only:

```sh
scripts/busierbox-bringup --host root@192.168.8.1 --dry-run
```

Run one integration case after the recommended build:

```sh
scripts/busierbox-bringup \
  --host root@192.168.8.1 \
  --target-preset glinet-mt7621-openwrt-musl \
  --run-integration survey-core
```

## Outputs

Each run writes:

```text
local/bringup-runs/<timestamp>-<pid>/
  build.log
  ssh.log
  survey.json
  reality-test.json
  config-info.out
  recommendation.json
  recommended.conf
  release-find.json
  release-self-test.json
  recommended-build.log
  summary.json
```

`summary.json` records the run status, local run directory, remote directory,
host, target preset, payload preset, generated target preset path, release
selection, maximum compatibility threshold, compatibility label/reasons,
selected artifact provider status, generated trailer command, staged fetch
command, selected artifact Doom WAD metadata, release self-test diagnostics when
a release bundle helper is present, selected artifact release summary metadata,
next operator commands, and next target commands. The local
survey-derived recommendation also carries `recommendation_compatibility` and
the same object under `recommendation.compatibility`; this is separate from the
top-level `compatibility`, which describes the selected release artifact when
release selection is used. When `--write-target-preset` is used, the summary
also includes `recommended_target_preset_summary` with the generated preset's
target tuple, confidence, target-tuple compatibility notes, and survey evidence
used for inference. The JSON also includes normalized
`selected_tool_provider_status_records` and
`selected_doom_wad_records` with lookup maps by provider tool, provider status,
WAD filename, and WAD sha256. It also includes
`next_operator_command_records` and `next_target_command_records` with
side/effect metadata, a combined `next_command_records` list,
`next_command_records_by_side`, `next_command_records_by_service`, and
`next_command_records_by_purpose` lookup maps. Composite maps
`next_command_records_by_side_service` and
`next_command_records_by_service_purpose` let frontends jump directly to
records like `target:file-service` or
`file-service:explicitly fetch operator-staged artifact or config` without
rescanning every command. `command_record_summary` includes operator/target,
networked target action, listener, staged fetch, execution-safety counts, and
booleans that state whether all next commands require explicit operator/target
action. When reality-test JSON is present, `reality_summary` mirrors its check
counts, constraints, `checks_by_name`, `checks_by_status`, `checks_by_type`,
and `api_collections` metadata so consumers can show active probe status
without separately opening `reality-test.json`. The summary also includes
`run_files`, flat `run_file_records`, and
`run_file_summary` records for the local run directory, survey JSON, reality-test JSON, recommendation JSON,
recommended config, generated target preset, release-find result, and
selected/recommended artifacts. Those file records include path, expected kind,
existence, readability, writability, and size so dashboards and audits can
render a bringup run without separately probing the filesystem. Lookup maps
`run_files_by_name`, `run_files_by_path`, `run_files_by_expected_kind`,
`run_files_by_exists`, and `run_files_by_readable` let frontends jump directly
to a generated artifact or group missing/readable files without rescanning the
flat record list. The summary
also preserves `release_self_test_summary` when a release selection is used,
including command-queue token, execution-supported, and
operator-supplied-command execution counters from the selected release bundle.
The summary
publishes `api_collections` metadata with `count`, `summary_key`,
`count_summary_key`, `primary_key`, and index names for `next_command_records`,
`run_file_records`, selected tool provider records, and selected Doom WAD
records. This mirrors the collection/index discovery pattern used by
`scripts/busierbox-server --api-status` and the native JSON applets.
It also includes a `safety_boundary` object that states that bringup does not
enable network autorun, hidden control channels, command queue execution, or
default remote command execution.

## Safety Defaults

The initial survey artifact uses the selected payload preset, defaults to
`survey-core`, forces `BB_RUNTIME_ALLOW_EXTERNAL_WRITES="no"`, and keeps
`BB_ZERO_ARG_MODE="help"`. `scripts/config-from-survey` remains conservative:
it does not enable external writes or network autorun unless explicitly asked.
`--configure-trailer` prints an `scripts/artifact-config set ...` command; it
does not run target-side code. `--stage-recommended-artifact` updates the
operator staged-files index so the target can explicitly run `busierbox fetch`;
it does not start the file-service listener by itself.

Use `--keep-remote` only when debugging. Otherwise the remote temp directory is
removed after the survey capture.
