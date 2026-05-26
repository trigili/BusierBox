# BusierBox

BusierBox is a reproducible embedded Linux debug-toolkit builder and runtime launcher. It is designed for old and modern embedded Linux targets where you want to upload one small supervisor binary, survey the target, extract a known payload when useful, and run familiar debug tools from that payload.

BusierBox is not a BusyBox replacement and is not a BusyBox fork. BusierBox manages survey, environment repair, payload extraction, and dispatch. BusyBox provides standard Unix utilities such as `sh`, `cp`, `dd`, `mount`, `ps`, `nc`, and `tar`.

## Why It Is Handy

- 🧭 Survey first: `busierbox survey --json` and the portable shell probe collect target facts without assuming Python or a full userspace.
- 🧰 One artifact, many tools: the supervisor dispatches BusyBox applets and staged heavy tools from a reproducible payload.
- 🧪 Bring-up loop: `scripts/busierbox-bringup` can survey a target, generate a conservative config, rebuild, and optionally run integration checks.
- 🧾 Explainable artifacts: `busierbox manifest --json` and `payload/manifest.json` show what was built, staged, missing, and validated.
- 🧹 Cleanup visibility: `busierbox cleanup-ledger --json` and `busierbox clean --dry-run --json` show BusierBox-controlled runtime paths before removal.
- 🔒 Safe defaults: no external writes and no network autorun unless explicitly configured.

Typical workflow:

1. Pick a target preset such as `glinet-mt7621-openwrt-musl`.
2. Pick a payload preset such as `survey-core`, `default`, or `ssh-operator`.
3. Build a self-extracting artifact.
4. Copy the artifact to the target.
5. Run `survey`, `config-info`, `doctor`, `extract`, and optionally `rshell`.
6. Validate with `scripts/integration-glinet` when the GL.iNet exemplar target is available.

```sh
make menuconfig
make package TARGET=glinet-mt7621-openwrt-musl
scp dist/busierbox-glinet-mt7621-openwrt-musl-full root@192.168.8.1:/tmp/busierbox
ssh root@192.168.8.1 'chmod +x /tmp/busierbox && /tmp/busierbox survey --json'
```

For first contact with a target, `scripts/busierbox-bringup` wraps the survey
and recommendation loop:

```sh
scripts/busierbox-bringup --host root@192.168.8.1 --operator-host auto
```

Bringup is a guided onboarding flow. `scripts/integration-glinet` is the
repeatable validation harness for known-safe test cases.

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

Target presets describe architecture/libc/kernel tuples. Payload presets
describe runtime behavior and staged tools. Payload presets do not change the
target tuple; they set choices such as core-only versus extract mode, zero-arg
behavior, reverse-access transport, heavy tools, dotfiles, and external-write
policy.

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

produces a deployable full artifact:

```text
dist/busierbox-mipsel-linux-4.x-musl-full
```

`-full` is the feature-complete self-extracting artifact. It contains a BusierBox core built for that target plus a payload archive built for that same target. A compatibility copy without the `-full` suffix is still written for existing scripts. Internal payload-less cores are written only under `dist/internal/` when enabled and should not be deployed as normal artifacts.

Artifact output knobs:

```sh
BB_BUILD_FULL="yes"
BB_BUILD_INTERNAL_CORE="no"
```

Reverse access flow:

```sh
scripts/busierbox-server --transport ssh
./busierbox-mipsel-linux-4.x-musl-full rshell start
```

`scripts/busierbox-server` reads `local/server-config.json` by default. In SSH mode it acts as a small operator-side Paramiko SSH server that accepts the target dbclient identity and catches the reverse forward. The target starts `dropbear` locally, runs `dbclient -R`, and the operator connects through the forwarded port:

```sh
ssh -p 2200 root@127.0.0.1
```

Reverse access is explicit and operator-controlled. BusierBox does not install persistence, daemonize by default, hide process names, delete logs, or repeatedly beacon in the background. The `rshell` applet is also available as an explicit command:

