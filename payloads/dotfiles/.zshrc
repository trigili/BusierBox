precmd() { print -Pn "\e]0;%n@%m: %~\a" }
PROMPT='%n@%m:%~%# '
RPROMPT=''

_grit_bin="${GRIT_PAYLOAD_DIR:-$HOME/..}/bin"
case ":${PATH}:" in
    *":${_grit_bin}:"*) ;;
    *) export PATH="${_grit_bin}:${PATH}" ;;
esac
unset _grit_bin
[ -n "${TERM:-}" ] || export TERM=xterm-256color

if [ -n "${GRIT_PAYLOAD_DIR:-}" ] && [ -d "$GRIT_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$GRIT_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi

_grit_has_zsh_function() {
    local _grit_dir
    for _grit_dir in $fpath; do
        [ -r "$_grit_dir/$1" ] && return 0
    done
    return 1
}

if _grit_has_zsh_function compinit; then
    autoload -Uz compinit 2>/dev/null && compinit 2>/dev/null
fi

unfunction _grit_has_zsh_function 2>/dev/null || true
