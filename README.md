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
buildroot/configs/       checked-in Buildroot defconfigs
buildroot/generated-configs/ generated tuple Buildroot defconfigs
buildroot/external/      BusierBox Buildroot external tree
targets/presets.json     preset templates that populate target tuples
payloads/profiles/       checked-in target metadata used by payload packaging
payloads/generated-profiles/ generated tuple payload metadata
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

Configure the active target tuple and package one artifact:

```sh
make menuconfig
make package
ls dist/busierbox-*
```

`make package` reads the active tuple fields in `configs/busierbox.conf`, generates Buildroot backend files when needed, and builds one target-specific artifact. Presets are convenience templates that populate tuple fields; the tuple is the source of truth.

```text
BB_TARGET_ARCH="mipsel"
BB_TARGET_ENDIAN="little"
BB_TARGET_CPU="mips32r2-24kc"
BB_TARGET_ABI="default"
BB_TARGET_LIBC="musl"
BB_KERNEL_FLOOR="4.x"
BB_STATIC_POLICY="static-preferred"
BB_PAYLOAD_TIER="debug"
```

produces:

```text
dist/busierbox-mipsel-linux-4.x-musl
```

Each `dist/busierbox-<target>` is a self-extracting binary for one target. It contains a BusierBox core built for that target plus a payload archive built for that same target. These are not multi-architecture binaries, and packaging must not reuse a native core for a foreign payload.

Convenience commands:

```sh
make package-native
make package TARGET=native
make package TARGET=glinet-mt7621-openwrt-musl
make package-all-presets
```

For backwards compatibility, packaging `native` also writes `dist/busierbox` as a convenience copy of `dist/busierbox-native`.

Buildroot-backed targets use the pinned Buildroot source from `manifests/sources.lock.json`:

```sh
make fetch-sources
make package
make package TARGET=armv7-linux-3.x-musl
```

For generated tuples, `scripts/gen-buildroot-defconfig` writes:

```text
buildroot/generated-configs/<target>_defconfig
payloads/generated-profiles/<target>.mk
```

These generated paths are ignored by git. Buildroot then builds the cross toolchain and BusyBox, stages `runtime/payload/bin/busybox`, discovers the actual installed BusyBox applets from the target rootfs, stages only real heavy-tool binaries that were built, writes `runtime/payload/manifest.json`, creates ustar-compatible payload archives, builds the BusierBox core with the Buildroot cross compiler, embeds the target payload, and writes `dist/busierbox-<target>.sha256`.

The payload manifest separates intent from reality:

- `requested_payload_tools`: tools selected in config/menuconfig
- `built_payload_tools`: requested tools for which Buildroot or the host produced binaries
- `staged_payload_tools`: executable tools copied into `payload/bin`
- `missing_payload_tools`: requested tools that were not staged
- `busybox_applets`: applets actually discovered in the staged BusyBox payload

BusierBox generates its advertised dispatch lists from `runtime/payload/busybox-applets.txt` and `runtime/payload/staged-tools.txt`. It does not advertise requested-but-missing tools, and missing heavy tools are recorded under the manifest plus `payload/share/busierbox/missing-tools.txt` instead of placeholder executables.

Supported generated tuple families currently include `mipsel`/`mips` with `musl` or `uclibc`, and `armv7`, `aarch64`, `x86_64`, and `i386` with `musl`. Unsupported combinations fail clearly during target resolution or defconfig generation.

GL.iNet/OpenWrt-ish MIPS little-endian musl example:

```sh
make menuconfig
# Target Configuration
#   Preset profiles -> GL.iNet MT7621/OpenWrt musl
# or manually:
#   arch=mipsel
#   cpu=mips32r2-24kc
#   endian=little
#   libc=musl
#   kernel_floor=4.x

make fetch-sources
make package VERIFY=1
scripts/inspect-artifact dist/busierbox-mipsel-linux-4.x-musl
scripts/verify-artifact dist/busierbox-mipsel-linux-4.x-musl
scp dist/busierbox-mipsel-linux-4.x-musl root@router:/tmp/busierbox
ssh root@router
chmod +x /tmp/busierbox
/tmp/busierbox doctor
/tmp/busierbox list
/tmp/busierbox survey
/tmp/busierbox extract
/tmp/busierbox sh
```

Tool compatibility metadata lives in `payloads/tool-compat.json`. Menuconfig shows warnings for selected heavy tools such as `tmux`, `strace`, `gdbserver`, `dropbear`, `curl`, and `zsh`; it does not hard-block uncertain cases. Generated Buildroot defconfigs enable supported package symbols for selected heavy tools (`strace`, `libcurl` with the `curl` binary, `dropbear`, `zsh`, `tmux`, and `gdbserver`). If Buildroot drops a package due to dependencies or the binary cannot be found after the build, the tool is listed as missing and is not dispatchable.

Artifact inspection and verification:

```sh
scripts/inspect-artifact dist/busierbox-native
scripts/verify-artifact dist/busierbox-native
make verify-artifact TARGET=native
VERIFY=1 make package TARGET=native
```

`scripts/inspect-artifact` parses the embedded payload trailer and manifest without executing the target binary. `scripts/verify-artifact` also executes the artifact when native or when qemu-user is available; otherwise it performs non-execution inspection and skips execution clearly. Verification copies only the self-extracting artifact to a temp directory, runs `list`, `config-info`, `doctor`, `extract`, `sh`, and help probes for advertised payload commands.

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

`./busierbox list --plain` prints script-friendly command rows such as `busybox sh` and `tool strace`. `./busierbox list --json` prints the compiled native, BusyBox, and staged-tool command lists.

`./busierbox doctor` reports embedded payload presence, format, size, hash status, extraction status, payload directory, manifest presence, BusyBox presence, BusyBox applet count, staged tools, missing requested tools, candidate extraction health, `/dev/pts`, and a conservative ptrace status.

`./busierbox config-info` reports the BusierBox build, extraction status, payload directory, payload hash, BusyBox dispatch status, and the payload manifest summary when available.

## Tiers

Tier 0: BusierBox supervisor.

- `survey`
- `envfix`
- `extract`
- `clean`
- `list`
- `config-info`
- `doctor`
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

`make test-qemu-user` copies only the selected `dist/busierbox-<target>` self-extracting binary into per-target artifact directories, runs `extract`, dispatches common applets, captures `survey.json`, captures `config-info`, and validates survey JSON. Missing qemu interpreters or missing target artifacts are reported as skips. `scripts/verify-artifact` is the stricter packaging-time check for advertised command reality; it catches commands that are listed but not dispatchable.

The primary generated OpenWrt-style target is `mipsel-linux-4.x-musl`. Legacy `mipsel-linux-2.6-uclibc` and ARMv7 musl remain available through presets/templates.

## Offline SDK Model

The repository contains build logic, manifests, patches, source pins, and small supervisor code. Large source caches, toolchains, and generated payload archives belong in release artifacts, not in the source tree.

All third-party sources should be pinned by version and SHA-256 in `manifests/sources.lock.json` before they become required for reproducible offline builds.
