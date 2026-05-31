#!/bin/sh
set -eu

menu=${1:-scripts/menuconfig}
preset_dir=${2:-presets/payload}

[ -f "$menu" ] || {
    printf '%s\n' "payload-presets: missing $menu" >&2
    exit 1
}
[ -d "$preset_dir" ] || {
    printf '%s\n' "payload-presets: missing $preset_dir" >&2
    exit 1
}

for name in default survey-core builtin-core-shell payload-bash socat-rescue ssh-operator full-debug; do
    file="$preset_dir/$name.conf"
    [ -f "$file" ] || {
        printf '%s\n' "payload-presets: missing $file" >&2
        exit 1
    }
    if grep -q '^GRIT_TARGET_\|^GRIT_TARGETS=\|^GRIT_KERNEL_FLOOR=' "$file"; then
        printf '%s\n' "payload-presets: target tuple variable found in $file" >&2
        exit 1
    fi
    grep -q '^GRIT_RUNTIME_MODE=' "$file"
    grep -q '^GRIT_ZERO_ARG_MODE=' "$file"
    grep -q '^GRIT_TRAILER_OVERRIDES_ENABLE=' "$file"
    grep -q '^GRIT_RSHELL_TRANSPORT=' "$file"
    grep -q '^GRIT_RSHELL_RUN_MODE=' "$file"
    grep -q '^GRIT_RSHELL_SESSION_POLICY=' "$file"
    grep -q '^GRIT_HEAVY_TOOLS=' "$file"
    meta="$preset_dir/$name.meta.json"
    [ -f "$meta" ] || {
        printf '%s\n' "payload-presets: missing $meta" >&2
        exit 1
    }
    python3 - "$name" "$meta" <<'PY'
import json
import sys

name, path = sys.argv[1:]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
required = [
    "schema",
    "name",
    "description",
    "menu_label",
    "risk_level",
    "size_hint",
    "autorun",
    "network_behavior",
    "external_write_behavior",
    "validated_cases",
    "notes",
]
missing = [key for key in required if key not in data]
if missing:
    raise SystemExit(f"{path}: missing {', '.join(missing)}")
if data["name"] != name:
    raise SystemExit(f"{path}: name mismatch {data['name']!r} != {name!r}")
if data["risk_level"] not in {"low", "medium", "high"}:
    raise SystemExit(f"{path}: invalid risk_level")
if data["external_write_behavior"] != "disabled":
    raise SystemExit(f"{path}: presets must keep external writes disabled by default")
if not isinstance(data["validated_cases"], list):
    raise SystemExit(f"{path}: validated_cases must be a list")
if len(data["menu_label"]) < 20:
    raise SystemExit(f"{path}: menu_label is too terse")
PY
done

grep -q 'load_payload_preset()' "$menu"
grep -q 'apply_payload_preset()' "$menu"
grep -q 'current_payload_config_snapshot()' "$menu"
grep -q 'payload_preset_snapshot()' "$menu"
grep -q 'payload_preset_is_dirty()' "$menu"
grep -q 'save_payload_preset()' "$menu"
grep -q 'payload_preset_description()' "$menu"
grep -q 'Payload preset: $(payload_preset_label)' "$menu"
grep -q 'configure_busybox_applet_search()' "$menu"
grep -q 'Search applets by name/group/description' "$menu"
grep -q 'Built-in presets will not be modified' "$menu"
grep -q 'Save this config as-is' "$menu"
grep -q 'Save these payload settings as a new user preset' "$menu"
grep -q 'Discard edits and restore preset defaults' "$menu"
grep -q 'local/presets/payload' "$menu"
grep -q 'presets/payload' "$menu"
grep -q '\* means current payload settings differ from the selected preset' "$menu"
grep -q 'menu_label' "$menu"

grep -q 'Extract payload; help on zero-arg; no reverse access' presets/payload/default.meta.json
grep -q 'Core-only local survey; no extraction; no reverse access' presets/payload/survey-core.meta.json
grep -q 'Core-only builtin TLS shell; zero-arg reverse access' presets/payload/builtin-core-shell.meta.json
grep -q 'Extract BusyBox plus bash; help on zero-arg; no reverse access' presets/payload/payload-bash.meta.json
grep -q 'No-residue socat TLS shell; stages socat' presets/payload/socat-rescue.meta.json
grep -q 'Extract Dropbear/dbclient; explicit reverse SSH; no autorun' presets/payload/ssh-operator.meta.json
grep -q 'Large debug/operator payload; no network autorun' presets/payload/full-debug.meta.json

for topic in top target payload payload-preset runtime launch artifact-overrides rshell busybox heavy dotfiles overlay tool-compat dropbear gdbserver; do
    grep -q "$topic)" "$menu" || {
        printf '%s\n' "payload-presets: missing help topic $topic" >&2
        exit 1
    }
done

grep -q 'GRIT_PAYLOAD_PRESET=' "$menu"
grep -q 'GRIT_RSHELL_RUN_MODE' "$menu"
grep -q 'GRIT_RSHELL_SESSION_POLICY' "$menu"
grep -q 'GRIT_TRAILER_OBFUSCATION' "$menu"
grep -q 'GRIT_DOOM_WAD_PATH' "$menu"
grep -q 'GRIT_PAYLOAD_PRESET=' configs/grit.conf.example
grep -q 'GRIT_DOOM_WAD_PATH=' configs/grit.conf.example
! grep -q 'GRIT_DOOM_USER_PATH' "$menu"
! grep -q 'GRIT_DOOM_USER_PATH=' configs/grit.conf.example

printf '%s\n' "payload-presets ok"
