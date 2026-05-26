# Artifact Manifest

`busierbox manifest` explains what an artifact is:

```sh
busierbox manifest
busierbox manifest --json
busierbox manifest --json --include-missing
busierbox manifest --base64
busierbox doctor --json
busierbox doctor --json --include-missing
```

The JSON manifest includes:

- schema version
- payload version, artifact tier, build timestamp, and git commit when available
- target preset/name and target arch/endian/cpu/abi/libc/kernel/static policy
- payload preset and gdbserver provider
- runtime mode, no-residue level, root, and fallback settings
- zero-arg mode and log mode
- rshell transport, encryption, run mode, and shell provider
- dotfile modes and user overlay policy
- native feature flags
- BusyBox applets and staged heavy tools compiled into the dispatch table
- compiled config, effective config, and post-build override trailer status

Artifact-facing manifest and doctor output are positive inventory by default:
they describe what is present and usable. They do not list every requested or
unavailable payload tool unless `--include-missing` is supplied. Release
bundles keep broader builder-facing negative inventory in explicit
`build-report.json` / `*.build-missing.json` reports when
`scripts/make-release --include-missing-reports` is used.

Extraction writes the artifact manifest to
`./.busierbox/manifest/artifact.json` next to the runtime payload. The extracted
payload also carries `payload/manifest.json`, produced during packaging. That
payload manifest records requested tools, staged tools, missing tools, overlay
metadata, gdbserver provider state, BusyBox applets, and payload hashes.

Runtime extraction state is intentionally reported by runtime diagnostics rather
than the compiled manifest. `busierbox config-info` and `busierbox doctor
--json` report `payload_extraction_mode` / `extraction_mode` as `core` or
`full`. BusyBox applet dispatch may create a core payload containing
`payload/bin/busybox` and metadata only; `busierbox extract` and heavy-tool
dispatch upgrade that runtime root to full before use.

BusierBox is not a BusyBox fork. Native BusierBox applets are compiled into the
supervisor. BusyBox applets dispatch through `payload/bin/busybox`, while heavy
tools dispatch through `payload/bin/<tool>` after full extraction.

Integration runs capture manifest output next to the case logs so each validation run can be tied back to the artifact and preset that produced it.

Post-build runtime override trailers are edited with
`scripts/artifact-config`. They can change selected runtime/operator settings
without rebuilding and appear under `trailer_override`, `compiled_config`, and
`effective_config` in `manifest --json`. See
[Artifact runtime overrides](artifact-runtime-overrides.md).

Payload preset metadata lives next to each built-in preset as
`presets/payload/<name>.meta.json`. These sidecars describe the preset's
operator-facing purpose, risk level, network behavior, external-write behavior,
validated cases, and notes without changing the shell config format consumed by
the build scripts.

## Config Export

`busierbox config-export` wraps the artifact manifest in a rebuild-oriented JSON
document:

```sh
busierbox config-export --json
busierbox config-export --base64
```

On a build host, convert manifest or config-export JSON back into a shell config
starter:

```sh
busierbox config-export --json > artifact-config.json
scripts/config-from-manifest artifact-config.json > recovered.conf
```

The recovered config includes target, payload preset, selected heavy tools,
gdbserver provider, runtime, zero-arg, rshell, dotfile, and overlay metadata. It
intentionally does not include private keys or local operator secret material.

## Support Token

`busierbox doctor --support-token` emits a single base64-encoded JSON token with
the artifact manifest embedded:

```sh
busierbox doctor --support-token > support.token
scripts/config-from-support-token "$(cat support.token)" > recovered.conf
```

The token may include configured operator hostnames and ports. It does not embed
private key material.
