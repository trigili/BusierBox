precmd() { print -Pn "\e]0;%n@%m: %~\a" }
PROMPT='%n@%m:%~%# '
RPROMPT=''

_bbx_bin="${BUSIERBOX_PAYLOAD_DIR:-$HOME/..}/bin"
case ":${PATH}:" in
    *":${_bbx_bin}:"*) ;;
    *) export PATH="${_bbx_bin}:${PATH}" ;;
esac
unset _bbx_bin
[ -n "${TERM:-}" ] || export TERM=xterm-256color

if [ -n "${BUSIERBOX_PAYLOAD_DIR:-}" ] && [ -d "$BUSIERBOX_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$BUSIERBOX_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi

_bbx_has_zsh_function() {
    local _bbx_dir
    for _bbx_dir in $fpath; do
        [ -r "$_bbx_dir/$1" ] && return 0
    done
    return 1
}

if _bbx_has_zsh_function compinit; then
    autoload -Uz compinit 2>/dev/null && compinit 2>/dev/null
fi

unfunction _bbx_has_zsh_function 2>/dev/null || true
