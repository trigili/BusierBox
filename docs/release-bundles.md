# Release Bundles

`scripts/make-release` builds or assembles a set of BusierBox artifacts into a
reusable release directory and tarball under `dist/releases/`.

Examples:

```sh
scripts/make-release --name lab-router-pack
scripts/make-release --name lab-router-pack --targets glinet-mt7621-openwrt-musl,mipsel-linux-4.x-musl --payload-presets survey-core,ssh-operator
scripts/make-release --name lab-router-pack --reverse-access-profiles builtin,ssh
scripts/make-release --name lab-router-pack --matrix release/matrices/iot-lab.json
scripts/make-release --name lab-router-pack --dry-run
```

Each release contains:

- `bin/`: built artifacts and per-artifact SHA256 files.
- `configs/`: generated per-target/per-preset configs.
- `manifests/`: artifact manifest/config-info output when available.
- `scripts/`: copied `artifact-config` plus wrapper helpers.
- `docs/`: release and runtime override notes.
- `release.json`: build status, commit, safe build-host metadata, source-lock summary, selected matrix, artifact paths, checksums, and failures.
- `SHA256SUMS.original`: pristine bundle checksums.

Matrix files can include a `configs` list. Each listed config is used as a
base config for every selected target/payload/format combination, and
`scripts/make-release` writes generated per-combination configs under
`configs/` without modifying the source config.

Reverse-access profiles are explicit opt-in selectors for existing payload
presets: `builtin` maps to `builtin-core-shell`, `ssh` maps to `ssh-operator`,
and `socat` maps to `socat-rescue`. They can be supplied with
`--reverse-access-profiles` or as `reverse_access_profiles` in a matrix file.

Trailer configuration after packaging:

```sh
scripts/configure-artifact bin/busierbox-native-default-full \
  --operator-host 192.168.8.241 \
  --transport builtin \
  --shell-port 22203 \
  --zero-arg-mode rshell

scripts/configure-all \
  --operator-host 192.168.8.241 \
  --transport builtin \
  --shell-port 22203
```

The helper scripts wrap the bundled `scripts/artifact-config`. They can show,
clear, import, export, and set allowlisted trailer keys. After a trailer edit,
they write `SHA256SUMS.configured` and update `SHA256SUMS` to match the current
configured bundle.

XOR trailer obfuscation is not encryption. Do not place credentials, private
keys, or other secrets in trailer overrides or release bundles.

Trailer overrides can adjust selected runtime/operator settings such as
operator host, ports, transport, run mode, zero-arg mode, and log verbosity.
They cannot change target architecture, libc, kernel floor, static policy,
payload tools, heavy tools, dotfiles, overlays, or compiled features.

Release tooling does not enable network autorun or external writes by default.
Use payload presets and trailer overrides deliberately, and verify the resulting
bundle with:

```sh
scripts/verify-checksums --original
scripts/verify-checksums --configured
```
