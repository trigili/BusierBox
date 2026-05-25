precmd() { print -Pn "\e]0;bbx:%n@%m:%~\a" }
PROMPT='%F{green}bbx%f:%F{cyan}%~%f %# '
RPROMPT='%F{yellow}${BUSIERBOX_PAYLOAD_DIR:t}%f'

case ":$PATH:" in
    *":${BUSIERBOX_PAYLOAD_DIR:-$HOME/..}/bin:"*) ;;
    *) export PATH="${BUSIERBOX_PAYLOAD_DIR:-$HOME/..}/bin:$PATH" ;;
esac
[ -n "${TERM:-}" ] || export TERM=xterm-256color

if [ -n "${BUSIERBOX_PAYLOAD_DIR:-}" ] && [ -d "$BUSIERBOX_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$BUSIERBOX_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi

alias ll='ls -l'
alias la='ls -la'
alias path='print -rl -- ${(s/:/)PATH}'
alias bbx-doctor='busierbox doctor'
alias bbx-list='busierbox list --plain'

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
