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
then environment overrides for the same `BB_*` keys.

`busierbox config-info` reports trailer presence and validity plus selected
compiled/effective values. `busierbox manifest --json` includes
`compiled_config`, `effective_config`, and `trailer_override`.

Allowed trailer keys are limited to runtime/operator behavior: runtime
mode/root, zero-arg mode/logging, reverse-shell transport, operator host and
ports, retry settings, shell provider, and autorun guard settings. Target tuple,
architecture, libc, kernel floor, static policy, compiled feature flags, heavy
tool selection, dotfiles, and overlay contents are intentionally rejected.

The trailer is fixed-size and appended at EOF with `BBXCONFIGv1` magic, version,
encoding, payload offset/size, SHA-256 of the decoded `KEY=VALUE` payload, and
optional XOR metadata.

XOR obfuscation is only casual string hiding. It is not encryption, does not
protect secrets, and must not be used for private keys, passwords, or
credentials.
