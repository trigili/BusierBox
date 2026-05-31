# griTTYkit

griTTYkit is a reproducible embedded Linux debug-toolkit builder and runtime launcher. It is designed for old and modern embedded Linux targets where you want to upload one small supervisor binary, survey the target, extract a known payload when useful, and run familiar debug tools from that payload.

griTTYkit is not a BusyBox replacement and is not a BusyBox fork. griTTYkit manages survey, environment repair, payload extraction, and dispatch. BusyBox provides standard Unix utilities such as `sh`, `cp`, `dd`, `mount`, `ps`, `nc`, and `tar`.

griTTYkit's own code and project-maintained scripts are licensed under
GPL-2.0-or-later. Release artifacts can include separately licensed upstream
payload/build components such as BusyBox, Buildroot, doom-ascii, and miniz; see
[LICENSE.grit](LICENSE.grit), [NOTICE](NOTICE), and
[docs/licensing.md](docs/licensing.md) for the project license declaration,
compatibility notes, and source license inventory.
`manifests/license-policy.json` is the machine-readable compatibility policy,
and `scripts/check-licensing` verifies that the policy, pinned source metadata,
and bundled notices stay aligned.

## Why It Is Handy

- 🧭 Survey first: `grit survey --json` and the portable shell probe collect target facts without assuming Python or a full userspace.
- 🧰 One artifact, many tools: the supervisor dispatches BusyBox applets and staged heavy tools from a reproducible payload.
- 🧪 Bring-up loop: `scripts/grit-bringup` can survey a target, generate a conservative config, rebuild, and optionally run integration checks.
- 🧾 Explainable artifacts: `grit manifest --json` and `grit doctor` show positive inventory by default: compiled native applets, available BusyBox applets, staged heavy tools, runtime mode, reverse-access settings, and trailer override state. Missing requested tools are available through explicit `--include-missing` output and release build reports.
- 🧹 Cleanup visibility: `grit cleanup-ledger --json` and `grit clean --dry-run --json` show griTTYkit-controlled runtime paths before removal.
- 🔒 Safe defaults: no external writes and no network autorun unless explicitly configured.

Typical workflow:

1. Pick a target preset such as `mipsel-linux-4.x-musl`.
2. Pick a payload preset such as `survey-core`, `default`, or `ssh-operator`.
3. Build a self-extracting artifact.
4. Copy the artifact to the target.
5. Run `survey`, `config-info`, `doctor`, `extract`, and optionally `rshell`.
6. Validate locally with smoke tests, QEMU when configured, or a device-specific harness you provide.

```sh
make menuconfig
make package TARGET=mipsel-linux-4.x-musl
scp dist/grit-mipsel-linux-4.x-musl-full root@target:/tmp/grit
ssh root@target 'chmod +x /tmp/grit && /tmp/grit survey --json'
```

For first contact with a target, `scripts/grit-bringup` wraps the survey
and recommendation loop:

```sh
scripts/grit-bringup --host root@target --operator-host auto
```

Bringup is a guided onboarding flow for first contact, survey capture, config
recommendation, and explicit next-step commands.

## Architecture

The core binary stays small and static-first:

```sh
./grit survey
./grit envfix
./grit extract
./grit list
./grit config-info
```

Everything else is payload dispatch:

```sh
./grit sh
./grit cp a b
./grit dd if=/dev/mtd0 of=flash.bin bs=64k
./grit nc --help
./grit tmux
./grit strace ...
./grit gdbserver ...
```

Standard Unix tools execute through `payload/bin/busybox`:

```text
grit cp a b -> payload/bin/busybox cp a b
grit sh     -> payload/bin/busybox sh
```

Heavy tools execute directly from the extracted payload:

```text
grit tmux      -> payload/bin/tmux
grit strace    -> payload/bin/strace
grit gdbserver -> payload/bin/gdbserver
grit dropbear  -> payload/bin/dropbear
grit curl      -> payload/bin/curl
```

Native applets such as `survey`, `envfix`, `extract`, `clean`, `list`,
`config-info`, and `doctor` are compiled into griTTYkit. BusyBox applets
dispatch through `payload/bin/busybox`; heavy tools dispatch through
`payload/bin/<tool>`. Heavy tools are only advertised when a real executable was
staged into `payload/bin`. Requested tools that cannot be provided remain
visible in explicit build/runtime missing reports, but do not become placeholder
commands.

## Layout

