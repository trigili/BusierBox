# BusierBox

BusierBox is a reproducible embedded Linux debug-toolkit builder and runtime launcher. It is designed for old and modern embedded Linux targets where you want to upload one small supervisor binary, survey the target, extract a known payload when useful, and run familiar debug tools from that payload.

BusierBox is not a BusyBox replacement and is not a BusyBox fork. BusierBox manages survey, environment repair, payload extraction, and dispatch. BusyBox provides standard Unix utilities such as `sh`, `cp`, `dd`, `mount`, `ps`, `nc`, and `tar`.

## Architecture

The core binary stays small and static-first:

```sh
./busierbox survey
./busierbox envfix
./busierbox extract
./busierbox list
./busierbox config-info
```

Everything else is payload dispatch:

```sh
./busierbox sh
./busierbox cp a b
./busierbox dd if=/dev/mtd0 of=flash.bin bs=64k
./busierbox nc --help
./busierbox tmux
./busierbox strace ...
./busierbox gdbserver ...
```

Standard Unix tools execute through `payload/bin/busybox`:

```text
busierbox cp a b -> payload/bin/busybox cp a b
busierbox sh     -> payload/bin/busybox sh
```

Heavy tools execute directly from the extracted payload:

```text
busierbox tmux      -> payload/bin/tmux
busierbox strace    -> payload/bin/strace
busierbox gdbserver -> payload/bin/gdbserver
busierbox dropbear  -> payload/bin/dropbear
busierbox curl      -> payload/bin/curl
```

The current implementation stages placeholder launchers for heavy tools. Full tmux, strace, gdbserver, dropbear, and curl builds are future Tier 2 payload work.

## Layout

```text
buildroot/configs/       target Buildroot defconfigs
buildroot/external/      BusierBox Buildroot external tree
payloads/profiles/       target metadata used by payload packaging
payloads/dotfiles/       default .profile, .zshrc, .tmux.conf, .gdbinit
runtime/payload/         staged payload tree
runtime/payload/bin/     BusyBox and future tool binaries
runtime/payload/lib/     bundled shared libraries when static builds are unavailable
runtime/payload/home/    payload HOME
dist/busierbox-<target>  self-extracting target-specific artifact
dist/busierbox           native convenience alias, when native is packaged
dist/payload-<target>.*  optional payload archives/debug artifacts
```

Generated binaries, payload archives, local rootfs images, and test artifacts are ignored by git.

## Build

For fast native development, initialize the BusyBox submodule if needed:

```sh
git submodule update --init third_party/busybox
```

Build the supervisor:

```sh
make
```

Build native BusyBox:

```sh
make busybox
```

Configure targets and package artifacts:

```sh
make menuconfig
make package
ls dist/busierbox-*
```

`make package` reads `configs/busierbox.conf` and builds one artifact per selected `BB_TARGETS` entry. For example:

```text
BB_TARGETS="native x86_64-linux-current-musl armv7-linux-3.x-musl mipsel-linux-2.6-uclibc"
```

produces target-named outputs where supported:

```text
dist/busierbox-native
dist/busierbox-armv7-linux-3.x-musl
dist/busierbox-mipsel-linux-2.6-uclibc
```

Each `dist/busierbox-<target>` is a self-extracting binary for one target. It contains a BusierBox core built for that target plus a payload archive built for that same target. These are not multi-architecture binaries, and packaging must not reuse a native core for a foreign payload.

Convenience commands:

```sh
make package-native
make package TARGET=native
make package TARGET=mipsel-linux-2.6-uclibc
make package-all
```

For backwards compatibility, packaging `native` also writes `dist/busierbox` as a convenience copy of `dist/busierbox-native`.

Buildroot-backed targets use the pinned Buildroot source from `manifests/sources.lock.json`:

```sh
make fetch-sources
make package TARGET=mipsel-linux-2.6-uclibc
make package TARGET=armv7-linux-3.x-musl
```

