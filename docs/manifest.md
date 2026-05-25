# Artifact Manifest

`busierbox manifest` explains what an artifact is:

```sh
busierbox manifest
busierbox manifest --json
busierbox manifest --base64
```

The JSON manifest includes:

- schema version
- payload version, artifact tier, build timestamp, and git commit when available
- target preset/name and target arch/endian/cpu/abi/libc/kernel/static policy
- payload preset
- runtime mode/root/fallback settings
- zero-arg mode and log mode
- rshell transport, encryption, run mode, and shell provider
- dotfile modes and user overlay policy
- native feature flags
- BusyBox applets and staged heavy tools compiled into the dispatch table

Extraction writes the artifact manifest to
`./.busierbox/manifest/artifact.json` next to the runtime payload. The extracted
payload also carries `payload/manifest.json`, produced during packaging. That
payload manifest records requested tools, staged tools, missing tools, overlay
metadata, gdbserver provider state, BusyBox applets, and payload hashes.

Integration runs capture manifest output next to the case logs so each validation run can be tied back to the artifact and preset that produced it.

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

The recovered config includes target, payload preset, runtime, zero-arg,
rshell, dotfile, and overlay metadata. It intentionally does not include private
keys or local operator secret material.

## Support Token

`busierbox doctor --support-token` emits a single base64-encoded JSON token with
the artifact manifest embedded:

```sh
busierbox doctor --support-token > support.token
scripts/config-from-support-token "$(cat support.token)" > recovered.conf
```

The token may include configured operator hostnames and ports. It does not embed
private key material.
