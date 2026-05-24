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

Heavy tools are only advertised when a real executable was staged into `payload/bin`. Requested tools that cannot be provided remain visible in the payload manifest as missing, with a reason, but do not become placeholder commands.

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
dist/busierbox-<target>-full    self-extracting target-specific artifact
dist/busierbox-<target>-stager  small bootstrap/fetch-full artifact
dist/internal/                  internal payload-less cores when enabled
dist/busierbox                  native convenience alias, when native is packaged
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

Configure the active target tuple and package deployable artifacts:

```sh
make menuconfig
make package
ls dist/busierbox-*
```

`make package` reads the active tuple fields in `configs/busierbox.conf`, generates Buildroot backend files when needed, and builds target-specific outputs. Presets are convenience templates that populate tuple fields; the tuple is the source of truth.

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

produces deployable tiered artifacts:

```text
dist/busierbox-mipsel-linux-4.x-musl-full
dist/busierbox-mipsel-linux-4.x-musl-stager
```

`-full` is the feature-complete self-extracting artifact. It contains a BusierBox core built for that target plus a payload archive built for that same target. `-stager` is intentionally small and identifies itself as a stager; it does not advertise payload tools and provides `fetch-full` to download a full artifact with target `wget` or `curl`. A compatibility copy without the `-full` suffix is still written for existing scripts. Internal payload-less cores are written only under `dist/internal/` when enabled and should not be deployed as normal artifacts.

Artifact output knobs:

```sh
BB_BUILD_FULL="yes"
BB_BUILD_STAGER="yes"
BB_BUILD_INTERNAL_CORE="no"
```

Stager fetch example:

```sh
./busierbox-mipsel-linux-4.x-musl-stager fetch-full http://host/busierbox-mipsel-linux-4.x-musl-full ./busierbox-full --sha256 <hash>
./busierbox-full doctor
```

Callback/connect-back configuration is explicit, visible in `doctor` and `config-info`, and non-persistent by default:

```sh
BB_STAGER_CALLBACK_ENABLE="no"
BB_STAGER_CALLBACK_HOST=""
BB_STAGER_CALLBACK_PORT=""
BB_STAGER_CALLBACK_SHELL="sh"
```

Convenience commands:

```sh
make package-native
make package TARGET=native
make package TARGET=glinet-mt7621-openwrt-musl
make package-all-presets
```

For backwards compatibility, packaging also writes `dist/busierbox-<target>` as a copy of `dist/busierbox-<target>-full`; packaging `native` also writes `dist/busierbox`.

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

These generated paths are ignored by git. Buildroot then builds the cross toolchain and BusyBox, stages `runtime/payload/bin/busybox`, discovers the actual installed BusyBox applets from the target rootfs, stages only real heavy-tool binaries that were built, writes `runtime/payload/manifest.json`, creates ustar-compatible payload archives, builds the BusierBox core with the Buildroot cross compiler, embeds the target payload, and writes `dist/busierbox-<target>-full.sha256`.

The payload manifest separates intent from reality:

- `requested_payload_tools`: tools selected in config/menuconfig
- `built_payload_tools`: requested tools for which a provider produced usable staged output
- `staged_payload_tools`: executable tools copied into `payload/bin`
- `missing_payload_tools`: requested tools no provider satisfied
- `missing_payload_tool_reasons`: per-tool reasons for missing requested tools
- `busybox_applets`: applets actually discovered in the staged BusyBox payload

BusierBox generates its advertised dispatch lists from `runtime/payload/busybox-applets.txt` and `runtime/payload/staged-tools.txt`. It does not advertise requested-but-missing tools, and missing heavy tools are recorded under the manifest plus `payload/share/busierbox/missing-tools.txt` instead of placeholder executables.

BusyBox applet selection is hierarchical in `make menuconfig`. Group checkboxes set sensible defaults, and each group has an applet submenu for overrides. Manual configs can use:

