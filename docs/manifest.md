# Artifact Manifest

`grit manifest` explains what an artifact is:

```sh
grit manifest
grit manifest --json
grit manifest --json --include-missing
grit manifest --base64
grit doctor --json
grit doctor --json --include-missing
```

The JSON manifest includes:

- schema version
- payload version, artifact tier, build timestamp, and git commit when available
- target preset/name and target arch/endian/cpu/abi/libc/kernel/static policy
- payload preset and gdbserver provider
- runtime mode, no-residue level, no-residue policy summary, root, and fallback settings
- zero-arg mode and log mode
- rshell transport, encryption, run mode, and shell provider
- command-queue policy, interval polling settings, daemon state support, and
  mode records/indexes for status/poll/once/daemon/stop behavior
- dotfile modes and user overlay policy
- artifact licensing posture: griTTYkit GPL license, combined GPLv2
  compatibility, BusyBox fork boundary, and third-party component license
  inventory for BusyBox, Buildroot, doom-ascii, and miniz
- native feature flags
- BusyBox applets and staged heavy tools compiled into the dispatch table
- compiled config, effective config, and post-build override trailer status
- flat config records with lookup maps and `api_collections.config_records`
  metadata (`count`, `summary_key`, `count_summary_key`, `primary_key`, and
  index names)

Artifact-facing manifest and doctor output are positive inventory by default:
they describe what is present and usable. They do not list every requested or
unavailable payload tool unless `--include-missing` is supplied. Release
bundles keep broader builder-facing negative inventory in explicit
`build-report.json` / `*.build-missing.json` reports when
`scripts/make-release --include-missing-reports` is used.

Extraction writes the artifact manifest to
`./.grit/manifest/artifact.json` next to the runtime payload. The extracted
payload also carries `payload/manifest.json`, produced during packaging. That
payload manifest records requested tools, staged tools, missing tools, overlay
metadata, staged Doom WAD basenames/sizes/hashes, gdbserver provider state, structured provider status under
`tool_provider_status`, BusyBox applets, and payload hashes. For provider-backed
tools such as `gdbserver`, the status records the searched local drop-in paths,
checker output, executable state, and installed metadata so release bundles can
audit what provider path was available when the artifact was built.

Runtime extraction state is intentionally reported by runtime diagnostics rather
than the compiled manifest. `grit config-info` and `grit doctor
--json` report `payload_extraction_mode` / `extraction_mode` as `core` or
`full`. BusyBox applet dispatch may create a core payload containing
`payload/bin/busybox` and metadata only; `grit extract` and heavy-tool
dispatch upgrade that runtime root to full before use.
`grit config-info` also prints `noresidue_policy_*` fields that mirror the
manifest/doctor safety boundary: cleanup is best-effort, scoped to
griTTYkit-owned runtime roots and ledgered files, external writes require
explicit apply, and no mode claims forensic no-trace behavior.

griTTYkit is not a BusyBox fork. Native griTTYkit applets are compiled into the
supervisor. BusyBox applets dispatch through `payload/bin/busybox`, while heavy
tools dispatch through `payload/bin/<tool>` after full extraction.

Integration runs capture manifest output next to the case logs so each validation run can be tied back to the artifact and preset that produced it.

Post-build runtime override trailers are edited with
`scripts/lib/artifact-config`. They can change selected runtime/operator settings
without rebuilding and appear under `trailer_override`, `compiled_config`,
`effective_config`, `config_records`, and the `config_records_by_*` lookup maps
in `manifest --json`. See
[Artifact runtime overrides](artifact-runtime-overrides.md).

Payload preset metadata lives next to each built-in preset as
`presets/payload/<name>.meta.json`. These sidecars describe the preset's
operator-facing purpose, risk level, network behavior, external-write behavior,
validated cases, and notes without changing the shell config format consumed by
the build scripts.

## Config Export

`grit config-export` wraps the artifact manifest in a rebuild-oriented JSON
document:

```sh
grit config-export --json
grit config-export --base64
```

On a build host, convert manifest or config-export JSON back into a shell config
starter:

```sh
grit config-export --json > artifact-config.json
scripts/lib/config-from-manifest artifact-config.json > recovered.conf
```

The recovered config includes target, payload preset, selected heavy tools,
gdbserver provider, runtime, zero-arg, rshell, dotfile, and overlay metadata. It
intentionally does not include private keys or local operator secret material.

## Support Token

`grit doctor --support-token` emits a single base64-encoded JSON token with
the artifact manifest embedded:

```sh
grit doctor --support-token > support.token
scripts/lib/config-from-support-token "$(cat support.token)" > recovered.conf
```

The token may include configured operator hostnames and ports. It does not embed
private key material.
