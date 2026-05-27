# gdbserver Workflow

BusierBox treats target-side `gdbserver` as a provider-based payload tool. It
keeps Buildroot support where that works, but for known-problem tuples such as
mipsel/mips musl static builds, the preferred path is a local drop-in, user
binary, or overlay.

`gdbserver` is a staged heavy tool. It dispatches from `payload/bin/gdbserver`
after full payload extraction, not from the native BusierBox supervisor and not
through BusyBox.

## Local Drop-Ins

Search order:

```text
local/tools/<target-name>/bin/gdbserver
local/tools/<arch>-<libc>/bin/gdbserver
local/tools/generic/<arch>/bin/gdbserver
```

Install a binary:

```sh
scripts/tools/install-dropin-gdbserver --source ./gdbserver --target mipsel-linux-4.x-musl --strict
```

Check a binary:

```sh
scripts/tools/check-dropin-tool --tool gdbserver --path local/tools/mipsel-linux-4.x-musl/bin/gdbserver --arch mipsel --libc musl
```

The checker prints executable, ELF, dynamic-linker, warning, and `sha256`
metadata. Add `--metadata-out local/tools/mipsel-linux-4.x-musl/bin/metadata.json`
to write the same inspection result as JSON without installing the file. Use
`--strict` when installing or checking a final drop-in so detected
architecture/endian mismatches fail instead of becoming payload content. For
non-native target drop-ins, strict mode also rejects files whose architecture
cannot be identified.

Set `BB_GDBSERVER_PROVIDER="local-dropin"` or leave it as `auto`.

## Operator Workspace

Generate a local GDB workspace from survey, manifest, or config data:

```sh
scripts/busierbox-gdb-workspace \
  --survey local/bringup-runs/example/survey.json \
  --manifest local/bringup-runs/example/manifest.json \
  --host 127.0.0.1 --port 31337 --binary ./target-program
```

Target side:

```sh
busierbox gdbserver :31337 /path/to/binary
```

Operator side:

```sh
gdb-multiarch -x local/gdb-workspaces/example/connect.gdb ./target-program
```

GEF and pwndbg are operator-side GDB plugins in this workflow. Do not bundle
them onto small targets unless target-side full GDB plus Python has been
explicitly selected and validated.

## GL.iNet / mipsel-musl Caveat

Buildroot GDB/BFD is known to fail for some mipsel/mips musl static builds.
BusierBox pre-excludes that Buildroot provider in best-effort mode and reports a
warning instead of turning package generation into a surprise build failure.

## Troubleshooting

- Confirm ptrace is allowed on the target.
- Confirm the debug port is reachable or forwarded.
- If the drop-in is dynamic, ensure the target has the interpreter and shared
  libraries reported by `check-dropin-tool`.
- Use `file` or `readelf -h` to confirm architecture and endian match.
