# Reverse Access Validation Report

Date: 2026-05-25
Branch: `reverse-access-hardening`

## What Changed

- Hardened SSH reverse-access filesystem policy so `disabled` and
  `payload-home` authkeys modes do not create or mutate `/root/.ssh`.
- Added rshell run modes, status/stop/restart lifecycle handling, retry
  settings, shell provider selection, and clearer reverse-access summaries.
- Improved builtin wolfSSL relay handling for handshake errors, EINTR,
  WANT_READ/WANT_WRITE, partial writes, EOF, hangups, child exit, and SIGPIPE.
- Added a repeatable GL.iNet integration harness at `scripts/lib/integration-glinet`.
- Added scripted shell support to `scripts/grit-console` for TLS/plain shell
  integration cases.
- Added local regression coverage for validation-matrix cases and retired
  stager/callback UX text.
- Added target presets and a local-only Penguin workflow for the router
  firmware examples under `local/testing/Routers`.

## Local Verification

Commands run:

```sh
tests/smoke/rehosted-router-presets.sh
make smoke-test
```

Relevant smoke coverage:

- `tests/smoke/validation-matrix.sh`
- `tests/smoke/menuconfig-validation.sh`
- `tests/smoke/rshell-external-writes.sh`
- `tests/smoke/rshell-lifecycle.sh`
- `tests/smoke/rshell-transport-names.sh`
- `tests/smoke/stale-ux-text.sh`
- `tests/smoke/integration-glinet-harness.sh`
- `tests/smoke/rehosted-router-presets.sh`

Result: `make smoke-test` passed.

## GL.iNet Verification

Target: `root@192.168.8.1`
Operator host: `192.168.8.241`
Target preset: `glinet-mt7621-openwrt-musl`

Commands run:

```sh
scripts/lib/integration-glinet --host root@192.168.8.1 --operator-host auto --all-safe --require-target
scripts/lib/integration-glinet --host root@192.168.8.1 --operator-host auto --case ssh-operator --require-target
scripts/lib/integration-glinet --host root@192.168.8.1 --operator-host auto --case socat-rescue --require-target --build-timeout 3600
```

Passing local evidence:

- `local/integration-runs/20260525-121043/summary.json`
  - `survey-core`: pass
  - `default-extract-help`: pass
  - `builtin-core-shell`: pass
  - `zero-arg-builtin`: pass
- `local/integration-runs/20260525-121650/summary.json`
  - `ssh-operator`: pass
- `local/integration-runs/20260525-124828/summary.json`
  - `socat-rescue`: pass

The integration logs are intentionally under ignored `local/` paths because they
include built artifacts, generated configs, target transcripts, and router-local
runtime details.

## Rehosted Router Examples

Firmware inputs remained under `local/testing/Routers`, which is ignored by git.
Generated rootfs archives, Penguin projects, and run logs stayed under
`local/testing/rehost`.

Command run:

```sh
scripts/lib/rehost-router-examples --all --force --timeout 30
```

Observed local Penguin runs:

- Archer A7: QEMU mipseb started, root shell exposed, OpenWrt-style init ran
  until timeout.
- Archer AX1800: QEMU armel started, root shell exposed, init ran, and guest UDP
  service binds were reported.
- ASUS RT-N16: QEMU mipsel started, root shell exposed, router services including
  HTTP and dnsmasq came up.
- D-Link DIR-615 RevC: QEMU mipseb started, root shell exposed, HTTP/DHCP-related
  services came up, and the guest shut down before timeout.

Tracked griTTYkit target presets derived from those images:

- `tplink-archer-a7-v5-openwrt-uclibc`
- `tplink-archer-ax1800-v56-openwrt-musl`
- `asus-rt-n16-uclibc`
- `dlink-dir-615-revc-uclibc`
- `dlink-dir-300-a1-uclibc`
- `linksys-wrt54g-v5-ddwrt-uclibc`
- `netgear-wndr3700-v1-uclibc`

## Remaining Limitations

- PTY support is not claimed for builtin TLS; the relay is pipe-backed.
- `GRIT_RSHELL_SESSION_POLICY` distinguishes single-shot, reconnect, and
  persistent lifecycle behavior. Reconnect and persistent modes create fresh
  shell sessions after disconnect; session resume is not claimed. SSH
  reverse-forward mode supervises `dbclient` under the rshell guard path so
  post-disconnect behavior follows the selected policy instead of relying on an
  unmanaged one-shot worker.
- No-residue cleanup remains best-effort.
- Root-writing authkeys modes are reserved behind explicit integration flags and
  are not part of the default safe GL.iNet run.
- The Penguin router examples are smoke-level rehosting examples. Deeper service
  validation should use the local Penguin project logs and configs as the next
  refinement point.
