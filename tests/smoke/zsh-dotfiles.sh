#!/bin/sh
set -eu

if ! command -v zsh >/dev/null 2>&1; then
    printf '%s\n' "skip: zsh dotfile smoke unavailable"
    exit 0
fi

tmp=${TMPDIR:-local/tmp}
mkdir -p "$tmp"
empty_fpath=$(mktemp -d "$tmp/zsh-fpath.XXXXXX")
out=$(mktemp "$tmp/zsh-dotfiles.XXXXXX")
trap 'rm -rf "$empty_fpath"; rm -f "$out"' EXIT HUP INT TERM

for zshrc in \
    payloads/dotfiles/.zshrc \
    payloads/dotfiles/default-comfort/.zshrc \
    payloads/dotfiles/default-minimal/.zshrc \
    payloads/dotfiles/default-operator/.zshrc
do
    FPATH=$empty_fpath zsh -fc "source '$zshrc'" >"$out" 2>&1 || {
        cat "$out" >&2
        exit 1
    }
    if grep -q 'function definition file not found' "$out"; then
        cat "$out" >&2
        exit 1
    fi
done

FPATH=$empty_fpath zsh -fc 'source payloads/dotfiles/default-comfort/.zshrc; bindkey "^[[A"; bindkey "^[[B"' >"$out" 2>&1
grep -q '"\^\[\[A" up-line-or-history' "$out"
grep -q '"\^\[\[B" down-line-or-history' "$out"

zsh -fc 'source payloads/dotfiles/default-comfort/.zshrc; bindkey "^[[A"; bindkey "^[[B"' >"$out" 2>&1
if grep -q 'function definition file not found' "$out"; then
    cat "$out" >&2
    exit 1
fi

printf '%s\n' "zsh-dotfiles ok"
