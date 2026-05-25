# Rehosted Router Examples

BusierBox includes target presets derived from local firmware rehosting work.
The firmware images themselves are not part of the repository and must stay
under `local/`, for example through `local/testing/Routers`.

## Local Workflow

List the expected local firmware inputs:

```sh
scripts/rehost-router-examples --list
```

Extract root filesystems, create Penguin projects, and run short automatic
rehosting checks:

```sh
scripts/rehost-router-examples --all --force --timeout 30
```

Generated files stay under `local/testing/rehost/`:

- `rootfs/<slug>/`: fw2tar rootfs archives and extractor logs
- `projects/<slug>/`: Penguin project directories and `config.yaml`
- `runs/<slug>/auto-<sec>s/`: Penguin run logs such as `console.log`

Do not copy firmware, rootfs archives, Penguin base files, or run outputs into
tracked paths.

## Derived Target Presets

The following presets are in `targets/presets.json`:

- `tplink-archer-a7-v5-openwrt-uclibc`: big-endian MIPS32r2 uClibc, module dir `3.3.8`
- `tplink-archer-ax1800-v56-openwrt-musl`: ARM EABI musl, OpenWrt target `board_ipq50xx/generic`, module dir `4.4.60`
- `asus-rt-n16-uclibc`: little-endian MIPS uClibc, module dir `2.6.22.19`
- `dlink-dir-615-revc-uclibc`: big-endian MIPS uClibc, conservative `2.6` tuple because the rootfs contains multiple legacy module dirs

Build examples:

```sh
scripts/package-target tplink-archer-a7-v5-openwrt-uclibc
scripts/package-target tplink-archer-ax1800-v56-openwrt-musl
scripts/package-target asus-rt-n16-uclibc
scripts/package-target dlink-dir-615-revc-uclibc
```

## Rehosting Evidence

On May 25, 2026, the local images in `local/testing/Routers` were extracted with
`fw2tar`, initialized with Penguin v3.0.12, and run with `penguin run --timeout
30 -a`.

Observed results:

- Archer A7: QEMU mipseb started, root shell was exposed at `192.168.0.2:23`, and OpenWrt-style init ran until the 30-second timeout.
- Archer AX1800: QEMU armel started, root shell was exposed, init ran, and guest UDP services were reported before timeout.
- ASUS RT-N16: QEMU mipsel started, root shell was exposed, ASUS init brought up router services including HTTP and dnsmasq before timeout.
- D-Link DIR-615 RevC: QEMU mipseb started, root shell was exposed, init brought up HTTP/DHCP-related services, and the guest shut down before the 30-second timeout.

These are smoke-level rehosting checks, not full firmware validation. Use the
Penguin run logs under `local/testing/rehost/runs/` to refine configs for deeper
service testing.