```text
buildroot/configs/       checked-in Buildroot defconfigs
buildroot/generated-configs/ generated tuple Buildroot defconfigs
buildroot/external/      griTTYkit Buildroot external tree
targets/presets.json     preset templates that populate target tuples
payloads/profiles/       checked-in target metadata used by payload packaging
payloads/generated-profiles/ generated tuple payload metadata
payloads/dotfiles/       default .profile, .zshrc, .tmux.conf, .gdbinit
runtime/payload/         staged payload tree
runtime/payload/bin/     BusyBox and future tool binaries
runtime/payload/lib/     bundled shared libraries when static builds are unavailable
runtime/payload/home/    payload HOME
dist/grit-<target>-full    self-extracting target-specific artifact
dist/internal/                  internal payload-less cores when enabled
dist/grit                  native convenience alias, when native is packaged
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
ls dist/grit-*
```

`make package` reads the active tuple fields in `configs/grit.conf`, generates Buildroot backend files when needed, and builds target-specific outputs. Presets are convenience templates that populate tuple fields; the tuple is the source of truth.

Target presets describe architecture/libc/kernel tuples. Payload presets
describe runtime behavior and staged tools. Payload presets do not change the
target tuple; they set choices such as core-only versus extract mode, zero-arg
behavior, reverse-access transport, heavy tools, dotfiles, and external-write
policy.

```text
GRIT_TARGET_ARCH="mipsel"
GRIT_TARGET_ENDIAN="little"
GRIT_TARGET_CPU="mips32r2-24kc"
GRIT_TARGET_ABI="default"
GRIT_TARGET_LIBC="musl"
GRIT_KERNEL_FLOOR="4.x"
GRIT_STATIC_POLICY="static-preferred"
GRIT_PAYLOAD_TIER="debug"
```

produces a deployable full artifact:

```text
dist/grit-mipsel-linux-4.x-musl-full
```

`-full` is the feature-complete self-extracting artifact. It contains a griTTYkit core built for that target plus a payload archive built for that same target. A compatibility copy without the `-full` suffix is still written for existing scripts. Internal payload-less cores are written only under `dist/internal/` when enabled and should not be deployed as normal artifacts.

Artifact output knobs:

```sh
GRIT_BUILD_FULL="yes"
GRIT_BUILD_INTERNAL_CORE="no"
```

Reverse access flow:

```sh
scripts/grit-server --transport ssh
./grit-mipsel-linux-4.x-musl-full rshell start
```

`scripts/grit-server` reads `local/server-config.json` by default. In SSH mode it acts as a small operator-side Paramiko SSH server that accepts the target dbclient identity and catches the reverse forward. The target starts `dropbear` locally, runs `dbclient -R`, and the operator connects through the forwarded port:

```sh
ssh -p 2200 root@127.0.0.1
```

Run `scripts/grit-server --tui` for the operator workbench. It can inspect
services, recent sessions, received uploads, staged fetch files, and release
bundle artifacts/devices/tuples when launched from a release directory. The
curses view can open local logs, metadata, and staged/release files in a pager
for operator inspection. Generated target commands can be copied locally with
the `c` key or exported with `--copy-target-command`; the fallback copy path is
`local/operator-session/last-command.txt`. Staging a file or release artifact
only prepares an explicit target-side `grit fetch` command; it does not
execute commands on the target.
`scripts/grit-server --status` and `--json-status` expose the same
structured event log with aggregate counts and tail indexes by service, event,
and level for operator tooling.

The optional command queue remains a separate advanced feature. Operator-side
queue entries can be recorded with `scripts/grit-server --queue-command`
and inspected in server status. Explicit live target polling can receive queued
metadata, but current queue tooling does not execute queued commands by
default.

Reverse access is explicit and operator-controlled. griTTYkit does not install persistence, daemonize by default, hide process names, delete logs, or repeatedly beacon in the background. The `rshell` applet is also available as an explicit command:

```sh
./grit rshell
./grit rshell status
./grit rshell stop
```

By default, artifacts do not initiate reverse access when run with no arguments.
Presets that do enable zero-arg reverse access say so in their metadata. Root
authorized-key writes and persistence installation remain disabled unless
explicitly configured and applied.

Convenience commands:

```sh
make package-native
make package TARGET=native
make package TARGET=mipsel-linux-4.x-musl
make package-full TARGET=mipsel-linux-4.x-musl
make package-all-presets
```

