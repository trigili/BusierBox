# Artifact Manifest

`busierbox manifest` explains what an artifact is:

```sh
busierbox manifest
busierbox manifest --json
```

The JSON manifest includes:

- schema version
- payload version and artifact tier
- runtime mode/root/fallback settings
- zero-arg mode and log mode
- rshell transport, encryption, run mode, and shell provider
- native feature flags
- BusyBox applets and staged heavy tools compiled into the dispatch table

The extracted payload also carries `payload/manifest.json`, produced during packaging. That payload manifest records requested tools, staged tools, missing tools, overlay metadata, gdbserver provider state, BusyBox applets, and payload hashes.

Integration runs capture manifest output next to the case logs so each validation run can be tied back to the artifact and preset that produced it.

Payload preset metadata lives next to each built-in preset as
`presets/payload/<name>.meta.json`. These sidecars describe the preset's
operator-facing purpose, risk level, network behavior, external-write behavior,
validated cases, and notes without changing the shell config format consumed by
the build scripts.
