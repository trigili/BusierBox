# Build Matrix

`scripts/lib/build-matrix` batches griTTYkit builds across target presets, payload
presets, and payload archive formats. It writes each run under
`local/matrix-runs/<timestamp>/` by default and records a machine-readable
`summary.json`.

List available dimensions:

```sh
scripts/lib/build-matrix --list-targets
scripts/lib/build-matrix --list-payloads
```

Preview a matrix without building:

```sh
scripts/lib/build-matrix \
  --targets glinet-mt7621-openwrt-musl,aarch64-linux-4.x-musl \
  --payload-presets survey-core,builtin-core-shell,full-debug \
  --formats tgz \
  --dry-run
```

Run a small native matrix:

```sh
scripts/lib/build-matrix --targets native --payload-presets survey-core,default --formats tgz
```

Run the standing compatibility gate:

```sh
scripts/lib/build-matrix \
  --matrix tests/matrix/compatibility-ci.json \
  --fail-fast \
  --run-dir local/matrix-runs/compatibility-ci
```

`tests/matrix/compatibility-ci.json` is the pre-release/CI-style compatibility
matrix. It is intentionally smaller than `release-full.json`, but covers legacy
uClibc, musl, MIPS big/little endian, ARMv7, AArch64, current x86_64, and the
`survey-core`, `default`, and `ssh-operator` payload presets. Normal
`make smoke-test` dry-runs this matrix through
`tests/smoke/compatibility-matrix.sh` so drift in the standing gate is caught
without rebuilding every cross artifact.

For targeted uClibc regressions, run:

```sh
scripts/lib/build-matrix \
  --matrix tests/matrix/release-uclibc-fix.json \
  --fail-fast \
  --run-dir local/matrix-runs/uclibc-regression
```

For full release coverage, run `make release-full` or invoke
`scripts/lib/build-matrix --matrix tests/matrix/release-full.json` directly.

The script generates per-job configs under:

```text
local/matrix-runs/<timestamp>/configs/
```

Built artifacts are copied to:

```text
local/matrix-runs/<timestamp>/artifacts/
```

Each summary job records requested target, resolved target, payload preset,
format, generated config, command, log path, status, artifact path, size, and
sha256 when a build passes. The resolved target is used for artifact lookup, so
aliases and generated target presets still copy the correct output. Failures are
recorded and the matrix continues by default. Use `--fail-fast` to stop after
the first failure.

## Matrix JSON

```json
{
  "targets": ["glinet-mt7621-openwrt-musl", "aarch64-linux-4.x-musl"],
  "payload_presets": ["survey-core", "builtin-core-shell"],
  "formats": ["tgz"],
  "variants": {
    "operator": {
      "payload_preset": "ssh-operator",
      "GRIT_ZERO_ARG_MODE": "help"
    }
  }
}
```

Run it with:

```sh
scripts/lib/build-matrix --matrix configs/matrix/example.json --dry-run
```

Variant keys that are not `target`, `targets`, `payload`, `payloads`,
`payload_preset`, `payload_presets`, `format`, or `formats` are appended to the
generated config.

The older `payloads` key and `--payloads` flag remain accepted as aliases for
payload presets; release-style matrices should prefer `payload_presets`.

## Jobs And Offline Flags

`--jobs N` is accepted for CLI compatibility, but builds are currently
serialized to avoid shared Buildroot output collisions. For offline/enclave
workflows, the matrix script also accepts:

```sh
scripts/lib/build-matrix --offline --mirror-dir local/source-mirror --dry-run
```

That exports `GRIT_OFFLINE=1`, `GRIT_MIRROR_DIR`, and
`BUILDROOT_DL_DIR=<mirror>/buildroot-dl` to each build command. Non-dry-run
offline builds run `scripts/lib/check-offline-readiness` before starting jobs. Use
`--strict-offline` to require a complete mirror manifest for the selected matrix,
or `--skip-offline-preflight` when intentionally debugging an incomplete mirror.
Full mirror population and readiness checks are described in
[offline-enclave.md](offline-enclave.md).
