# Artifact Runtime Overrides

BusierBox artifacts can carry an optional post-build override trailer. This
lets selected runtime/operator settings change after packaging without
recompiling the BusierBox core or rebuilding the payload.

```sh
scripts/artifact-config show dist/busierbox-native-full
scripts/artifact-config set dist/busierbox-native-full BB_OPERATOR_SERVER_HOST=203.0.113.10 BB_ZERO_ARG_MODE=rshell
scripts/artifact-config export dist/busierbox-native-full > overrides.env
scripts/artifact-config import dist/busierbox-native-full overrides.env
scripts/artifact-config clear dist/busierbox-native-full
```

Effective config precedence is compiled defaults, then valid trailer overrides,
then environment overrides for the same `BB_*` keys, then command-specific CLI
flags where an applet exposes them.

`busierbox config-info` reports trailer presence, validity, encoding, and
selected compiled/effective values. `busierbox runtime-config` and
`busierbox runtime-config --json` report the full allowlisted compiled config,
effective config, trailer metadata, environment override count, and
`effective_config_source` (`compiled`, `trailer`, `env`, or `cli`). `busierbox
runtime-config --json` also includes `noresidue_policy` and
`rshell_readiness`, matching the doctor/manifest safety and reverse-access
fields. `busierbox manifest --json` includes `compiled_config`,
`effective_config`, and `trailer_override`.

Allowed trailer keys are limited to runtime/operator behavior: runtime
mode/root, no-residue level (`best-effort` or `aggressive`), zero-arg
mode/logging, reverse-shell transport, operator host and ports, retry settings,
session policy (`single`, `reconnect`, or
`persistent`), shell provider, and autorun guard settings. Target tuple,
architecture, libc, kernel floor, static policy, compiled feature flags, heavy
tool selection, dotfiles, and overlay contents are intentionally rejected.
Trailer overrides can change whether rshell stops after one session, reconnects
for a bounded retry count, or keeps trying persistently, but cannot change target tuple compatibility
or add, remove, or replace payload contents. Rebuild the artifact when the target
tuple, BusyBox applets, heavy tools, dotfiles, overlays, or compiled features
need to change.

The trailer is fixed-size and appended at EOF with `BBXCONFIGv1` magic, version,
encoding, payload format, payload offset/size, SHA-256 of the decoded
`KEY=VALUE` payload, and optional XOR metadata. XOR payload bytes are stored as
ASCII-safe hex so trailer inspection never depends on raw binary payload bytes.

XOR obfuscation is only casual string hiding. It is not encryption, does not
protect secrets, and must not be used for private keys, passwords, or
credentials.
`scripts/artifact-config` and the runtime reject obvious secret-like trailer
values such as private-key PEM headers and `PASSWORD=`, `TOKEN=`, or
`PRIVATE_KEY=` assignments; keep credentials outside override trailers.
