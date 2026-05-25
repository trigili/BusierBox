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

for name in default survey-core builtin-core-shell socat-rescue ssh-operator full-debug; do
    file="$preset_dir/$name.conf"
    [ -f "$file" ] || {
        printf '%s\n' "payload-presets: missing $file" >&2
        exit 1
    }
    if grep -q '^BB_TARGET_\|^BB_TARGETS=\|^BB_KERNEL_FLOOR=' "$file"; then
        printf '%s\n' "payload-presets: target tuple variable found in $file" >&2
        exit 1
    fi
    grep -q '^BB_RUNTIME_MODE=' "$file"
    grep -q '^BB_ZERO_ARG_MODE=' "$file"
    grep -q '^BB_RSHELL_TRANSPORT=' "$file"
    grep -q '^BB_HEAVY_TOOLS=' "$file"
done

grep -q 'load_payload_preset()' "$menu"
grep -q 'apply_payload_preset()' "$menu"
grep -q 'current_payload_config_snapshot()' "$menu"
grep -q 'payload_preset_snapshot()' "$menu"
grep -q 'payload_preset_is_dirty()' "$menu"
grep -q 'save_payload_preset()' "$menu"
grep -q 'Payload preset: $(payload_preset_label)' "$menu"
grep -q 'Save current payload settings as a new preset' "$menu"
grep -q 'Reapply original preset' "$menu"
grep -q 'local/presets/payload' "$menu"
grep -q 'presets/payload' "$menu"
grep -q '\* means current payload settings differ from the selected preset' "$menu"

for topic in top target payload payload-preset runtime launch rshell busybox heavy dotfiles overlay tool-compat dropbear gdbserver; do
    grep -q "$topic)" "$menu" || {
        printf '%s\n' "payload-presets: missing help topic $topic" >&2
        exit 1
    }
done

grep -q 'BB_PAYLOAD_PRESET=' "$menu"
grep -q 'BB_PAYLOAD_PRESET=' configs/busierbox.conf.example

printf '%s\n' "payload-presets ok"
