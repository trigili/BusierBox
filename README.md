# griTTYkit

griTTYkit is a reproducible embedded Linux debug-toolkit builder and runtime
launcher. It is designed for old and modern embedded Linux targets where you
want to upload one small supervisor binary, survey the target, extract a known
payload, and run familiar debug tools from that payload.

griTTYkit is not a BusyBox replacement and is not a BusyBox fork. griTTYkit
manages survey, environment repair, payload extraction, and dispatch. BusyBox
provides standard Unix utilities such as `sh`, `cp`, `dd`, `mount`, `ps`,
`nc`, and `tar`.

griTTYkit's own code and project-maintained scripts are licensed under
GPL-2.0-or-later. Release artifacts can include separately licensed upstream
payload/build components such as BusyBox, Buildroot, doom-ascii, and miniz; see
[LICENSE.grit](LICENSE.grit), [NOTICE](NOTICE), and
[docs/licensing.md](docs/licensing.md) for the project license declaration,
compatibility notes, and source license inventory.
`manifests/license-policy.json` is the machine-readable compatibility policy,
and `scripts/check-licensing` verifies that the policy, pinned source metadata,
and bundled notices stay aligned.

---

## Quick Start

```sh
# Build a native artifact for local testing
git submodule update --init third_party/busybox
make
make package TARGET=native

# Run on the local machine
./dist/grit-native-full survey --json
./dist/grit-native-full doctor
./dist/grit-native-full list
```

```sh
# Build for a MIPS OpenWrt target and deploy
make menuconfig          # configure arch/libc/kernel/payload
make package TARGET=mipsel-linux-4.x-musl
scp dist/grit-mipsel-linux-4.x-musl-full root@router:/tmp/grit
ssh root@router 'chmod +x /tmp/grit && /tmp/grit doctor'
```

---

## Operator Console

The operator side is managed through `scripts/grit-server`, which provides an
interactive console, reverse-access listeners, a file service, and command
queueing for targets that phone home.

### Starting the console

```sh
scripts/grit-server --tui
```

The console opens with a compact status banner and a `grit[all]>` prompt. It
supports readline editing — arrow-key history, `Ctrl+L` to clear, `Ctrl+R` to
search, and `Tab` for context-aware completions.

```
griTTYkit Workbench  0 listening  |  2 targets  |  6 staged  |  50608 events

  ? help  workspace overview  targets/sessions/files  start ssh|tls|file-service

grit[all]>
```

Type `?` for a topic index. Type `<topic> ?` or `help <topic>` for details on
any topic:

```
grit[all]> ?

Console help topics:

  workspace   overview, status, info, search, next
  targets     agents, select, mailbox, activity feed
  listeners   services, start/stop, options
  sessions    list, select, inspect, interact
  files       stage, fetch, download, release, serve-binary, view
  probe       shell probe (pre-deployment): run probe.sh, see results, gen config
  survey      full griTTYkit survey (post-deployment): config, presets
  queue       command queue, mailbox, results
  routes      bridge profiles, multi-hop tunnels
  daemon      systemd workflow actions
  jobs        background jobs
  build       binary build config, guided options
  console     history, resource scripts, completions, aliases

  help <topic>  or  <topic> ?   get detailed help on a topic
```

### Listeners

Start a reverse-access listener:

```
grit[all]> start ssh
grit[all]> start tls-shell
grit[all]> start file-service
grit[all]> listeners
```

Stop a listener:

```
grit[all]> stop ssh
```

### Targets and sessions

```
grit[all]> targets                  # list known agents
grit[all]> use target my-router     # select a target context
grit[my-router]> sessions           # list sessions for this target
grit[my-router]> sessions -v        # with paths and log locations
grit[my-router]> sessions clear     # preview cleanup of finished sessions
grit[my-router]> sessions clear --confirm
```

### Files

Stage a file so a target can fetch it:

```
grit[all]> upload ./grit-mipsel-linux-4.x-musl-full grit --start
```

`--start` also starts the file-service listener. The console prints the
target-side fetch command to run on the device.

