#!/bin/sh
# Verify menuconfig has validate_config() and that related structural checks are in place.
set -eu

menu=${1:-scripts/menuconfig}

[ -f "$menu" ] || {
    printf '%s\n' "menuconfig-validation: missing $menu" >&2
    exit 1
}

# validate_config function must exist
grep -q 'validate_config()' "$menu"
grep -q 'validate_config' "$menu"

# validate_config must be called from save path
if ! grep -q 'validate_config' "$menu"; then
    printf '%s\n' "menuconfig-validation: validate_config not found" >&2
    exit 1
fi

# Checks that must be present inside validate_config body
# core-only + ssh/socat → error
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'core-only'
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'ssh\|socat'

# zero-arg rshell without host → error
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'BB_OPERATOR_SERVER_HOST'

# ssh without dropbear → auto-fix
awk '/^validate_config\(\)/,/^}/' "$menu" | grep -q 'dropbear'

# none log mode exists in menu
grep -q '"none"' "$menu"
grep -q 'BB_ZERO_ARG_LOG_MODE.*none\|none.*BB_ZERO_ARG_LOG_MODE' "$menu"

# "default" blank preset is in presets.json
presets=targets/presets.json
[ -f "$presets" ] || {
    printf '%s\n' "menuconfig-validation: missing $presets" >&2
    exit 1
}
python3 -c "
import json, sys
raw = json.load(open('$presets'))
presets = raw['presets'] if isinstance(raw, dict) and 'presets' in raw else raw
names = [x['preset_name'] for x in presets]
assert 'default' in names, 'default preset missing'
d = next(x for x in presets if x['preset_name'] == 'default')
assert d.get('arch','') == '', 'default preset must have empty arch'
assert d.get('libc','') == '', 'default preset must have empty libc'
assert d.get('support_status') == 'blank', 'default preset must have support_status=blank'
print('presets ok')
"

# BB_AUTORUN_GUARD_PATH defaults to runtime root in menuconfig (not /tmp)
if grep 'BB_AUTORUN_GUARD_PATH=' "$menu" | grep -v '#' | grep -q '"/tmp/busierbox-autorun"'; then
    printf '%s\n' "menuconfig-validation: BB_AUTORUN_GUARD_PATH still defaults to /tmp/busierbox-autorun" >&2
    exit 1
fi
grep -q 'BB_RUNTIME_ROOT.*run\|BB_AUTORUN_GUARD_PATH.*run' "$menu"

printf '%s\n' "menuconfig-validation ok"
