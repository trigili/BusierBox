# Offline / Enclave Builds

griTTYkit keeps source fetching explicit. Anything required by griTTYkit itself
must be pinned in `manifests/sources.lock.json` with version, URL, filename, and
SHA-256. Buildroot package downloads for selected target and payload jobs are
mirrored by generating the matching Buildroot defconfigs and running Buildroot's
`source` target on the online preparation machine.

## Online Preparation Machine

Install normal build prerequisites, then inspect the selected matrix:

```sh
git submodule update --init third_party/busybox
scripts/lib/build-matrix --matrix configs/matrix/all-supported.json --dry-run
```

Populate a source mirror for the same matrix:

```sh
scripts/lib/mirror-sources \
  --matrix configs/matrix/all-supported.json \
  --out local/source-mirror/all-supported \
  --include-buildroot-packages \
  --verify
```

`--verify` runs strict offline readiness checks after the mirror is written. To
run that check separately:

```sh
scripts/lib/check-offline-readiness \
  --mirror local/source-mirror/all-supported \
  --matrix configs/matrix/all-supported.json \
  --strict
```

Use `--dry-run` with `mirror-sources` when you only want to inspect the planned
mirror layout and Buildroot fetch commands. A dry run does not download files.

Then package the local mirror for transfer:

```sh
tar -C local/source-mirror -czf all-supported-source-mirror.tar.gz all-supported
```

The generated mirror contains:

```text
all-supported/
  grit-sources/
  sources/
  buildroot-dl/
  buildroot-defconfigs/
  plans/
  logs/
  sources.lock.json
  mirror-manifest.json
```

`grit-sources/` is the canonical cache for pinned griTTYkit source files.
`sources/` is retained for compatibility with older offline tooling.
`buildroot-dl/` is passed to Buildroot as `BR2_DL_DIR`.

## Transfer To Enclave

Copy the repository and mirror archive into the enclave. Unpack the mirror and
verify it before building:

```sh
mkdir -p /mnt/source-mirror
tar -xzf all-supported-source-mirror.tar.gz -C /mnt/source-mirror
scripts/lib/check-offline-readiness \
  --mirror /mnt/source-mirror/all-supported \
  --matrix configs/matrix/all-supported.json \
  --strict
```

Build with offline flags:

```sh
GRIT_OFFLINE=1 scripts/lib/build-matrix \
  --matrix configs/matrix/all-supported.json \
  --offline \
  --mirror-dir /mnt/source-mirror/all-supported
```

The matrix script exports these values for each job:

```text
GRIT_OFFLINE=1
GRIT_MIRROR_DIR=/mnt/source-mirror/all-supported
BUILDROOT_DL_DIR=/mnt/source-mirror/all-supported/buildroot-dl
```

For non-dry-run offline builds, `scripts/lib/build-matrix` runs
`scripts/lib/check-offline-readiness` before starting jobs. Add `--strict-offline`
to require a complete mirror manifest with matching matrix coverage. Use
`--skip-offline-preflight` only when deliberately debugging a partially prepared
mirror.

## Reporting

Summarize a prepared mirror with:

```sh
scripts/lib/mirror-report local/source-mirror/all-supported
```

The report includes strict readiness, selected job count, mirrored file count,
total bytes, and any missing or failed fetches. Use `--json` for machine-readable
output.

## Troubleshooting

- Missing lockfile source: run `scripts/lib/check-offline-readiness --mirror <dir>`
  and copy the reported filename into `grit-sources/`, `sources/`, or
  `buildroot-dl/`.
- Hash mismatch: replace the file with the exact locked version; do not update
  the lockfile inside the enclave.
- Missing Buildroot package source: rerun `scripts/lib/mirror-sources` online with
  `--include-buildroot-packages --verify` for the same matrix.
- Buildroot output needs inspection: rerun `scripts/lib/mirror-sources` with
  `--keep-build-dirs`. By default successful temporary Buildroot output
  directories are removed after the package sources are fetched.
- Host dependency absent: install host compilers and build prerequisites inside
  the enclave before running the matrix.

## Limitations

Buildroot package files are mirrored by executing Buildroot's `source` target for
the generated defconfigs. Packages with dynamic source lists are caught by strict
readiness when the recorded manifest is incomplete or the mirrored files are
missing. User-provided overlay binaries are external inputs and are not
downloaded by `scripts/lib/mirror-sources`.
