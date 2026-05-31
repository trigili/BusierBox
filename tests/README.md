# griTTYkit Integration Tests

The test harness is layered so developers can get useful signal without proprietary firmware, large committed images, or special infrastructure.

## Layers

`make smoke-test` builds `dist/grit-native-full`, runs `scripts/lib/verify-artifact`, runs the native host binary, and validates the Tier 0 applet contract. It also checks artifact tier behavior, target tuple resolution, generated mipsel musl Buildroot config creation, payload manifest reality for missing tools, placeholder regression, menuconfig serialization, reverse-access server CLI behavior, `survey --json` parsing, `scripts/lib/config-from-survey`, and copy-only self-extraction outside the repository.

`make test-qemu-user` runs target binaries under qemu-user when both the target binary and qemu interpreter exist. Missing cross binaries or interpreters are reported as `SKIP`, not as hard failures. This layer validates ELF compatibility, basic syscall compatibility, and applet behavior.
The runner writes `tests/artifacts/qemu-user/summary.txt` and
`tests/artifacts/qemu-user/summary.json`; the JSON form includes per-target
records, `status_counts`, and lookup maps for reports and dashboards.

`make test-qemu-system` boots locally supplied Buildroot/OpenWrt-style QEMU environments when enabled in `tests/matrix/environments.example.json`. All entries are disabled by default and no kernel/rootfs images are committed. Missing QEMU binaries, kernels, rootfses, or griTTYkit binaries are reported as `SKIP`.
The system runner mirrors the same text and JSON summary files under
`tests/artifacts/qemu-system/`.

`tests/smoke/qemu-matrix.sh` is the cheap metadata gate for the QEMU layer. It validates that the committed qemu-user matrix keeps host, x86, ARM, AArch64, little-endian MIPS, big-endian MIPS, musl, uClibc, and old/current kernel-floor coverage, and that the qemu-system example matrix keeps representative disabled environments with boot metadata plus architecture, libc, endian, and kernel-floor coverage.

`make test-all` runs the local smoke and QEMU layers. Real-device testing is
kept outside the default test path because it depends on reachable hardware and
site-specific network setup.

## Smoke Contract

Every backend runs the same Tier 0 smoke contract:

```sh
./grit list
./grit list --plain
./grit --help
./grit survey
./grit survey --json > survey.json
./grit envfix
./grit extract
./grit doctor
./grit sh -c 'echo ok'
./grit cp --help
./grit dd --help
./grit nc --help
./grit config-info
./grit uname -a
./grit id
./grit df .
./grit free || true
./grit ps || true
```

`tests/smoke/validate-survey-json.py` requires `survey.json` to contain:

- `arch`
- `kernel`
- `writable_dirs`
- `recommendations`

`scripts/lib/config-from-survey` then converts the JSON into compatibility-oriented build settings such as target arch, endian, kernel floor, payload mode viability, extract directory, and whether Tier 1 tools like tmux/strace/gdbserver look appropriate. Survey fixtures include modern OpenWrt, low-storage unknown targets, ancient MIPS/uClibc 2.4, and big-endian MIPS/uClibc 2.6 cases so compatibility scoring stays conservative across old router classes.

## Target Matrix

Representative qemu-user targets live in `tests/matrix/targets.example.json`:

- mipsel router class: `mipsel-linux-2.6-uclibc`
- OpenWrt-style MIPS little-endian musl: `mipsel-linux-4.x-musl`
- MIPS big-endian router class: `mips-linux-2.6-uclibc`
- ARMv5 EABI: `armv5-linux-2.6-uclibc-eabi`
- ARMv7 hardfloat: `armv7-linux-3.x-musl`
- AArch64: `aarch64-linux-4.x-musl`
- x86: `i386-linux-2.6-musl`
- host/native: `native`

Each entry names the expected self-extracting griTTYkit binary under `dist/` and the qemu-user interpreter. Add new generated targets by adding or editing a preset in `targets/presets.json` when useful, ensuring `scripts/lib/gen-buildroot-defconfig` supports the tuple, producing `dist/grit-<target>-full`, running `scripts/lib/check-buildroot-tool-mappings`, `scripts/lib/inspect-artifact`, and `scripts/lib/verify-artifact`, and adding a matrix entry with `name`, `arch`, `binary`, and `qemu_user`.

## QEMU User

Run:

```sh
make test-qemu-user
```

The runner prefers `qemu-*-static` but also accepts non-static qemu-user binaries when available. For the host profile it runs `dist/grit-native-full` directly with `qemu_user` set to `native`. Normal qemu-user tests copy only the self-extracting griTTYkit artifact, not a separate payload archive.

Artifacts are written to:

```text
tests/artifacts/qemu-user/<target>/
```

Typical files include `survey.json`, `recommended-config.txt`, `config-info.stdout`, extraction logs, per-command stdout/stderr, `status.txt`, and `summary.txt`.

## QEMU System

Run:

```sh
make test-qemu-system
```

Environment definitions live in `tests/matrix/environments.example.json`. All are disabled by default. To add a Buildroot or OpenWrt environment:

1. Generate a minimal kernel and rootfs outside this repository.
2. Place or symlink the kernel/rootfs under `tests/qemu-system/rootfs/<env>/`.
3. Build the matching griTTYkit binary under `dist/`.
4. Update the environment entry paths and set `enabled` to `true`.
5. Tune `qemu_machine`, `qemu_cpu`, and `append_args` for the generated image.

The runner uses serial-console-only operation. For enabled environments it creates a small host payload directory containing the matching griTTYkit binary and smoke scripts, exposes it with QEMU 9p using the `grit_payload` mount tag, boots with `init=/bin/sh`, mounts the payload from the serial shell, runs the smoke contract, and copies payload artifacts back to:

```text
tests/artifacts/qemu-system/<environment>/
```

Some boards or generated rootfses may need a different disk interface than the default `if=virtio`; adjust the runner or matrix when adding that environment.

## Environment Coverage

Use Buildroot/OpenWrt configs to simulate constraints griTTYkit cares about:

- tiny `/tmp`
- noexec mounts
- missing `/dev/pts`
- limited `PATH`
- missing or late-mounted procfs
- old syscall surfaces
- big-endian and little-endian MIPS
- ARMv5 softfloat and ARMv7 hardfloat

Do not commit generated kernels, rootfs images, firmware, or proprietary dumps. Keep large assets local or ship them as explicit release/test artifacts outside the source repository.

## Survey Data

Survey JSON is treated as compatibility data. It feeds `scripts/lib/config-from-survey`, which prints recommended build settings:

```sh
scripts/lib/config-from-survey tests/artifacts/qemu-user/native/survey.json
```

This keeps target observations separate from build policy and makes later SDK selection reproducible.
