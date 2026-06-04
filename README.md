# griTTYkit

griTTYkit is a reproducible embedded Linux debug-toolkit builder and runtime
launcher. It is designed for old and modern embedded Linux targets where you
want to upload one small supervisor binary, survey the target, extract a known
payload, and run familiar debug tools from that payload.

griTTYkit is not a BusyBox replacement and is not a BusyBox fork. griTTYkit
manages survey, environment repair, payload extraction, and dispatch. BusyBox
provides standard Unix utilities such as `sh`, `cp`, `dd`, `mount`, `ps`,
`nc`, and `tar`.

Bringup is a guided onboarding flow for turning an unknown target survey into a
recommended config, optional target preset, and staged release artifact. See
[docs/bringup.md](docs/bringup.md) for the operator workflow and
[docs/payload-presets.md](docs/payload-presets.md) for the payload profiles used
by releases and menuconfig.

griTTYkit's own code and project-maintained scripts are licensed under
GPL-2.0-or-later. Release artifacts can include separately licensed upstream
payload/build components such as BusyBox, Buildroot, doom-ascii, and miniz; see
[LICENSE.grit](LICENSE.grit), [NOTICE](NOTICE), and
[docs/licensing.md](docs/licensing.md) for the project license declaration,
compatibility notes, and source license inventory.
`manifests/license-policy.json` is the machine-readable compatibility policy,
and `scripts/lib/check-licensing` verifies that the policy, pinned source metadata,
and bundled notices stay aligned.

---

## What Can It Do?

griTTYkit is designed to work on targets that fight back — ancient kernels,
read-only root filesystems, `/tmp` mounted `noexec`, no Python, no package
manager, spotty connectivity, and hardware you'd rather not brick. Here's
what it actually does under the hood.

### Gets onto the target without knowing what it is first

The probe bootstrap (`probe.sh`) is a ~40-line POSIX sh script served
on-demand by the operator console. It runs before griTTYkit exists on the
device — all it needs is `wget` or `curl` and `/bin/sh`. It determines arch,
kernel version, word size, and endianness, then POSTs the results back to the
operator. From there, `probe config` generates a build config and `probe serve`
stages the right binary for the detected architecture.

```sh
# operator side — one command
grit[all]> probe --start
  wget -O- http://192.168.1.10:22207/probe.sh | /bin/sh   # ← run this on target
grit[all]> probe results      # see what came back
grit[all]> probe config --write-config configs/grit.conf
grit[all]> probe serve --start
```

`probe serve --start` stages the selected binary, starts the file service when
requested, and prints target-side fetch options. For first deployment use the
shown `wget` or `curl` command; when the file service is configured without TLS,
the console also prints a raw HTTP `nc` fallback. After griTTYkit is already
present, use the shown `grit fetch ...` command.

### Finds somewhere to live, no matter what

Before extracting, griTTYkit probes whether a directory is actually usable for
code execution — not just writable, but executable and not `noexec`-mounted.
It parses `/proc/mounts` to find the mount covering each candidate path, checks
the flags, measures available space (requires 4× payload size), then walks a
fallback chain:

```
./.grit  →  /tmp/grit-$uid  →  /var/tmp/grit-$uid  →  /dev/shm/grit-$uid
```

If every candidate is `noexec`, it tells you exactly why rather than silently
failing. Aggressive no-residue mode disables the fallback chain entirely and
errors at build time if it would be needed.

### Extracts without buffering the whole payload

The payload is a gzip'd tar embedded in the binary. `payload_extract.c`
implements its own streaming gzip decompressor — it inflates through an 8 KB
window that feeds directly into tar parsing, never buffering the full payload
in memory. A 50 MB payload with tmux, zsh, and gdbserver extracts on a router
with 32 MB free RAM. BusyBox-only invocations (`grit sh`, `grit cp`) trigger
a lightweight core-only extraction that skips the heavy tools entirely.

### Repairs a broken shell environment

On targets where init scripts forgot to set `PATH`, `HOME`, or `TERM`:

```sh
eval "$(./grit envfix)"
```

Prints the right `export` statements for the actual system, creates a fallback
home directory if needed, and works in any shell state — including one that has
sourced nothing useful.

### Checks whether the target can actually do what you need

`grit reality-test` runs 21 distinct probes before you commit to a workflow:

- Can it fork? Spawn a shell? Allocate a PTY?
- Is `/tmp` `noexec`? Is root read-only? Is `/proc` partial?
- Can it bind localhost? Reach the operator with a non-blocking TCP connect?
- Can it run payload binaries — BusyBox applets, heavy tools?
- Is `ptrace` available (needed for gdbserver)?

