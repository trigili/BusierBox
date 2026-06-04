#!/bin/sh
set -eu

menu=${1:-scripts/menuconfig}
[ -f "$menu" ] || {
    printf '%s\n' "menuconfig-autoexec: missing $menu" >&2
    exit 1
}

grep -q 'GRIT_ZERO_ARG_MODE=' "$menu"
grep -q 'GRIT_ZERO_ARG_LOG_MODE=' "$menu"
grep -q 'GRIT_ZERO_ARG_CUSTOM_COMMAND=' "$menu"
grep -q 'GRIT_TRAILER_OVERRIDES_ENABLE=' "$menu"
grep -q 'Artifact runtime overrides' "$menu"
grep -q 'scripts/grit-console artifact config' "$menu"
if grep -q 'scripts/lib/artifact-config' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: runtime override UX still recommends direct artifact-config helper" >&2
    exit 1
fi
grep -q 'GRIT_RSHELL_TRANSPORT=' "$menu"
grep -q 'GRIT_RSHELL_AUTHKEYS_MODE=' "$menu"
grep -q 'GRIT_DOTFILE_ZSH_MODE=' "$menu"
grep -q 'GRIT_DOTFILE_BASH_MODE=' "$menu"
grep -q 'GRIT_DOTFILE_TMUX_MODE=' "$menu"
grep -q 'GRIT_DOTFILE_GDB_MODE=' "$menu"
grep -q 'GRIT_DOTFILE_PROFILE_MODE=' "$menu"
grep -q 'configure_build_targets' "$menu"
grep -q 'configure_runtime_mode' "$menu"
grep -q 'GRIT_AUTORUN_GUARD_PATH=' "$menu"
grep -q 'Launch behavior: zero-arg=' "$menu"
grep -q 'scripts/grit-console' "$menu"
grep -q 'Applet configuration' "$menu"
grep -q 'Reverse access' "$menu"
grep -q 'Dotfiles by app' "$menu"
grep -q 'griTTYkit default initial config' "$menu"
if awk '
    /payload_preset_description\(\)/ { in_fn=1 }
    in_fn && /risk=/ { found=1 }
    in_fn && /size=/ { found=1 }
    in_fn && /^}/ { in_fn=0 }
    END { exit found ? 0 : 1 }
' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: payload preset menu rows append clipping-prone risk/size text" >&2
    exit 1
fi
if grep -q 'default-comfort\\|default-operator\\|default-minimal' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: old global dotfile profiles are still in menuconfig" >&2
    exit 1
fi
grep -q 'Classic Doom runtime' "$menu"
grep -q 'bash shell \[dotfiles\]' "$menu"
grep -q 'target binary required from drop-in/user/overlay' "$menu"
if grep -q -- '--item-help' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: Misc heavy tools should not use item-help flash behavior" >&2
    exit 1
fi
if grep -q 'provider-only' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: provider-only wording is still visible" >&2
    exit 1
fi
grep -q 'local/operator-session' "$menu"

if grep -q '"Callbacks:' "$menu" || grep -q 'Post-receive behavior is configured under' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: retired transport UX is still visible" >&2
    exit 1
fi

if awk '
    /operator_session_enabled\(\)/ { in_fn=1 }
    in_fn && /GRIT_FULL_CALLBACK_ENABLE/ { found=1 }
    in_fn && /^}/ { in_fn=0 }
    END { exit found ? 0 : 1 }
' "$menu"; then
    printf '%s\n' "menuconfig-autoexec: retired transport config would trigger SSH catch instructions" >&2
    exit 1
fi

printf '%s\n' "menuconfig-autoexec ok"