For backwards compatibility, packaging also writes `dist/grit-<target>` as a copy of `dist/grit-<target>-full`; packaging `native` also writes `dist/grit`.

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

These generated paths are ignored by git. Buildroot then builds the cross toolchain and BusyBox, stages `runtime/payload/bin/busybox`, discovers the actual installed BusyBox applets from the target rootfs, stages only real heavy-tool binaries that were built, writes `runtime/payload/manifest.json`, creates ustar-compatible payload archives, builds the griTTYkit core with the Buildroot cross compiler, embeds the target payload, and writes `dist/grit-<target>-full.sha256`.

The payload manifest separates intent from reality:

- `requested_payload_tools`: tools selected in config/menuconfig
- `built_payload_tools`: requested tools for which a provider produced usable staged output
- `staged_payload_tools`: executable tools copied into `payload/bin`
- `missing_payload_tools`: requested tools no provider satisfied
- `missing_payload_tool_reasons`: per-tool reasons for missing requested tools
- `busybox_applets`: applets actually discovered in the staged BusyBox payload

griTTYkit generates its advertised dispatch lists from `runtime/payload/busybox-applets.txt` and `runtime/payload/staged-tools.txt`. It does not advertise requested-but-missing tools, and missing heavy tools are recorded under the manifest plus `payload/share/grit/missing-tools.txt` instead of placeholder executables.

BusyBox applet selection is hierarchical in `make menuconfig`. Group checkboxes set sensible defaults, and each group has an applet submenu for overrides. Manual configs can use:

```text
GRIT_BUSYBOX_GROUPS="shell fileops disk process text system"
GRIT_BUSYBOX_APPLET_OVERRIDES="+nc -nuke"
```

`+nc` enables `nc` without selecting unrelated network tools. `-nuke` disables only the dangerous `nuke` applet while leaving the rest of the selected defaults intact. Dangerous or destructive applets such as `nuke`, `devmem`, reboot/poweroff, fdisk/mkfs, and flash tools live in the dedicated `dangerous` group where practical.

Supported generated tuple families currently include `mipsel`/`mips` with `musl` or `uclibc`, and `armv7`, `aarch64`, `x86_64`, and `i386` with `musl`. Unsupported combinations fail clearly during target resolution or defconfig generation.

OpenWrt-style MIPS little-endian musl example:

```sh
make menuconfig
# Target Configuration
#   Generated tuple -> mipsel / musl / 4.x / mips32r2-24kc
# or manually:
#   arch=mipsel
#   cpu=mips32r2-24kc
#   endian=little
#   libc=musl
#   kernel_floor=4.x

make fetch-sources
make package VERIFY=1
scripts/inspect-artifact dist/grit-mipsel-linux-4.x-musl-full
scripts/verify-artifact dist/grit-mipsel-linux-4.x-musl-full
scp dist/grit-mipsel-linux-4.x-musl-full root@router:/tmp/grit
ssh root@router
chmod +x /tmp/grit
/tmp/grit doctor
/tmp/grit list
/tmp/grit survey
/tmp/grit extract
/tmp/grit sh
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

For target builds, selecting `doom` builds the static griTTYkit `doom-ascii` provider through Buildroot. Set `GRIT_DOOM_WAD_PATH` to a local legally usable `.wad`; griTTYkit stages that data file and does not download or bundle game data by default. Target packaging fails visibly if the staged `doom-ascii` engine is not static.

Artifact inspection and verification:

```sh
scripts/inspect-artifact dist/grit-native-full
scripts/verify-artifact dist/grit-native-full
make verify-artifact TARGET=native
VERIFY=1 make package TARGET=native
```

`scripts/inspect-artifact` parses the embedded payload trailer and manifest without executing the target binary, then validates manifest consistency, applet symlink records, staged heavy tools, overlay records, missing-tool reasons, placeholder scripts, and tmux terminfo. `scripts/verify-artifact` performs the same static checks and also executes the artifact when native or when qemu-user is available; otherwise it performs non-execution inspection and skips execution clearly. Verification copies only the self-extracting artifact to a temp directory, runs `list`, `config-info`, `doctor`, repeated `extract`, `sh`, duplicate-PATH checks, zsh/tmux/nc probes when staged, and help probes for advertised payload commands.

For a quick single-artifact release, use the Make target:

```sh
make release
make release TARGET=mipsel-linux-4.x-musl GRIT_RELEASE_NAME=dev-mipsel-musl
```

The `make release` target packages and verifies the selected artifact, then stages it under `dist/releases/<name>/` with checksums, payload archives when present, and an inspector manifest under `dist/releases/<name>/manifests/`.

For reusable multi-target bundles with generated configs, trailer-configuration helpers, matrix metadata, and a tarball, use:

```sh
scripts/make-release --name lab-router-pack --targets mipsel-linux-4.x-musl,armv7-linux-3.x-musl --payload-presets survey-core,ssh-operator
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
- [Build matrix](docs/build-matrix.md)
- [Offline / enclave builds](docs/offline-enclave.md)
- [Plan mode](docs/plan-mode.md)
- [Cleanup ledger and no-residue](docs/cleanup-ledger.md)
- [Persistence](docs/persistence.md)
- [Command queue](docs/command-queue.md)
- [Manifest and support token](docs/manifest.md)
- [Artifact runtime overrides](docs/artifact-runtime-overrides.md)
- [gdbserver workflow](docs/gdbserver-workflow.md)
- [Release bundles](docs/release-bundles.md)
- [Heavy tool triage](docs/heavy-tools-triage.md)
- [Licensing](docs/licensing.md)