```
grit[all]> files          # list staged files and fetch commands
grit[all]> release        # list release artifacts and selectors
grit[all]> release stage by_device:gl-mt1300 --start
```

### Command queue

Queue a command for a target's next phone-home:

```
grit[my-router]> queue grit survey --json
grit[my-router]> queue list
grit[my-router]> queue result 1
```

### Headless operation

Common workflows without the interactive console:

```sh
scripts/grit-server --status
scripts/grit-server --json-status
scripts/grit-server --transport ssh
scripts/grit-server --serve-file ./grit --as grit
scripts/grit-server --stage-release-artifact by_device:gl-mt1300
scripts/grit-server --list-staged
scripts/grit-server --target-id my-router --queue-command 'grit survey --json'
```

Run as a background daemon with systemd:

```sh
scripts/grit-server --systemd-user-action print    # preview unit file
scripts/grit-server --systemd-user-action install  # install and enable
scripts/grit-server --daemon --daemon-service file-service --daemon-service command-queue
```

---

## Probe and Survey Workflow

Getting a config from scratch — no BusyBox required on the target, just
`wget` or `curl`.

### Step 1 — probe.sh (pre-deployment)

Start the probe listener and run the shown command on the target:

```
grit[all]> probe --start

Probe:
  port=22207  script=probe.sh  listening=yes
  wget -O- http://192.168.8.241:22207/probe.sh | /bin/sh

  Run the command above on the target, then: probe results
```

The probe captures arch, kernel, word size, and endian, and POSTs them back.

```
grit[all]> probe results

Probe results  (1 received)

  #  Remote           Arch    Kernel    OS     Bits  Endian  At
  ─  ───────────────  ──────  ────────  ─────  ────  ──────  ───────────
  1  192.168.8.1:...  mips    5.10.176  Linux  32    big     05-31 14:41

  Next steps:
    probe config                           — generate config from most recent result
    probe config --write-config FILE       — generate and save
    probe serve [--start]                  — stage the matching binary for this arch
```

Generate and save a config from probe data:

```
grit[all]> probe config --write-config local/server-config.json
```

Stage the right binary for the detected architecture:

```
grit[all]> probe serve --start
```

### Step 2 — full survey (post-deployment)

Once griTTYkit is running on the target, push a rich survey:

```sh
# on the target:
grit survey push --host 192.168.8.241 --port 8080
```

```
grit[all]> survey results    # see the uploaded survey.json
grit[all]> survey config --write-config local/server-config.json
grit[all]> survey preset --name gl-mt1300 --write-local
```

The full survey captures libc, filesystem layout, writable paths, available
tools, and network interfaces — enough for `config-from-survey` to generate
a precise build config rather than conservative defaults.

---

## Binary Usage (On Target)

### Built-in applets

```sh
./grit survey                 # print target facts to stdout
./grit survey --json          # JSON output
./grit survey push            # upload survey to operator file service
./grit envfix                 # print environment repair commands
eval "$(./grit envfix)"       # apply them
./grit extract                # extract full payload to writable location
./grit clean                  # remove local .grit extraction
./grit list                   # list all dispatchable commands
./grit list --json
./grit doctor                 # report target/runtime health
./grit doctor --json
./grit config-info            # report build and config
./grit manifest --json        # full payload manifest
./grit plan                   # preview extraction/cleanup impact
./grit plan --json
```

### Reverse access

```sh
./grit rshell                 # start reverse shell (uses compiled transport)
./grit rshell status          # show reverse shell state
./grit rshell stop            # stop the reverse shell
```

In SSH transport mode, `grit-server --transport ssh` acts as an operator-side
Paramiko SSH server. The target runs dbclient and establishes a reverse
forward; the operator connects through the forwarded port:

```sh
scripts/grit-server --transport ssh   # operator side
./grit rshell                         # target side — calls dbclient internally
ssh -p 2200 root@127.0.0.1            # operator connects through the forward
```

### BusyBox dispatch

Standard Unix tools run through the staged `payload/bin/busybox`:

```sh
./grit sh
./grit cp src dst
./grit tar xf archive.tar
./grit ps
./grit nc -l -p 4444
```