```sh
./busierbox rshell
./busierbox rshell status
./busierbox rshell stop
```

By default, artifacts do not initiate reverse access when run with no arguments.
Presets that do enable zero-arg reverse access say so in their metadata. Root
authorized-key writes and persistence installation remain disabled unless
explicitly configured and applied.

Convenience commands:

```sh
make package-native
make package TARGET=native
make package TARGET=glinet-mt7621-openwrt-musl
make package-full TARGET=mipsel-linux-4.x-musl
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

Tool compatibility metadata lives in `payloads/tool-compat.json`. Menuconfig shows warnings for selected heavy tools such as `bash`, `tmux`, `strace`, `gdbserver`, `dropbear`, `curl`, `zsh`, and the expanded operator tool set; it does not hard-block uncertain cases.

Generated Buildroot defconfigs enable supported package symbols for selected heavy tools:

```text
Networking/operator: socat tcpdump rsync mtr iperf3 ethtool iw minicom mosh-client
Text/utility:        ripgrep jq file htop screen
Debug/RE:            strace gdbserver ltrace readelf objdump xxd
System inspection:   usbutils pciutils
Shell/transport:     bash zsh tmux curl dropbear
Optional runtimes:   doom
```

Some provider names differ from staged command names. For example, selecting `ripgrep` stages `rg`, `usbutils` stages `lsusb`, and `pciutils` stages `lspci`. This is intentional: requested provider intent and staged dispatch commands are tracked separately. If Buildroot drops a package due to dependencies or the binary cannot be found after the build, the tool is listed as missing with a reason and is not dispatchable.

For target builds, selecting `doom` builds the static BusierBox `doom-ascii` provider through Buildroot. Set `BB_DOOM_WAD_PATH` to a local legally usable `.wad`; BusierBox stages that data file and does not download or bundle game data by default.

Artifact inspection and verification:

```sh
scripts/inspect-artifact dist/busierbox-native-full
scripts/verify-artifact dist/busierbox-native-full
make verify-artifact TARGET=native
VERIFY=1 make package TARGET=native
```

`scripts/inspect-artifact` parses the embedded payload trailer and manifest without executing the target binary, then validates manifest consistency, applet symlink records, staged heavy tools, overlay records, missing-tool reasons, placeholder scripts, and tmux terminfo. `scripts/verify-artifact` performs the same static checks and also executes the artifact when native or when qemu-user is available; otherwise it performs non-execution inspection and skips execution clearly. Verification copies only the self-extracting artifact to a temp directory, runs `list`, `config-info`, `doctor`, repeated `extract`, `sh`, duplicate-PATH checks, zsh/tmux/nc probes when staged, and help probes for advertised payload commands.

For a quick single-artifact release, use the Make target:

```sh
make release
make release TARGET=glinet-mt7621-openwrt-musl BB_RELEASE_NAME=dev-glinet
```

The `make release` target packages and verifies the selected artifact, then stages it under `dist/releases/<name>/` with checksums, payload archives when present, and an inspector manifest under `dist/releases/<name>/manifests/`.

For reusable multi-target bundles with generated configs, trailer-configuration helpers, matrix metadata, and a tarball, use:

```sh
scripts/make-release --name lab-router-pack --targets glinet-mt7621-openwrt-musl,mipsel-linux-4.x-musl --payload-presets survey-core,ssh-operator
scripts/make-release --name lab-router-pack --matrix release/matrices/iot-lab.json
scripts/make-release --name lab-router-pack --dry-run
```

See `docs/release-bundles.md` for the bundle layout and post-build trailer configuration helpers.

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

Workflow documentation:

- [Survey and bring-up](docs/survey-and-bringup.md)
- [Bringup script](docs/bringup.md)
- [Payload presets](docs/payload-presets.md)
- [GL.iNet integration](docs/integration-glinet.md)
- [Build matrix](docs/build-matrix.md)
- [Offline / enclave builds](docs/offline-enclave.md)
- [Plan mode](docs/plan-mode.md)
- [Cleanup ledger and no-residue](docs/cleanup-ledger.md)
- [Persistence](docs/persistence.md)
- [Manifest and support token](docs/manifest.md)
- [Artifact runtime overrides](docs/artifact-runtime-overrides.md)
- [gdbserver workflow](docs/gdbserver-workflow.md)
- [Release bundles](docs/release-bundles.md)
- [Heavy tool triage](docs/heavy-tools-triage.md)

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

Extract the full payload:

```sh
./busierbox extract
```

Extraction searches writable executable runtime locations:

- `./.busierbox`
- `/tmp/busierbox-$uid`
- `/var/tmp/busierbox-$uid`
- `/dev/shm/busierbox-$uid`

It avoids visible `noexec` mounts when `/proc/mounts` is readable, writes a payload `VERSION`, and reuses an existing full payload when the version matches. `./busierbox clean` removes the local `./.busierbox` extraction.

Extraction uses a lock directory, unpacks into a temporary directory, validates the result, and then atomically renames it into place. Interrupted extractions clean up their temporary directory where practical.

BusyBox applet dispatch uses a smaller core extraction when possible. For example, `./busierbox cp --help` only needs `payload/bin/busybox` plus payload metadata, so BusierBox extracts a `core` payload subset and writes `payload/.busierbox-extract-mode`. `./busierbox extract` and heavy tools upgrade that same runtime root to `full` before use. Legacy payload extractions without this marker are treated as full.

When launching payload tools BusierBox sets:

- `BUSIERBOX_PAYLOAD_DIR`
- `PATH`
- `HOME`
- `TERM` fallback
- `LD_LIBRARY_PATH` when `payload/lib` exists
- `ZDOTDIR` when payload home exists

`./busierbox list --plain` prints script-friendly command rows such as `busybox sh` and `tool strace`. `./busierbox list --json` prints the compiled native, BusyBox, and staged-tool command lists.

`./busierbox doctor` and `./busierbox doctor --json` report embedded payload presence, format, size, hash status, extraction status and mode, payload directory, manifest presence, BusyBox presence, BusyBox applet count, staged tools, missing requested tools, candidate extraction health, `/dev/pts`, and a conservative ptrace status.

Doctor also reports payload identity/staleness, applet symlink count, overlay status and warnings, missing-tool reasons, terminfo availability, zsh presence, PATH duplicate hints, extraction free space, available memory, default-route presence, and recommendations for common tmux/dropbear/terminfo failures.

`./busierbox plan` and `./busierbox plan --json` preview the operator-visible impact of extraction, reverse shell startup, cleanup, and recovery install actions without modifying the target. See `docs/plan-mode.md`.

`./busierbox config-info` reports the BusierBox build, extraction status, extraction mode, payload directory, payload hash, BusyBox dispatch status, post-build runtime override trailer status, and the payload manifest summary when available. `./busierbox runtime-config` and `./busierbox runtime-config --json` report compiled defaults, trailer overrides, environment overrides, command-line overrides where supported, and the effective runtime/operator config. `./busierbox manifest --json` includes compiled config, effective config, and trailer override metadata. `./busierbox config-export --json` and `./busierbox doctor --support-token` provide rebuild-oriented metadata that can be converted back into a starter config with `scripts/config-from-manifest` or `scripts/config-from-support-token`.

`scripts/artifact-config` can inspect, set, import, export, and clear optional runtime override trailers on existing artifacts. Overrides are limited to selected runtime/operator keys such as reverse-access host/ports, transport, run mode, retry settings, zero-arg mode, and log verbosity. They do not change target tuple, compiled features, payload tools, dotfiles, or overlay contents. Optional XOR obfuscation is not encryption and must not be used for credentials or private keys.

`scripts/make-release` builds reusable multi-target release bundles under `dist/releases/`. Bundles include artifacts, generated configs, manifests, checksum files, copied trailer-configuration helpers, and docs for post-build operator overrides. See `docs/release-bundles.md`.

`./busierbox persistence --survey` and `./busierbox persistence --plan` enumerate authorized lab persistence/recovery options without changing the target. Installation requires an explicit method/action plus `--dry-run` or `--external --apply`, and writes are recorded in the cleanup ledger with visible action metadata. `./busierbox recovery` remains as a deprecated compatibility alias.

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

Dotfiles are configured per app. Each app can use the BusierBox default initial config, a user-supplied file, or no staged config:

```text
BB_DOTFILES_ENABLE="yes"
BB_DOTFILE_ZSH_MODE="default"
BB_DOTFILE_ZSH_USER_FILE=""
BB_DOTFILE_BASH_MODE="default"
BB_DOTFILE_BASH_USER_FILE=""
BB_DOTFILE_TMUX_MODE="default"
BB_DOTFILE_TMUX_USER_FILE=""
BB_DOTFILE_GDB_MODE="default"
BB_DOTFILE_GDB_USER_FILE=""
BB_DOTFILE_PROFILE_MODE="default"
BB_DOTFILE_PROFILE_USER_FILE=""
```

Set a mode to `user` and point the matching `*_USER_FILE` at the exact file to stage, for example `.zshrc`, `.bashrc`, or `.tmux.conf`. Missing user files fail the payload build clearly. In `core-only` runtime mode, dotfiles are not staged because no payload HOME is extracted.

The payload sets `BUSIERBOX_PAYLOAD_DIR`, `PATH`, `HOME`, `SHELL`, `ZDOTDIR`, `TERM`, `TERMINFO_DIRS`, and `LD_LIBRARY_PATH` as needed when dispatching tools. To use a personal Oh My Zsh setup, do not make BusierBox fetch it. Place `.oh-my-zsh` and `.zshrc` under `overlay-root/common/home/` or `overlay-root/<target>/home/`, or set `BB_DOTFILE_ZSH_MODE=user` and point `BB_DOTFILE_ZSH_USER_FILE` at your local `.zshrc` before packaging.

## GL.iNet Integration Testing

For the GL-MT1300 / MT7621 target reachable as `root@192.168.8.1`:

```sh
make package
make test-glinet
```

The GL.iNet harness lives in `tests/integration/glinet/`. It starts a temporary local Python HTTP server, picks a local bind address when possible, downloads the artifact on the router with `wget` or `curl`, extracts under `/tmp/busierbox-itest` by default, runs `doctor`, verifies stale extraction reuse, checks PATH duplication, verifies BusyBox symlinks and advertised staged tools, launches zsh when staged, checks tmux/curl/strace when staged, validates overlay tools when present, and cleans up after success or failure. Use `KEEP_ARTIFACTS=1` to leave remote files for debugging, or override `ROUTER`, `REMOTE_DIR`, `BIND_ADDR`, `PORT`, and `ARTIFACT`.

Use `scripts/integration-report latest` for a compact table after a harness run,
and `scripts/integration-compare old-summary.json new-summary.json` to spot
status or artifact changes between runs.

## QEMU User Validation

`make test-qemu-user` copies only the selected `dist/busierbox-<target>-full` self-extracting binary into per-target artifact directories, runs `extract`, dispatches common applets, captures `survey.json`, captures `config-info`, and validates survey JSON. Missing qemu interpreters or missing target artifacts are reported as skips. `scripts/verify-artifact` is the stricter packaging-time check for advertised command reality; it catches commands that are listed but not dispatchable.

The primary generated OpenWrt-style target is `mipsel-linux-4.x-musl`. Legacy `mipsel-linux-2.6-uclibc` and ARMv7 musl remain available through presets/templates.

## Offline SDK Model

The repository contains build logic, manifests, patches, source pins, and small supervisor code. Large source caches, toolchains, and generated payload archives belong in release artifacts, not in the source tree.

All third-party sources should be pinned by version and SHA-256 in `manifests/sources.lock.json` before they become required for reproducible offline builds.
