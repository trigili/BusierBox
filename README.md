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
third_party/busybox/     upstream BusyBox submodule
payloads/                future per-tool payload recipes/hooks
runtime/payload/         staged payload tree
runtime/payload/bin/     BusyBox and future tool binaries
runtime/payload/lib/     bundled shared libraries when static builds are unavailable
runtime/payload/home/    payload HOME with .profile, .tmux.conf, .gdbinit
dist/busierbox           BusierBox supervisor
dist/payload.tar.gz      runtime payload archive
```

Generated binaries, payload archives, local rootfs images, and test artifacts are ignored by git.

## Build

Initialize the BusyBox submodule if needed:

```sh
git submodule update --init third_party/busybox
```

Build the supervisor:

```sh
make
```

Build BusyBox:

```sh
make busybox
```

Stage and package the payload:

```sh
make payload
```

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

When launching payload tools BusierBox sets:

- `BUSIERBOX_PAYLOAD_DIR`
- `PATH`
- `HOME`
- `TERM` fallback
- `LD_LIBRARY_PATH` when `payload/lib` exists

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

## Offline SDK Model

The repository contains build logic, manifests, patches, source pins, and small supervisor code. Large source caches, toolchains, and generated payload archives belong in release artifacts, not in the source tree.

All third-party sources should be pinned by version and SHA-256 in `manifests/sources.lock.json` before they become required for reproducible offline builds.