### Heavy tool dispatch

Staged heavy tools run directly from the extracted payload:

```sh
./grit tmux
./grit strace ./some-binary
./grit gdbserver :1234 ./some-binary
./grit dropbear -F -p 2222
./grit curl https://...
./grit rg pattern /etc
./grit jq . survey.json
```

Heavy tools run directly from `payload/bin/<tool>`. They are only available
when built and staged. `./grit list` and `./grit doctor` report positive inventory by default —
only real, dispatchable commands are advertised.
`./grit doctor --include-missing` adds requested tools that could not be provided.

---

## Build

### Prerequisites

```sh
git submodule update --init third_party/busybox
```

### Native (for local testing)

```sh
make
make package TARGET=native
./dist/grit-native-full doctor
```

### Cross-compiled target

```sh
make menuconfig              # configure arch / libc / kernel / payload
make fetch-sources           # fetch pinned Buildroot and sources
make package                 # build with active config
make package TARGET=mipsel-linux-4.x-musl   # explicit target
make package-full TARGET=mipsel-linux-4.x-musl
```

Key config fields:

```text
GRIT_TARGET_ARCH="mipsel"
GRIT_TARGET_ENDIAN="little"
GRIT_TARGET_CPU="mips32r2-24kc"
GRIT_TARGET_LIBC="musl"
GRIT_KERNEL_FLOOR="4.x"
GRIT_PAYLOAD_PRESET="ssh-operator"
```

Supported tuple families: `mipsel`/`mips` (musl, uclibc),
`armv7`, `aarch64`, `x86_64`, `i386` (musl).

### Payload presets

| Preset | Description |
|---|---|
| `survey-core` | Probe + survey only; minimal footprint |
| `default` | BusyBox + common debug tools |
| `ssh-operator` | Adds dropbear, tmux, full rshell suite |

Payload presets set runtime behavior and staged tools without changing the
target tuple. See `docs/payload-presets.md`.

### BusyBox applet selection

Configure applet groups in `make menuconfig` or set directly:

```text
GRIT_BUSYBOX_GROUPS="shell fileops disk process text system"
GRIT_BUSYBOX_APPLET_OVERRIDES="+nc -nuke"
```

`+nc` enables `nc` without pulling in all network tools. `-nuke` disables the
`nuke` applet while leaving other selected defaults intact.

### Artifact output

```text
dist/grit-<target>-full          self-extracting artifact
dist/grit-<target>-full.sha256   checksum
```

`-full` is the feature-complete self-extracting artifact containing the
griTTYkit core plus its payload archive for that target. A compatibility alias
without `-full` is also written.

### Inspection and verification

```sh
scripts/inspect-artifact dist/grit-native-full
scripts/verify-artifact dist/grit-native-full
make verify-artifact TARGET=native
VERIFY=1 make package TARGET=native
```

`inspect-artifact` parses the embedded trailer and manifest without executing
the binary. `verify-artifact` runs the artifact (natively or via qemu-user)
through a real extraction, applet dispatch, and tool probe sequence.

---

## Architecture

### Supervisor tiers

**Tier 0 — native applets** (compiled into `grit`):
`survey`, `envfix`, `extract`, `clean`, `list`, `config-info`, `doctor`,
`plan`, `manifest`, `rshell`, `persistence`, `recovery`

**Tier 1 — BusyBox** (`payload/bin/busybox`):
`sh`, coreutils-style file tools, `tar`/`gzip`, `ps`/`mount`/`df`,
`nc`, `wget`, `awk`, `sed`, ...

**Tier 2 — heavy tools** (`payload/bin/<tool>`):
`tmux`, `strace`, `gdbserver`, `dropbear`, `curl`, `zsh`, `bash`,
`socat`, `tcpdump`, `rsync`, `mtr`, `iperf3`, `ethtool`, `iw`,
`ripgrep`/`rg`, `jq`, `file`, `htop`, `screen`, `ltrace`, `readelf`,
`objdump`, `xxd`, `lsusb`, `lspci`, `mosh-client`

