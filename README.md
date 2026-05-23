# BusierBox

BusierBox is a reproducible embedded Linux debug-toolkit builder. Its goal is to produce target-specific, single-file, mostly-static `busierbox` binaries for old and modern embedded Linux systems with as few runtime assumptions as possible.

This repository is the build logic and small native core. Large third-party sources, toolchains, and release caches belong in offline SDK artifacts, not in the primary source repository.

## What This Is Not

BusierBox is not a BusyBox fork. It does not import BusyBox source, config, or applet implementations. BusyBox is a compact Unix userland. BusierBox is a curated debugging environment inspired by BusyBox, Buildroot, and crosstool-NG workflows:

- BusyBox-style multicall runtime UX.
- Buildroot-style source fetching and reproducible cache handling.
- crosstool-NG-style attention to pinned toolchains and target ABI constraints.

The long-term output is a small static core plus optional target-specific debug tools. The current MVP implements a practical Tier 0 native-host binary and keeps the source layout ready for target-specific cross builds.

## Target Model

Future releases are expected to build artifacts such as:

```sh
dist/busierbox-mipsel-linux-2.6
dist/busierbox-armv5-linux-2.6
dist/busierbox-armv7-linux-3.x
dist/busierbox-aarch64-linux-4.x
```

The runtime model is a static multicall binary:

```sh
./busierbox sh
./busierbox survey
./busierbox survey --json
./busierbox envfix
./busierbox nc HOST PORT
./busierbox http get http://host/path
./busierbox serve -p 8080 .
```

Tier 0 applets must not depend on `/tmp`. A later tier may add optional self-extracting heavy tools, but the core applets should remain useful when the filesystem is hostile or minimal.

## Quick Start

```sh
make
./dist/busierbox list
./dist/busierbox survey
./dist/busierbox survey --json
./dist/busierbox envfix
./dist/busierbox sh
```

`make` builds `dist/busierbox` for the host. It first attempts static linking and falls back to a normal host binary if static linking is unavailable.

The MVP `sh` applet is a small interactive loop. It supports `exit`, internal applet dispatch, and `execvp` fallback. It does not implement job control, pipes, quoting, globbing, variables, or scripting.

## Online Source Flow

All third-party sources must be pinned in [manifests/sources.lock.json](manifests/sources.lock.json) by:

- `name`
- `version`
- `url`
- `sha256`
- `filename`

Fetch and verify:

```sh
make fetch-sources
make verify-sources
```

The MVP manifest is intentionally empty because the current native core has no third-party source dependency. Add entries before introducing external code or toolchains.

## Offline SDK Flow

Create an offline cache release:

```sh
make offline-pack
```

This writes one of:

```sh
dist/busierbox-sdk-YYYYMMDD.tar.zst
dist/busierbox-sdk-YYYYMMDD.tar.gz
```

Unpack a cache on an offline machine:

```sh
scripts/offline-unpack dist/busierbox-sdk-YYYYMMDD.tar.gz
make verify-sources
make build
```

Release philosophy:

- The repository contains build logic, manifests, patches, and the small BusierBox core.
- Release artifacts contain frozen source caches and, later, pinned toolchains.
- Reproducibility comes from locked versions, locked hashes, and offline-verifiable caches.

## Configs

Example configs live in [configs](configs). For the MVP they document intended target triples and kernel floors. Native build selection is intentionally simple:

```sh
make CONFIG=configs/native-linux.example
```

Cross-toolchain support is a planned extension.

## Roadmap Tiers

Tier 0: no-extraction static core applets.

- `survey`
- `envfix`
- `sh`
- embedded triage and byte-moving helpers
- plain TCP and plain HTTP transfer helpers

Tier 1: integrated static debug tools.

- `strace`
- `gdbserver`
- `dropbear`
- `tcpdump`
- target-specific network and filesystem diagnostics

Tier 2: optional self-extracting heavy tools.

- `zsh`
- `tmux`
- `vim`
- other tools that are too large or stateful for the core binary

Tier 2 must remain optional. Tier 0 should stay usable without writing to `/tmp`.

## Current Applets

Tier 0 applets currently compiled into `dist/busierbox`:

```text
list sh survey envfix nc http serve cat ls hexdump strings sha256sum base64
dd uname id which readlink stat df free ps mount env cp mv rm mkdir chmod
touch grep-lite sleep tee
```

Every applet supports `--help`. These are intentionally small embedded-focused applets, not full GNU/coreutils-compatible replacements.

`survey` prints embedded triage information and supports JSON:

- `uname`
- architecture, endianness, pointer width, and kernel version
- uid/euid/gid/egid
- current working directory
- `PATH`, `HOME`, and `TERM`
- mount summary and visible `noexec` flags when readable
- writable/executable status and free bytes for `.`, `/tmp`, `/var/tmp`, `/dev/shm`, and `/var`
- whether `/proc` exists
- whether `/dev/pts` exists
- process count, memory summary, and network interface names when `/proc` is readable
- conservative extraction/debug recommendations

`envfix` prints shell commands for repairing common constrained environments. It does not modify the system unless passed `--apply`.

`http` is a tiny plain-HTTP client, not curl. It supports:

```sh
./dist/busierbox http get http://host[:port]/path [-o FILE]
./dist/busierbox http post http://host[:port]/path --file FILE
./dist/busierbox http post http://host[:port]/path --data STRING
```

HTTPS, redirects, proxies, cookies, and full curl behavior are intentionally out of scope for Tier 0.

`serve` is a tiny one-connection-at-a-time HTTP file server:

```sh
./dist/busierbox serve -p 8080 .
```

It serves regular files and simple directory listings, and rejects paths containing `..`.

## Examples

Survey a target and save JSON:

```sh
./busierbox survey
./busierbox survey --json > survey.json
```

Send survey JSON to a waiting TCP listener:

```sh
./busierbox survey --json | ./busierbox nc 192.0.2.10 9000
```

POST survey JSON to a plain HTTP collector:

```sh
./busierbox survey --json > survey.json
./busierbox http post http://192.0.2.10:8080/upload --file survey.json
```

Serve the current filesystem subtree over HTTP:

```sh
./busierbox serve -p 8080 .
```

Repair a constrained shell environment:

```sh
eval "$(./busierbox envfix)"
./busierbox envfix --apply
```

Future Tier 1 payload work may add target-specific `tmux`, `strace`, `gdbserver`, `dropbear`, `tcpdump`, and similar tools through pinned source/cache releases instead of vendoring large trees in this repo.
