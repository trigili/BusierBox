# Payload Presets

Payload presets describe runtime behavior and staged payload tools. They do not
select the target architecture or libc; target presets and tuple fields do that.

Built-in payload presets live under `presets/payload/`:

| Preset | Purpose |
| --- | --- |
| `survey-core` | Core-only local survey; no extraction; no reverse access |
| `default` | Extract payload; help on zero-arg; no reverse access |
| `builtin-core-shell` | Core-only builtin TLS shell; zero-arg reverse access |
| `payload-bash` | Extract BusyBox plus bash; help on zero-arg; no reverse access |
| `socat-rescue` | No-residue socat TLS shell; stages socat |
| `ssh-operator` | Extract Dropbear/dbclient; explicit reverse SSH; no autorun |
| `full-debug` | Large debug/operator payload; no network autorun |

Each preset has a sidecar metadata file:

```text
presets/payload/<name>.meta.json
```

The metadata records the menu label, risk level, size hint, autorun behavior,
network behavior, external-write behavior, validated cases, and notes. The
shell `.conf` files remain the build input; the JSON sidecars are for operator
UX and documentation.

## User Presets

When `make menuconfig` detects that current payload settings differ from the
selected built-in preset, it offers to save those settings as a user preset.
User presets are written under:

```text
local/presets/payload/
```

Built-in presets are not modified by that flow.

## Safety Defaults

Built-in presets keep external writes disabled by default. Presets that make
reverse access available distinguish explicit launch from zero-arg autorun in
their metadata. `ssh-operator` stages Dropbear/dbclient but does not start
reverse SSH on zero-arg. `builtin-core-shell` and `socat-rescue` are the
reverse-access-oriented presets and should be selected only when that behavior
is intended.

## Validation

Local smoke coverage checks that built-in presets keep target tuple fields out
of payload config, include required metadata, and expose clear menu labels:

```sh
tests/smoke/payload-presets.sh
```
