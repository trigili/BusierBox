#!/bin/sh
set -eu

[ -x runtime/payload/bin/busybox ] || {
    printf '%s\n' "dotfiles-by-app: missing runtime/payload/bin/busybox; run package-native first" >&2
    exit 1
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

printf '%s\n' '# user zsh' >"$tmp/zshrc"
printf '%s\n' '# user bash' >"$tmp/bashrc"

GRIT_RUNTIME_MODE=extract \
GRIT_DOTFILES_ENABLE=yes \
GRIT_DOTFILE_ZSH_MODE=user \
GRIT_DOTFILE_ZSH_USER_FILE="$tmp/zshrc" \
GRIT_DOTFILE_BASH_MODE=user \
GRIT_DOTFILE_BASH_USER_FILE="$tmp/bashrc" \
GRIT_DOTFILE_TMUX_MODE=none \
GRIT_DOTFILE_GDB_MODE=default \
GRIT_DOTFILE_PROFILE_MODE=none \
scripts/build-payload >/dev/null

grep -q '# user zsh' runtime/payload/home/.zshrc
grep -q '# user bash' runtime/payload/home/.bashrc
[ ! -e runtime/payload/home/.tmux.conf ]
[ -e runtime/payload/home/.gdbinit ]
[ ! -e runtime/payload/home/.profile ]

if GRIT_RUNTIME_MODE=extract GRIT_DOTFILES_ENABLE=yes GRIT_DOTFILE_ZSH_MODE=user GRIT_DOTFILE_ZSH_USER_FILE="$tmp/missing" scripts/build-payload >"$tmp/missing.out" 2>&1; then
    printf '%s\n' "dotfiles-by-app: missing user dotfile did not fail" >&2
    exit 1
fi
grep -q 'zsh dotfile mode is user but file is missing' "$tmp/missing.out"

GRIT_RUNTIME_MODE=core-only \
GRIT_DOTFILES_ENABLE=yes \
GRIT_DOTFILE_ZSH_MODE=default \
GRIT_DOTFILE_BASH_MODE=default \
GRIT_DOTFILE_TMUX_MODE=default \
GRIT_DOTFILE_GDB_MODE=default \
GRIT_DOTFILE_PROFILE_MODE=default \
scripts/build-payload >/dev/null

[ ! -e runtime/payload/home/.zshrc ]
[ ! -e runtime/payload/home/.bashrc ]
[ ! -e runtime/payload/home/.tmux.conf ]
[ ! -e runtime/payload/home/.gdbinit ]
[ ! -e runtime/payload/home/.profile ]

printf '%s\n' "dotfiles-by-app ok"
