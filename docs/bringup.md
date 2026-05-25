# Bringup

`scripts/busierbox-bringup` is a guided onboarding flow for a target that is not
fully characterized yet. It is meant to answer: can a conservative BusierBox
artifact run, what did the target survey report, and what config should be tried
next?

It is different from `scripts/integration-glinet`: bringup is exploratory and
creates a recommendation, while integration is the repeatable validation
harness for known cases.

## What It Does

- Creates `local/bringup-runs/<timestamp>/`.
- Builds a conservative survey artifact unless `--survey-json` is supplied.
- Copies that artifact to `/tmp/busierbox-bringup-<timestamp>/` on the target.
- Runs `./busierbox survey --json` and `./busierbox config-info`.
- Runs `scripts/config-from-survey`.
- Writes `survey.json`, `recommendation.json`, `recommended.conf`, logs, and
  `summary.json`.
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
  --host root@192.0.2.1 \
  --recommend-only \
  --survey-json local/survey.json \
  --target-preset glinet-mt7621-openwrt-musl
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
local/bringup-runs/<timestamp>/
  build.log
  ssh.log
  survey.json
  config-info.out
  recommendation.json
  recommended.conf
  recommended-build.log
  summary.json
```

`summary.json` records the run status, local run directory, remote directory,
host, target preset, payload preset, and paths to the generated recommendation.

## Safety Defaults

The initial survey artifact uses the selected payload preset, defaults to
`survey-core`, forces `BB_RUNTIME_ALLOW_EXTERNAL_WRITES="no"`, and keeps
`BB_ZERO_ARG_MODE="help"`. `scripts/config-from-survey` remains conservative:
it does not enable external writes or network autorun unless explicitly asked.

Use `--keep-remote` only when debugging. Otherwise the remote temp directory is
removed after the survey capture.