The build attempts static linking for griTTYkit and BusyBox. If a payload tool cannot be built fully static, the intended fallback is to bundle its required shared libraries in `runtime/payload/lib` and set `LD_LIBRARY_PATH` when dispatching payload tools. The build should print warnings rather than silently producing a broken payload.

## Runtime

Survey a target:

```sh
./grit survey
./grit survey --json > survey.json
```

Repair a constrained shell environment:

```sh
eval "$(./grit envfix)"
```

Extract the full payload:

```sh
./grit extract
```

Extraction searches writable executable runtime locations:

- `./.grit`
- `/tmp/grit-$uid`
- `/var/tmp/grit-$uid`
- `/dev/shm/grit-$uid`

It avoids visible `noexec` mounts when `/proc/mounts` is readable, writes a payload `VERSION`, and reuses an existing full payload when the version matches. `./grit clean` removes the local `./.grit` extraction.

Extraction uses a lock directory, unpacks into a temporary directory, validates the result, and then atomically renames it into place. Interrupted extractions clean up their temporary directory where practical.

BusyBox applet dispatch uses a smaller core extraction when possible. For example, `./grit cp --help` only needs `payload/bin/busybox` plus payload metadata, so griTTYkit extracts a `core` payload subset and writes `payload/.grit-extract-mode`. `./grit extract` and heavy tools upgrade that same runtime root to `full` before use. Legacy payload extractions without this marker are treated as full.

When launching payload tools griTTYkit sets:

- `GRIT_PAYLOAD_DIR`
- `PATH`
- `HOME`
- `TERM` fallback
- `LD_LIBRARY_PATH` when `payload/lib` exists
- `ZDOTDIR` when payload home exists

`./grit list --plain` prints script-friendly command rows such as `busybox sh` and `tool strace`. `./grit list --json` prints the compiled native, BusyBox, and staged-tool command lists.

`./grit doctor` and `./grit doctor --json` report target/runtime
health and available capabilities by default: embedded payload presence, format,
size, hash status, extraction status and mode, payload directory, manifest
presence, BusyBox presence, BusyBox applet count, staged tools, candidate
extraction health, `/dev/pts`, and a conservative ptrace status. Add
`--include-missing` when you need requested-but-unavailable tool details.

Doctor also reports payload identity/staleness, applet symlink count, overlay
status and warnings, terminfo availability, zsh presence, PATH duplicate hints,
extraction free space, available memory, default-route presence, and
recommendations for common tmux/dropbear/terminfo failures. Missing-tool
reasons are included only with `--include-missing`.

`./grit plan` and `./grit plan --json` preview the operator-visible impact of extraction, reverse shell startup, cleanup, and recovery install actions without modifying the target. See `docs/plan-mode.md`.

`./grit config-info` reports the griTTYkit build, extraction status, extraction mode, payload directory, payload hash, BusyBox dispatch status, post-build runtime override trailer status, and the payload manifest summary when available. `./grit runtime-config` and `./grit runtime-config --json` report compiled defaults, trailer overrides, environment overrides, command-line overrides where supported, and the effective runtime/operator config. `./grit manifest --json` includes compiled config, effective config, and trailer override metadata. `./grit config-export --json` and `./grit doctor --support-token` provide rebuild-oriented metadata that can be converted back into a starter config with `scripts/config-from-manifest` or `scripts/config-from-support-token`.

