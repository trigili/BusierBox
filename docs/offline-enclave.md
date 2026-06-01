# Offline / Enclave Builds

griTTYkit keeps source fetching explicit. Anything required by griTTYkit itself
must be pinned in `manifests/sources.lock.json` with version, URL, filename, and
SHA-256. Buildroot package downloads for selected target and payload jobs are
mirrored by generating the matching Buildroot defconfigs and running Buildroot's
`source` target on the online preparation machine.

## Online Preparation Machine

Install normal build prerequisites, then inspect the release-full matrix:

```sh
git submodule update --init third_party/busybox
make release-full DRY_RUN=1
```

Populate a strict source mirror for the same matrix. This mirror is source-only:
it intentionally does not contain compiled `release-full` artifacts, but it does
include pinned griTTYkit sources, Buildroot package sources for the release-full
matrix, and Buildroot-mapped utility sources for menuconfig choices beyond the
release payload presets.

```sh
make source-mirror
```

Create a transferable source-release tarball:

```sh
make source-release
```

Use dry-run mode when you only want to inspect the planned mirror layout and
Buildroot fetch commands. A dry run does not download files or create a tarball.

```sh
make source-mirror DRY_RUN=1
make source-release DRY_RUN=1
```

The lower-level equivalent is:

```sh
scripts/lib/mirror-sources \
  --matrix tests/matrix/release-full.json \
  --source-only \
  --include-buildroot-packages \
  --all-supported-tools \
  --out dist/source-mirror/full \
  --strict \
  --verify
```

The generated source mirror contains:

```text
full/
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

Copy the repository and source-release archive into the enclave. Unpack the
mirror and verify it before building:

```sh
mkdir -p /mnt/source-mirror
tar -xzf source-full-*.tar.gz -C /mnt/source-mirror
scripts/lib/check-offline-readiness \
  --mirror /mnt/source-mirror/full \
  --matrix tests/matrix/release-full.json \
  --strict
```

Build the binary release from the source mirror:

```sh
export GRIT_OFFLINE=1
export GRIT_MIRROR_DIR=/mnt/source-mirror/full
export BUILDROOT_DL_DIR=/mnt/source-mirror/full/buildroot-dl
make release-full
```

The release build uses these values for each job:

```text
GRIT_OFFLINE=1
GRIT_MIRROR_DIR=/mnt/source-mirror/full
BUILDROOT_DL_DIR=/mnt/source-mirror/full/buildroot-dl
```

The resulting release bundle is the same operator-facing package produced on an
online machine: it contains the generic kernel-era tuple artifacts, payload
preset selectors, `scripts/grit-server`, `scripts/verify-checksums`, and
`scripts/lib/release-self-test`.

## Reporting

Summarize a prepared mirror with:

```sh
scripts/lib/mirror-report dist/source-mirror/full
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
- Missing Buildroot package source: rerun `make source-mirror` online for the
  same `tests/matrix/release-full.json` matrix.
- Buildroot output needs inspection: rerun `scripts/lib/mirror-sources` with
  the lower-level command above and inspect `plans/`, `logs/`, and
  `buildroot-defconfigs/`.
- Host dependency absent: install host compilers and build prerequisites inside
  the enclave before running the matrix.

## Limitations

Buildroot package files are mirrored by executing Buildroot's `source` target for
the generated defconfigs. Packages with dynamic source lists are caught by strict
readiness when the recorded manifest is incomplete or the mirrored files are
missing. User-provided overlay binaries are external inputs and are not
downloaded by `scripts/lib/mirror-sources`.
