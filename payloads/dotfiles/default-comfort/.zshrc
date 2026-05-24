precmd() { print -Pn "\e]0;%n@%m: %~\a" }
PROMPT='%n@%m:%~%# '
RPROMPT=''

export PATH="${BUSIERBOX_PAYLOAD_DIR:-$HOME/..}/bin:$PATH"
[ -n "${TERM:-}" ] || export TERM=xterm-256color

if [ -n "${BUSIERBOX_PAYLOAD_DIR:-}" ] && [ -d "$BUSIERBOX_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$BUSIERBOX_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi

autoload -Uz compinit 2>/dev/null && compinit 2>/dev/null