`scripts/artifact-config` can inspect, set, import, export, and clear optional runtime override trailers on existing artifacts. Overrides are limited to selected runtime/operator keys such as reverse-access host/ports, transport, run mode, retry settings, zero-arg mode, and log verbosity. They do not change target tuple, compiled features, payload tools, dotfiles, or overlay contents. Optional XOR obfuscation is not encryption and must not be used for credentials or private keys.

`scripts/make-release` builds reusable multi-target release bundles under
`dist/releases/`. Bundles include artifacts, generated configs, manifests,
checksum files, copied trailer-configuration helpers, a release self-test,
artifact finder/index tools, and docs for post-build operator overrides. See
`docs/release-bundles.md`.

`./grit persistence --survey` and `./grit persistence --plan` enumerate authorized lab persistence/recovery options without changing the target. Installation requires an explicit method/action plus `--dry-run` or `--external --apply`, and writes are recorded in the cleanup ledger with visible action metadata. `./grit recovery` remains as a deprecated compatibility alias.

## Tiers

Tier 0: griTTYkit supervisor.

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
GRIT_USER_OVERLAY_ENABLE="yes"
GRIT_USER_OVERLAY_ROOT="/path/to/overlay-root"
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

`common/` applies to every target, and `<target>/` applies only to that target name such as `mipsel-linux-4.x-musl`. Overlay binaries are marked as staged tools, recorded in the manifest, and checked for likely architecture mismatches when the host `file` command is available. Conflicts are not overwritten unless `GRIT_USER_OVERLAY_ALLOW_OVERRIDE=yes`; conflicts and warnings are reported in the payload diagnostics and `doctor`.

Dotfiles are configured per app. Each app can use the griTTYkit default initial config, a user-supplied file, or no staged config:

```text
GRIT_DOTFILES_ENABLE="yes"
GRIT_DOTFILE_ZSH_MODE="default"
GRIT_DOTFILE_ZSH_USER_FILE=""
GRIT_DOTFILE_BASH_MODE="default"
GRIT_DOTFILE_BASH_USER_FILE=""
GRIT_DOTFILE_TMUX_MODE="default"
GRIT_DOTFILE_TMUX_USER_FILE=""
GRIT_DOTFILE_GDB_MODE="default"
GRIT_DOTFILE_GDB_USER_FILE=""
GRIT_DOTFILE_PROFILE_MODE="default"
GRIT_DOTFILE_PROFILE_USER_FILE=""
```

Set a mode to `user` and point the matching `*_USER_FILE` at the exact file to stage, for example `.zshrc`, `.bashrc`, or `.tmux.conf`. Missing user files fail the payload build clearly. In `core-only` runtime mode, dotfiles are not staged because no payload HOME is extracted.

The payload sets `GRIT_PAYLOAD_DIR`, `PATH`, `HOME`, `SHELL`, `ZDOTDIR`, `TERM`, `TERMINFO_DIRS`, and `LD_LIBRARY_PATH` as needed when dispatching tools. To use a personal Oh My Zsh setup, do not make griTTYkit fetch it. Place `.oh-my-zsh` and `.zshrc` under `overlay-root/common/home/` or `overlay-root/<target>/home/`, or set `GRIT_DOTFILE_ZSH_MODE=user` and point `GRIT_DOTFILE_ZSH_USER_FILE` at your local `.zshrc` before packaging.

## QEMU User Validation

`make test-qemu-user` copies only the selected `dist/grit-<target>-full` self-extracting binary into per-target artifact directories, runs `extract`, dispatches common applets, captures `survey.json`, captures `config-info`, and validates survey JSON. Missing qemu interpreters or missing target artifacts are reported as skips. `scripts/verify-artifact` is the stricter packaging-time check for advertised command reality; it catches commands that are listed but not dispatchable.

The primary generated OpenWrt-style target is `mipsel-linux-4.x-musl`. Legacy `mipsel-linux-2.6-uclibc` and ARMv7 musl remain available through presets/templates.

## Offline SDK Model

The repository contains build logic, manifests, patches, source pins, and small supervisor code. Large source caches, toolchains, and generated payload archives belong in release artifacts, not in the source tree.

All third-party sources should be pinned by version and SHA-256 in `manifests/sources.lock.json` before they become required for reproducible offline builds.
