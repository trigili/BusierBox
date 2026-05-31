precmd() { print -Pn "\e]0;bbx:%n@%m:%~\a" }
PROMPT='%F{green}bbx%f:%F{cyan}%~%f %# '
RPROMPT='%F{yellow}${GRIT_PAYLOAD_DIR:t}%f'

case ":$PATH:" in
    *":${GRIT_PAYLOAD_DIR:-$HOME/..}/bin:"*) ;;
    *) export PATH="${GRIT_PAYLOAD_DIR:-$HOME/..}/bin:$PATH" ;;
esac
[ -n "${TERM:-}" ] || export TERM=xterm-256color

if [ -n "${GRIT_PAYLOAD_DIR:-}" ] && [ -d "$GRIT_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$GRIT_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi

alias ll='ls -l'
alias la='ls -la'
alias path='print -rl -- ${(s/:/)PATH}'
alias grit-doctor='grit doctor'
alias grit-list='grit list --plain'

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