It outputs structured JSON separating *constraints* (what's missing) from
*capabilities* (what works), and feeds that into config recommendations. The
config pipeline uses reality-test output to decide whether to recommend
builtin TLS, socat, or SSH transport based on what the target can actually do.

### Knows what it wrote and cleans it up honestly

Every file griTTYkit creates is recorded in a JSONL ledger on the target with
the operation, path, scope, timestamp, and target identity. `grit clean` uses
the ledger rather than glob-deleting things it *thinks* it created.

For SSH authorized_keys specifically, there are three cleanup modes:
full removal, merge (remove only the injected block while preserving keys
that existed before), and backup restore. And `grit plan` explicitly lists
what it *cannot* clean — kernel logs, shell history, filesystem journals,
flash wear-leveling — rather than claiming a cleanliness it can't guarantee.

### Stamps binaries with operator config post-build

The trailer system appends an encrypted configuration block to the end of a
built artifact without touching the ELF. You can ship one binary to 100
different targets and stamp each one with a different operator IP, transport,
and port after the fact:

```sh
scripts/grit-console artifact config set dist/grit-mipsel-linux-4.x-musl-full \
  GRIT_OPERATOR_SERVER_HOST=10.0.0.5 \
  GRIT_RSHELL_TRANSPORT=tls-shell
```

The trailer is SHA-256 verified on load and optionally XOR-obfuscated. It
overrides compiled-in defaults without requiring a rebuild.

### Reverse shell that works on stripped OpenWrt

The builtin TLS reverse shell uses pipes instead of a PTY because OpenWrt PTY
behavior varies across kernel versions and target hardware. The wolfSSL
integration handles `WANT_READ`/`WANT_WRITE` correctly — TLS reads can require
writes and vice versa, and getting this wrong causes subtle hangs. The SSH
transport uses Dropbear's `dbclient` to establish a reverse forward, and the
operator console catches it with a small Paramiko SSH server.

Three transports, one config field:

```text
GRIT_RSHELL_TRANSPORT=ssh          # reverse SSH forward via dbclient
GRIT_RSHELL_TRANSPORT=tls-shell    # builtin wolfSSL or socat TLS
GRIT_RSHELL_TRANSPORT=plain-shell  # unencrypted, for isolated labs
```

### Works without internet — reproducibly

Every third-party source is SHA-256 pinned in `manifests/sources.lock.json`.
`scripts/lib/mirror-sources` fetches and verifies the full source set.
`scripts/lib/check-offline-readiness` validates completeness before a build
attempt. The result is a tarball you can carry into an air-gapped network and
build from with no external access required.

### Handles targets that phone home on their own schedule

When a target can't hold a persistent connection, the command queue lets you
stage work for delivery on the target's next poll. The operator queues
commands; the target polls at a configurable interval with exponential backoff
and jitter; results come back the next time the target checks in. The queue
has an explicit policy model (`none`, `grit-only`, `allowlist`, `custom`) that
controls what can be executed, with dry-run before any execution mode is
enabled.

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

The operator side is managed through `scripts/grit-console`, which provides an
interactive console, reverse-access listeners, a file service, and command
queueing for targets that phone home.

### Starting the console

```sh
scripts/grit-console
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
grit[all]> release stage by_device:glinet-mt1300 --start
grit[all]> release stage by_device_payload_preset:glinet-mt1300:survey-core
grit[all]> release stage by_tuple_payload_preset:by-tuple/mipsel/musl/4.x/mips32r2-24kc:ssh-operator
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
scripts/grit-console --status
scripts/grit-console --json-status
scripts/grit-console --transport ssh
scripts/grit-console --serve-file ./grit --as grit
scripts/grit-console --stage-release-artifact by_device:glinet-mt1300
scripts/grit-console --list-staged
scripts/grit-console --target-id my-router --queue-command 'grit survey --json'
```

Run as a background daemon with systemd:

```sh
scripts/grit-console --systemd-user-action print    # preview unit file
scripts/grit-console --systemd-user-action install  # install and enable
scripts/grit-console --daemon --daemon-service file-service --daemon-service command-queue
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
grit[all]> probe config --write-config configs/grit.conf
```

This writes a build/artifact config. It is separate from the operator console
server config such as `local/server-config.json`.

Stage the right binary for the detected architecture:

```
grit[all]> probe serve --start

Release artifact staged:
  target_fetch_command=grit fetch grit-mipsel-linux-4.x-musl-default-full ...
  Target fetch options:
    wget:  wget --no-check-certificate -O ./grit-mipsel-linux-4.x-musl-default-full ...
    curl:  curl -fLk -o ./grit-mipsel-linux-4.x-musl-default-full ...
    nc:    requires file-service TLS=no; use wget/curl/grit, or set GRIT_OPERATOR_FILE_SERVICE_TLS=no
    grit:  grit fetch grit-mipsel-linux-4.x-musl-default-full ...
    run:   chmod +x ./grit-mipsel-linux-4.x-musl-default-full && ./grit-mipsel-linux-4.x-musl-default-full --help
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

In SSH transport mode, `grit-console --transport ssh` acts as an operator-side
Paramiko SSH server. The target runs dbclient and establishes a reverse
forward; the operator connects through the forwarded port:

```sh
scripts/grit-console --transport ssh   # operator side
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
scripts/lib/inspect-artifact dist/grit-native-full
scripts/lib/verify-artifact dist/grit-native-full
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
  grit-console         operator console and reverse-access server
  grit-console bringup guided first-contact and survey loop
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

Opt-in longer console coverage starts from the transcript-capable line console
workflow and is kept out of the default smoke path:

```sh
make unit-test
```

QEMU-backed coverage is intentionally opt-in and can be run separately:

```sh
make unit-test-qemu
make unit-test-all
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