Tier 2 tools are optional and Buildroot-backed. `./grit list` only advertises
tools that were successfully built and staged; missing tools appear in
`./grit doctor --include-missing`.

### Dispatch model

```text
./grit cp a b       → payload/bin/busybox cp a b
./grit sh           → payload/bin/busybox sh
./grit tmux         → payload/bin/tmux
./grit strace ...   → payload/bin/strace ...
```

BusyBox applets dispatch through `payload/bin/busybox`. Heavy tools execute
directly from the extracted payload. Native applets such as `survey`,
`envfix`, and `doctor` are compiled into the supervisor binary itself.

### Extraction

On first use, the payload is extracted to the first writable executable
location found:

```text
./.grit
/tmp/grit-$uid
/var/tmp/grit-$uid
/dev/shm/grit-$uid
```

BusyBox applet dispatch only needs a lightweight core extraction
(`payload/bin/busybox` + metadata). Heavy tools and `extract` upgrade the
same runtime root to a full extraction. `./grit clean` removes `./.grit`.

---

## Layout

```text
src/                  griTTYkit supervisor C source
third_party/busybox/  BusyBox git submodule
buildroot/            Buildroot integration (external tree, configs)
payloads/             payload profiles, dotfiles
runtime/payload/      staged payload tree (gitignored)
targets/              target presets
configs/              active build config
manifests/            source pins, license policy
scripts/              operator tools and build helpers
  grit-server         operator console and reverse-access server
  grit-bringup        guided first-contact and survey loop
  config-from-survey  generate build config from survey JSON
  preset-from-survey  generate reusable target preset from survey JSON
  make-release        build multi-target release bundles
  inspect-artifact    parse artifact without executing
  verify-artifact     static + execution artifact verification
docs/                 workflow documentation
dist/                 built artifacts (gitignored)
local/                operator runtime state (gitignored)
```

---

## Release Bundles

For multi-target bundles with generated configs, checksums, trailer helpers,
and a matrix manifest:

```sh
scripts/make-release --name lab-pack \
  --targets mipsel-linux-4.x-musl,armv7-linux-3.x-musl \
  --payload-presets survey-core,ssh-operator

scripts/make-release --name lab-pack --matrix release/matrices/iot-lab.json
scripts/make-release --name lab-pack --dry-run
```

See `docs/release-bundles.md` for bundle layout, artifact finder tools,
post-build trailer configuration helpers, and the release self-test.

---

## Overlays and Dotfiles

User overlays are the escape hatch for personal tools and dotfiles:

```text
GRIT_USER_OVERLAY_ENABLE="yes"
GRIT_USER_OVERLAY_ROOT="/path/to/overlay-root"
```

Layout:

```text
overlay-root/common/bin/        applies to all targets
overlay-root/common/home/
overlay-root/<target>/bin/      applies to that target only
overlay-root/<target>/home/
```

Dotfile staging is per-app (`default`, `user`, or disabled):

```text
GRIT_DOTFILE_ZSH_MODE="user"
GRIT_DOTFILE_ZSH_USER_FILE="/path/to/.zshrc"
GRIT_DOTFILE_TMUX_MODE="default"
GRIT_DOTFILE_GDB_MODE="default"
```

---

## Smoke Tests

```sh
make smoke-test
```

---

## Documentation

- [Survey and bring-up](docs/survey-and-bringup.md)
- [Bringup script](docs/bringup.md)
- [Payload presets](docs/payload-presets.md)
- [Build matrix](docs/build-matrix.md)
- [Offline / enclave builds](docs/offline-enclave.md)
- [Plan mode](docs/plan-mode.md)
- [Cleanup ledger](docs/cleanup-ledger.md)
- [Persistence](docs/persistence.md)
- [Command queue](docs/command-queue.md)
- [Manifest and support token](docs/manifest.md)
- [Artifact runtime overrides](docs/artifact-runtime-overrides.md)
- [gdbserver workflow](docs/gdbserver-workflow.md)
- [Release bundles](docs/release-bundles.md)
- [Heavy tool triage](docs/heavy-tools-triage.md)
- [Licensing](docs/licensing.md)
