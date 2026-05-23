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
dist/busierbox           BusierBox supervisor
dist/payload.tar.gz      runtime payload archive
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

Stage and package the payload:

```sh
make payload
```

Buildroot-backed target payloads use the pinned Buildroot source from `manifests/sources.lock.json`:

```sh
make fetch-sources
make buildroot
make payload TARGET=mipsel-linux-2.6-uclibc
```

The optional ARMv7 profile is:

```sh
make payload TARGET=armv7-linux-3.x-musl
```

Buildroot builds the cross toolchain and BusyBox, stages `runtime/payload/bin/busybox`, copies default dotfiles into `runtime/payload/home`, permits bundled shared libraries in `runtime/payload/lib` when a fully static payload is unavailable, writes `runtime/payload/manifest.json`, and creates `dist/payload.tar.gz` plus `dist/payload.tar.gz.sha256`.

Build both:

```sh
make package
```

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

`make test-qemu-user` copies `dist/busierbox` and `dist/payload.tar.gz` into per-target artifact directories, runs `extract`, dispatches `sh`, `cp`, `dd`, `nc`, captures `survey.json`, captures `config-info`, and validates survey JSON. Missing qemu interpreters or missing cross BusierBox binaries are reported as skips.

The primary target profile for this milestone is `mipsel-linux-2.6-uclibc`; the optional secondary profile is `armv7-linux-3.x-musl`.

## Offline SDK Model

The repository contains build logic, manifests, patches, source pins, and small supervisor code. Large source caches, toolchains, and generated payload archives belong in release artifacts, not in the source tree.

All third-party sources should be pinned by version and SHA-256 in `manifests/sources.lock.json` before they become required for reproducible offline builds.