```text
BB_BUSYBOX_GROUPS="shell fileops disk process text system"
BB_BUSYBOX_APPLET_OVERRIDES="+nc -nuke"
```

`+nc` enables `nc` without selecting unrelated network tools. `-nuke` disables only the dangerous `nuke` applet while leaving the rest of the selected defaults intact. Dangerous or destructive applets such as `nuke`, `devmem`, reboot/poweroff, fdisk/mkfs, and flash tools live in the dedicated `dangerous` group where practical.

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
scripts/inspect-artifact dist/busierbox-mipsel-linux-4.x-musl-full
scripts/verify-artifact dist/busierbox-mipsel-linux-4.x-musl-full
scp dist/busierbox-mipsel-linux-4.x-musl-full root@router:/tmp/busierbox
ssh root@router
chmod +x /tmp/busierbox
/tmp/busierbox doctor
/tmp/busierbox list
/tmp/busierbox survey
/tmp/busierbox extract
/tmp/busierbox sh
```

Tool compatibility metadata lives in `payloads/tool-compat.json`. Menuconfig shows warnings for selected heavy tools such as `tmux`, `strace`, `gdbserver`, `dropbear`, `curl`, `zsh`, and the expanded operator tool set; it does not hard-block uncertain cases.

Generated Buildroot defconfigs enable supported package symbols for selected heavy tools:

```text
Networking/operator: socat tcpdump rsync mtr iperf3 ethtool iw minicom mosh-client
Text/utility:        ripgrep jq file htop screen
Debug/RE:            strace gdbserver ltrace readelf objdump xxd
System inspection:   usbutils pciutils
Shell/transport:     zsh tmux curl dropbear
```

Some provider names differ from staged command names. For example, selecting `ripgrep` stages `rg`, `usbutils` stages `lsusb`, and `pciutils` stages `lspci`. This is intentional: requested provider intent and staged dispatch commands are tracked separately. If Buildroot drops a package due to dependencies or the binary cannot be found after the build, the tool is listed as missing with a reason and is not dispatchable.

Artifact inspection and verification:

```sh
scripts/inspect-artifact dist/busierbox-native-full
scripts/verify-artifact dist/busierbox-native-full
make verify-artifact TARGET=native
VERIFY=1 make package TARGET=native
```

`scripts/inspect-artifact` parses the embedded payload trailer and manifest without executing the target binary, then validates manifest consistency, applet symlink records, staged heavy tools, overlay records, missing-tool reasons, placeholder scripts, and tmux terminfo. `scripts/verify-artifact` performs the same static checks and also executes the artifact when native or when qemu-user is available; otherwise it performs non-execution inspection and skips execution clearly. Verification copies only the self-extracting artifact to a temp directory, runs `list`, `config-info`, `doctor`, repeated `extract`, `sh`, duplicate-PATH checks, zsh/tmux/nc probes when staged, and help probes for advertised payload commands.

Release staging groundwork is intentionally single-target for now:

```sh
make release
make release TARGET=glinet-mt7621-openwrt-musl BB_RELEASE_NAME=dev-glinet
```

The release target packages and verifies the selected artifact, then stages it under `dist/releases/<name>/` with checksums, payload archives when present, and an inspector manifest under `dist/releases/<name>/manifests/`. Future release matrix work can build on the same artifact layout without changing normal `make package` behavior.

Validate Buildroot heavy-tool mappings against the checked-out Buildroot tree:

```sh
scripts/check-buildroot-tool-mappings
scripts/check-buildroot-tool-mappings --tools "socat tcpdump htop ltrace mosh-client"
```

The mapping checker distinguishes `supported`, `incompatible-for-tuple`, `provider-required`, `untested`, and `broken`. It catches nonexistent Buildroot symbols and known static-build exclusions before packaging emits invalid defconfig entries.

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

Doctor also reports payload identity/staleness, applet symlink count, overlay status and warnings, missing-tool reasons, terminfo availability, zsh presence, PATH duplicate hints, extraction free space, available memory, default-route presence, and recommendations for common tmux/dropbear/terminfo failures.

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
- `socat`, `tcpdump`, `rsync`, `mtr`, `iperf3`
- `ethtool`, `iw`, `minicom`, `mosh-client`
- `ripgrep`/`rg`, `jq`, `file`, `htop`, `screen`
- `ltrace`, `readelf`, `objdump`, `xxd`
- `lsusb` from `usbutils`, `lspci` from `pciutils`

Tier 2 should stay optional and Buildroot-friendly.

## Overlays And Shell Customization

User overlays are the escape hatch for personal tools and dotfiles. Enable them in `make menuconfig` or set:

```text
BB_USER_OVERLAY_ENABLE="yes"
BB_USER_OVERLAY_ROOT="/path/to/overlay-root"
```

The layout is:

```text
overlay-root/common/bin/
overlay-root/common/lib/
overlay-root/common/share/
overlay-root/common/home/
overlay-root/<target>/bin/
overlay-root/<target>/lib/
overlay-root/<target>/share/
overlay-root/<target>/home/
```

`common/` applies to every target, and `<target>/` applies only to that target name such as `mipsel-linux-4.x-musl`. Overlay binaries are marked as staged tools, recorded in the manifest, and checked for likely architecture mismatches when the host `file` command is available. Conflicts are not overwritten unless `BB_USER_OVERLAY_ALLOW_OVERRIDE=yes`; conflicts and warnings are reported in the payload diagnostics and `doctor`.

Default dotfile profiles live under `payloads/dotfiles/`:

- `default-minimal`
- `default-comfort`
- `default-operator`
- `user-supplied`
- `none`

The payload sets `BUSIERBOX_PAYLOAD_DIR`, `PATH`, `HOME`, `SHELL`, `ZDOTDIR`, `TERM`, `TERMINFO_DIRS`, and `LD_LIBRARY_PATH` as needed when dispatching tools. To use a personal Oh My Zsh setup, do not make BusierBox fetch it. Place `.oh-my-zsh` and `.zshrc` under `overlay-root/common/home/` or `overlay-root/<target>/home/`, or select the `user-supplied` dotfile profile and point it at a local dotfile directory before packaging.

## GL.iNet Integration Testing

For the GL-MT1300 / MT7621 target reachable as `root@192.168.8.1`:

```sh
make package
make test-glinet
```

The GL.iNet harness lives in `tests/integration/glinet/`. It starts a temporary local Python HTTP server, picks a local bind address when possible, downloads the artifact on the router with `wget` or `curl`, extracts under `/tmp/busierbox-itest` by default, runs `doctor`, verifies stale extraction reuse, checks PATH duplication, verifies BusyBox symlinks and advertised staged tools, launches zsh when staged, checks tmux/curl/strace when staged, validates overlay tools when present, and cleans up after success or failure. Use `KEEP_ARTIFACTS=1` to leave remote files for debugging, or override `ROUTER`, `REMOTE_DIR`, `BIND_ADDR`, `PORT`, and `ARTIFACT`.

## QEMU User Validation

`make test-qemu-user` copies only the selected `dist/busierbox-<target>-full` self-extracting binary into per-target artifact directories, runs `extract`, dispatches common applets, captures `survey.json`, captures `config-info`, and validates survey JSON. Missing qemu interpreters or missing target artifacts are reported as skips. `scripts/verify-artifact` is the stricter packaging-time check for advertised command reality; it catches commands that are listed but not dispatchable.

The primary generated OpenWrt-style target is `mipsel-linux-4.x-musl`. Legacy `mipsel-linux-2.6-uclibc` and ARMv7 musl remain available through presets/templates.

## Offline SDK Model

The repository contains build logic, manifests, patches, source pins, and small supervisor code. Large source caches, toolchains, and generated payload archives belong in release artifacts, not in the source tree.

All third-party sources should be pinned by version and SHA-256 in `manifests/sources.lock.json` before they become required for reproducible offline builds.
