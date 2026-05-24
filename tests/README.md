# BusierBox Integration Tests

The test harness is layered so developers can get useful signal without proprietary firmware, large committed images, or special infrastructure.

## Layers

`make smoke-test` builds `dist/busierbox-native`, runs `scripts/verify-artifact` on it, runs the native host binary, and validates the Tier 0 applet contract. It also checks target tuple resolution, generated mipsel musl Buildroot config creation, payload manifest reality for missing tools, placeholder regression, `survey --json` parsing, `scripts/config-from-survey`, and copy-only self-extraction outside the repository.

`make test-qemu-user` runs target binaries under qemu-user when both the target binary and qemu interpreter exist. Missing cross binaries or interpreters are reported as `SKIP`, not as hard failures. This layer validates ELF compatibility, basic syscall compatibility, and applet behavior.

`make test-qemu-system` boots locally supplied Buildroot/OpenWrt-style QEMU environments when enabled in `tests/matrix/environments.example.json`. All entries are disabled by default and no kernel/rootfs images are committed. Missing QEMU binaries, kernels, rootfses, or BusierBox binaries are reported as `SKIP`.

`make test-glinet` runs the real-device GL.iNet MT7621 integration harness against `root@192.168.8.1` by default. It builds the configured artifact unless `SKIP_BUILD=1`, serves it over a temporary local HTTP server, downloads it on the router, runs extraction and doctor checks, validates PATH and BusyBox applet symlinks, and checks staged tools such as zsh, tmux, curl, and strace when present.

`make test-all` runs the local smoke and QEMU layers. Real-device GL.iNet testing is kept as an explicit `make test-glinet` target because it depends on reachable hardware.

## Smoke Contract

Every backend runs the same Tier 0 smoke contract:

```sh
./busierbox list
./busierbox list --plain
./busierbox --help
./busierbox survey
./busierbox survey --json > survey.json
./busierbox envfix
./busierbox extract
./busierbox doctor
./busierbox sh -c 'echo ok'
./busierbox cp --help
./busierbox dd --help
./busierbox nc --help
./busierbox config-info
./busierbox uname -a
./busierbox id
./busierbox df .
./busierbox free || true
./busierbox ps || true
```

`tests/smoke/validate-survey-json.py` requires `survey.json` to contain:

- `arch`
- `kernel`
- `writable_dirs`
- `recommendations`

`scripts/config-from-survey` then converts the JSON into compatibility-oriented build settings such as target arch, endian, kernel floor, payload mode viability, extract directory, and whether Tier 1 tools like tmux/strace/gdbserver look appropriate.

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

Each entry names the expected self-extracting BusierBox binary under `dist/` and the qemu-user interpreter. Add new generated targets by adding or editing a preset in `targets/presets.json` when useful, ensuring `scripts/gen-buildroot-defconfig` supports the tuple, producing `dist/busierbox-<target>`, running `scripts/inspect-artifact` and `scripts/verify-artifact`, and adding a matrix entry with `name`, `arch`, `binary`, and `qemu_user`.

## QEMU User

Run:

```sh
make test-qemu-user
```

The runner prefers `qemu-*-static` but also accepts non-static qemu-user binaries when available. For the host profile it runs `dist/busierbox-native` directly with `qemu_user` set to `native`. Normal qemu-user tests copy only the self-extracting BusierBox artifact, not a separate payload archive.

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
3. Build the matching BusierBox binary under `dist/`.
4. Update the environment entry paths and set `enabled` to `true`.
5. Tune `qemu_machine`, `qemu_cpu`, and `append_args` for the generated image.

The runner uses serial-console-only operation. For enabled environments it creates a small host payload directory containing the matching BusierBox binary and smoke scripts, exposes it with QEMU 9p using the `busierbox_payload` mount tag, boots with `init=/bin/sh`, mounts the payload from the serial shell, runs the smoke contract, and copies payload artifacts back to:

```text
tests/artifacts/qemu-system/<environment>/
```

Some boards or generated rootfses may need a different disk interface than the default `if=virtio`; adjust the runner or matrix when adding that environment.

## GL.iNet Real Device

Run:

```sh
make test-glinet
```

Useful overrides:

```sh
ROUTER=root@192.168.8.1 make test-glinet
SKIP_BUILD=1 ARTIFACT=dist/busierbox-mipsel-linux-4.x-musl tests/integration/glinet/push-and-test
KEEP_ARTIFACTS=1 tests/integration/glinet/push-and-test dist/busierbox-mipsel-linux-4.x-musl
```

The default remote directory is `/tmp/busierbox-itest`, which avoids the small persistent root filesystem on many OpenWrt-style devices. Override `REMOTE_DIR` only when that location has enough free space for the artifact plus extraction. The harness fails loudly for missing advertised tools, missing applet symlinks, broken extraction, duplicate payload PATH entries, zsh without payload commands, and overlay tool drift.

## Environment Coverage

Use Buildroot/OpenWrt configs to simulate constraints BusierBox cares about:

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

Survey JSON is treated as compatibility data. It feeds `scripts/config-from-survey`, which prints recommended build settings:

```sh
scripts/config-from-survey tests/artifacts/qemu-user/native/survey.json
```

This keeps target observations separate from build policy and makes later SDK selection reproducible.
