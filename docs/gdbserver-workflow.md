# gdbserver Workflow

BusierBox treats target-side `gdbserver` as a provider-based payload tool. It
keeps Buildroot support where that works, but for known-problem tuples such as
mipsel/mips musl static builds, the preferred path is a local drop-in, user
binary, or overlay.

## Local Drop-Ins

Search order:

```text
local/tools/<target-name>/bin/gdbserver
local/tools/<arch>-<libc>/bin/gdbserver
local/tools/generic/<arch>/bin/gdbserver
```

Install a binary:

```sh
scripts/tools/install-dropin-gdbserver --source ./gdbserver --target mipsel-linux-4.x-musl
```

Check a binary:

```sh
scripts/tools/check-dropin-tool --tool gdbserver --path local/tools/mipsel-linux-4.x-musl/bin/gdbserver --arch mipsel --libc musl
```

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
