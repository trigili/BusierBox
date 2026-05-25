# Build Matrix

`scripts/build-matrix` batches BusierBox builds across target presets, payload
presets, and payload archive formats. It writes each run under
`local/matrix-runs/<timestamp>/` by default and records a machine-readable
`summary.json`.

List available dimensions:

```sh
scripts/build-matrix --list-targets
scripts/build-matrix --list-payloads
```

Preview a matrix without building:

```sh
scripts/build-matrix \
  --targets glinet-mt7621-openwrt-musl,aarch64-linux-4.x-musl \
  --payloads survey-core,builtin-core-shell,full-debug \
  --formats tgz \
  --dry-run
```

Run a small native matrix:

```sh
scripts/build-matrix --targets native --payloads survey-core,default --formats tgz
```

The script generates per-job configs under:

```text
local/matrix-runs/<timestamp>/configs/
```

Built artifacts are copied to:

```text
local/matrix-runs/<timestamp>/artifacts/
```

Each summary job records target, payload preset, format, generated config,
command, log path, status, artifact path, size, and sha256 when a build passes.
Failures are recorded and the matrix continues by default. Use `--fail-fast` to
stop after the first failure.

## Matrix JSON

```json
{
  "targets": ["glinet-mt7621-openwrt-musl", "aarch64-linux-4.x-musl"],
  "payloads": ["survey-core", "builtin-core-shell"],
  "formats": ["tgz"],
  "variants": {
    "operator": {
      "payload_preset": "ssh-operator",
      "BB_ZERO_ARG_MODE": "help"
    }
  }
}
```

Run it with:

```sh
scripts/build-matrix --matrix configs/matrix/example.json --dry-run
```

Variant keys that are not `target`, `targets`, `payload`, `payloads`,
`payload_preset`, `format`, or `formats` are appended to the generated config.

## Jobs And Offline Flags

`--jobs N` is accepted for CLI compatibility, but builds are currently
serialized to avoid shared Buildroot output collisions. For offline/enclave
workflows, the matrix script also accepts:

```sh
scripts/build-matrix --offline --mirror-dir local/source-mirror --dry-run
```

That exports `BUSIERBOX_OFFLINE=1`, `BUSIERBOX_MIRROR_DIR`, and
`BUILDROOT_DL_DIR=<mirror>/buildroot-dl` to each build command. Full mirror
population and readiness checks are described in
[offline-enclave.md](offline-enclave.md).
