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

autoload -Uz compinit 2>/dev/null && compinit 2>/dev/null