Buildroot builds the cross toolchain and BusyBox, stages `runtime/payload/bin/busybox`, copies default dotfiles into `runtime/payload/home`, permits bundled shared libraries in `runtime/payload/lib` when a fully static payload is unavailable, writes `runtime/payload/manifest.json`, creates ustar-compatible payload archives, builds the BusierBox core with the Buildroot cross compiler, embeds the target payload, and writes `dist/busierbox-<target>.sha256`.

Known target metadata lives in `targets/profiles.json`. Currently supported profiles are `native`, `armv7-linux-3.x-musl`, and `mipsel-linux-2.6-uclibc`. Other listed profiles are scaffold entries until their payload profile and Buildroot defconfig are added. Strict packaging is the default: scaffold or unsupported selections fail clearly. Use `STRICT=0 make package` to skip scaffold entries and print a summary.

The custom tuple UI records intent in `configs/busierbox.conf`, but arbitrary backend generation is future work. When enabled, packaging includes the generated custom target name in the plan and then fails or skips clearly instead of pretending it was built.

Run smoke tests:

```sh
make smoke-test
```

The build attempts static linking for BusierBox and BusyBox. If a payload tool cannot be built fully static, the intended fallback is to bundle its required shared libraries in `runtime/payload/lib` and set `LD_LIBRARY_PATH` when dispatching payload tools. The build should print warnings rather than silently producing a broken payload.

## Runtime

Survey a target:

```sh
./busierbox survey
./busierbox survey --json > survey.json
```

Repair a constrained shell environment:

```sh
eval "$(./busierbox envfix)"
```

Extract the payload:

```sh
./busierbox extract
```

Extraction searches writable executable runtime locations:

- `./.busierbox`
- `/tmp/busierbox-$uid`
- `/var/tmp/busierbox-$uid`
- `/dev/shm/busierbox-$uid`

It avoids visible `noexec` mounts when `/proc/mounts` is readable, writes a payload `VERSION`, and reuses an existing payload when the version matches. `./busierbox clean` removes the local `./.busierbox` extraction.

Extraction uses a lock directory, unpacks into a temporary directory, validates the result, and then atomically renames it into place. Interrupted extractions clean up their temporary directory where practical.

When launching payload tools BusierBox sets:

- `BUSIERBOX_PAYLOAD_DIR`
- `PATH`
- `HOME`
- `TERM` fallback
- `LD_LIBRARY_PATH` when `payload/lib` exists
- `ZDOTDIR` when payload home exists

`./busierbox config-info` reports the BusierBox build, extraction status, payload directory, payload hash, BusyBox dispatch status, and the payload manifest summary when available.

## Tiers

Tier 0: BusierBox supervisor.

- `survey`
- `envfix`
- `extract`
- `clean`
- `list`
- `config-info`
- payload launcher

Tier 1: BusyBox payload.

- `ash`/`sh`
- coreutils-style file tools
- `tar`/`gzip`
- `ps`/`mount`/`df`
- lightweight networking tools such as `nc` and `wget`

Tier 2: heavy debug payloads.

- `tmux`
- `strace`
- `gdbserver`
- `dropbear`
- `curl`
- additional target-specific tools

Tier 2 should stay optional and Buildroot-friendly.

## QEMU User Validation

`make test-qemu-user` copies only the selected `dist/busierbox-<target>` self-extracting binary into per-target artifact directories, runs `extract`, dispatches `sh`, `cp`, `dd`, `nc`, captures `survey.json`, captures `config-info`, and validates survey JSON. Missing qemu interpreters or missing target artifacts are reported as skips.

The primary Buildroot-backed target profile is `mipsel-linux-2.6-uclibc`; the secondary supported profile is `armv7-linux-3.x-musl`.

## Offline SDK Model

The repository contains build logic, manifests, patches, source pins, and small supervisor code. Large source caches, toolchains, and generated payload archives belong in release artifacts, not in the source tree.

All third-party sources should be pinned by version and SHA-256 in `manifests/sources.lock.json` before they become required for reproducible offline builds.
