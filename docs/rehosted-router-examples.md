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
- `dlink-dir-300-a1-uclibc`: big-endian MIPS uClibc, binwalk reported Linux `2.4.25`
- `linksys-wrt54g-v5-ddwrt-uclibc`: little-endian MIPS uClibc, DD-WRT micro module dir `2.4.37`
- `netgear-wndr3700-v1-uclibc`: big-endian MIPS uClibc, module dir `2.6.15`

Build examples:

```sh
scripts/package-target tplink-archer-a7-v5-openwrt-uclibc
scripts/package-target tplink-archer-ax1800-v56-openwrt-musl
scripts/package-target asus-rt-n16-uclibc
scripts/package-target dlink-dir-615-revc-uclibc
scripts/package-target dlink-dir-300-a1-uclibc
scripts/package-target linksys-wrt54g-v5-ddwrt-uclibc
scripts/package-target netgear-wndr3700-v1-uclibc
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
- D-Link DIR-300 A1: QEMU mipseb started, root shell was exposed, and router services including HTTP, DHCP, DNS, telnet, and NEAPS were reported before timeout. Penguin reported the guest return code as `-11` after timeout shutdown, so treat this as a useful but unstable rehost smoke case.
- Linksys Gv5Flash DD-WRT micro: QEMU mipsel started, root shell was exposed, and the guest shut down cleanly before the 30-second timeout. The extracted DD-WRT rootfs is a kernel 2.4.37/uClibc coverage example for WRT54G v5/v6-class devices.
- Netgear WNDR3700 v1: QEMU mipseb started, root shell was exposed, and router services including DHCP, miniupnpd, dnsmasq, uhttpd, and Samba were reported before timeout.

Known non-rootfs inputs:

- `FW_WRT54Gv5v6_1.02.8.001_US_20091005.bin`: fw2tar did not find a Linux filesystem. This appears to be stock WRT54G v5/v6 firmware rather than a Linux rootfs image.
- `openwrt-18.06.1-ixp4xx-generic-zImage`: kernel image only; fw2tar did not find a root filesystem to rehost.

These are smoke-level rehosting checks, not full firmware validation. Use the
Penguin run logs under `local/testing/rehost/runs/` to refine configs for deeper
service testing.
