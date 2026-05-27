# Heavy Tools Wishlist And Provider Triage

BusierBox separates standard Unix utilities from heavy tools. Standard tools should come from BusyBox or another upstream payload. Heavy tools need provider metadata because static builds, payload size, privileges, and target kernel features vary heavily.

Current classifications:

| Tool | Classification | Notes |
| --- | --- | --- |
| `gdbserver` | target payload, Buildroot/user/overlay providers | Prefer target-side `gdbserver` plus operator-side GDB/GEF. MIPS musl static Buildroot builds have known failures. |
| `gdb` | local-dropin/overlay or host-side | Full target GDB is large; prefer operator-side GDB. |
| GEF/pwndbg | host/operator-side | Requires Python and full GDB environment. |
| `nmap`, `nmap-ncat` | target payload if Buildroot support validates | `ncat` may overlap with BusyBox `nc`; do not duplicate by default. |
| `pstree`/psmisc | already partly covered | BusyBox has `pstree`; psmisc can be optional if needed. |
| `openssl` | target payload | Useful for diagnostics, large TLS surface. |
| `ripgrep` | already supported as `rg` when staged | Do not duplicate `ripgrep` and `rg`. |
| `fd`, `zoxide` | local-dropin/overlay first | Convenience tools, not debug-critical. |
| `mosh-client` | already represented as optional heavy tool | Validate static/dynamic constraints per target. |
| radare2/rizin | local-dropin/overlay only initially | Very heavy. |
| `gcore` | tied to GDB/provider | Prefer host-side workflow unless target GDB is selected. |
| `tshark` | local-dropin/overlay only initially | Very heavy and dependency-rich. |
| mtd-utils/ubi-utils/i2c-tools/spi-tools/mmc-utils/e2fsprogs/parted | dangerous storage/flash diagnostics | Hide behind explicit dangerous category; never default/full-debug by default. |

Provider metadata should record buildroot, local-dropin, overlay, host-only, disabled, known failures, approximate payload size, static/dynamic constraints, and required kernel capabilities.

Implemented provider hooks:

- `payloads/tool-compat.json` carries provider/classification metadata for the wishlist tools.
- `scripts/check-buildroot-tool-mappings` validates Buildroot symbols for supported target-payload tools and reports tools that require a target-compatible drop-in/user/overlay binary without failing non-strict checks.
- `scripts/gen-buildroot-defconfig` emits Buildroot package symbols for supported wishlist payloads.
- `scripts/menuconfig` exposes a clearly labeled dangerous storage/flash diagnostics category; none of those tools are selected by default presets.
- `doom` uses the BusierBox Buildroot `doom-ascii` package for static target builds. Set `BB_DOOM_WAD_PATH` to a local legally usable `.wad`; BusierBox records that path in the generated target profile and stages the file, but never fetches game data. Target packaging verifies that the staged `doom-ascii` ELF is static. BusierBox does not accept a user-provided Doom engine path for target payloads.

Provider-only tools such as full `gdb`, GEF/pwndbg, radare2/rizin, `gcore`, and `tshark` remain explicit local-dropin/overlay choices until a target tuple has validated package support.
