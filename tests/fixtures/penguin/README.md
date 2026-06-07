# Penguin/QEMU Fixtures

The Penguin-backed QEMU tests are meant to be usable from a public checkout
without committing firmware images, root filesystems, qcow files, or vendor
payloads to this repository.

The repository provides the harness. Each user provides their own legal test
fixtures.

## What Is Tracked

Tracked files:

- `tests/integration/release-qemu-penguin`
- `tests/integration/qemu-penguin-image`
- lightweight smoke checks and matrix metadata

Untracked by design:

- firmware images
- extracted firmware root filesystems
- qcow images
- Penguin project outputs
- private rehosting workspaces

## Fixture Contract

The harness expects a Penguin project directory with this shape:

```text
projects/
  archer-a7-us-v5-211022/
    config.yaml
    base/
      fs.tar.gz
    static/
      ArchId.yaml
      KernelVersionFinder.yaml
    static_patches/
      ...
```

`config.yaml` must be a normal Penguin config. The griTTYkit scripts generate a
temporary copy of the project, stage the selected artifact as `/igloo/grit` using
Penguin `static_files`, add an `init.d` drop-in that copies it to `/tmp/grit`
after guest boot setup, and run that generated project. The original fixture is
not modified.

## Legal Setup Options

Use one of these approaches:

1. Use firmware or rootfs images you are legally allowed to analyze.
2. Generate a synthetic router-like rootfs yourself with Buildroot, OpenWrt, or
   another redistributable build system.
3. Use a private fixture archive shared outside this source repository, subject
   to the license terms for the firmware or image.

Do not commit the image files or generated projects here. If a fixture comes
from a vendor download, keep the download step and license acceptance outside
the repo. If you publish a fixture pack separately, include source URLs,
licenses, checksums, and redistribution notes in that pack.

## Local Layout

The default local developer layout is:

```text
local/testing/
  penguin/
    penguin
  rehost/
    projects/
      <project>/
```

That path is optional. Public users can keep fixtures anywhere and point the
harness at them:

```sh
PENGUIN_RUNNER=/path/to/penguin/penguin \
PENGUIN_PROJECT_ROOT=/path/to/rehost/projects \
tests/integration/qemu-penguin-image --project archer-a7-us-v5-211022
```

For a bounded automated run:

```sh
PENGUIN_RUNNER=/path/to/penguin/penguin \
PENGUIN_PROJECT_ROOT=/path/to/rehost/projects \
tests/integration/qemu-penguin-image --project archer-a7-us-v5-211022 --auto --timeout 90
```

To test a specific griTTYkit artifact instead of building the default one:

```sh
PENGUIN_RUNNER=/path/to/penguin/penguin \
PENGUIN_PROJECT_ROOT=/path/to/rehost/projects \
tests/integration/qemu-penguin-image \
  --project archer-a7-us-v5-211022 \
  --grit dist/grit-mips-linux-4.x-uclibc-survey-core-full
```

## Release Harness

The release harness can plan without fixtures:

```sh
tests/integration/release-qemu-penguin
```

With fixtures present, it can build, extract, select an artifact, and run a
real Penguin/QEMU target:

```sh
PENGUIN_RUNNER=/path/to/penguin/penguin \
PENGUIN_PROJECT_ROOT=/path/to/rehost/projects \
GRIT_RELEASE_QEMU_PENGUIN_BUILD=1 \
GRIT_RELEASE_QEMU_PENGUIN_RUN=1 \
PENGUIN_LIMIT=1 \
PENGUIN_TIMEOUT=90 \
RELEASE_TARGETS=mips-linux-4.x-uclibc \
RELEASE_PAYLOAD_PRESETS=survey-core \
RELEASE_FORMATS=tgz \
tests/integration/release-qemu-penguin
```

The default target tuple above matches the known big-endian MIPS 4.x uClibc
fixture used during local validation. For other fixtures, build or pass a
matching artifact with `--grit`.

## Why The Repo Does Not Download Firmware

The tests intentionally avoid automatic vendor firmware downloads. Even when a
firmware image is publicly available, redistribution and automated download
rights can vary by vendor, region, and version. Keeping those assets outside
the source tree avoids accidentally turning the test suite into a firmware
mirror.

For fully public CI, prefer synthetic images generated from redistributable
sources. For private compatibility testing, use local or private artifact
storage and set `PENGUIN_PROJECT_ROOT`/`PENGUIN_RUNNER` in the job environment.
