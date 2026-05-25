# Offline / Enclave Builds

BusierBox keeps source fetching explicit. Anything required by BusierBox itself
must be pinned in `manifests/sources.lock.json` with version, URL, filename, and
SHA-256. Buildroot package downloads for selected payload tools still need to be
available in the Buildroot download cache for a fully offline target build.

## Online Preparation Machine

Install normal build prerequisites, then populate the pinned BusierBox mirror:

```sh
git submodule update --init third_party/busybox
scripts/mirror-sources --out local/source-mirror
scripts/check-offline-readiness --mirror local/source-mirror
```

For a selected matrix, preview the build commands and record why the mirror is
being prepared:

```sh
scripts/mirror-sources \
  --matrix configs/matrix/all-supported.json \
  --out local/source-mirror \
  --dry-run
```

To prepare Buildroot package tarballs for the exact selected defconfigs, run the
matrix once online with `BUILDROOT_DL_DIR` pointed at the mirror cache, or run
the corresponding Buildroot fetch steps for those defconfigs:

```sh
BUILDROOT_DL_DIR=local/source-mirror/buildroot-dl \
  scripts/build-matrix --matrix configs/matrix/all-supported.json
```

Use `--dry-run` before that command when you only want to inspect the planned
build commands. A dry run does not download Buildroot package tarballs.

Then package the local cache for transfer:

```sh
tar -C local -czf source-mirror.tar.gz source-mirror
```

The generated mirror contains:

```text
local/source-mirror/
  sources/
  buildroot-dl/
  sources.lock.json
  mirror-manifest.json
```

## Transfer To Enclave

Copy the repository and mirror archive into the enclave. Unpack the mirror and
verify it before building:

```sh
tar -xzf source-mirror.tar.gz -C local
scripts/check-offline-readiness \
  --mirror local/source-mirror \
  --matrix configs/matrix/all-supported.json
```

Build with offline flags:

```sh
scripts/build-matrix \
  --matrix configs/matrix/all-supported.json \
  --offline \
  --mirror-dir local/source-mirror
```

The matrix script exports:

```text
BUSIERBOX_OFFLINE=1
BUSIERBOX_MIRROR_DIR=local/source-mirror
BUILDROOT_DL_DIR=local/source-mirror/buildroot-dl
```

`scripts/buildroot-build-payload` uses the mirror-provided Buildroot tarball in
offline mode and passes `BR2_DL_DIR` to Buildroot when `BUILDROOT_DL_DIR` is
set.

## Troubleshooting

- Missing source: run `scripts/check-offline-readiness --mirror <dir>` and copy
  the missing filename into `sources/` or `buildroot-dl/`.
- Hash mismatch: replace the file with the exact locked version; do not update
  the lockfile inside the enclave.
- Buildroot tries the network: the selected Buildroot package source is absent
  from `buildroot-dl/`. Populate it on the online preparation machine.
- Host dependency absent: install host compilers and build prerequisites inside
  the enclave before running the matrix.
- Cross-toolchain cache mismatch: remove the affected `buildroot/output/<target>`
  directory and rebuild with the same mirror.

## Current Limitations

`scripts/mirror-sources` covers BusierBox-pinned sources in
`manifests/sources.lock.json`. It does not yet statically enumerate every
Buildroot package tarball implied by every payload/tool selection; those are
validated by Buildroot using `BR2_DL_DIR` for the matrix you actually build.
