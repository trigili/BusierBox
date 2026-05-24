# Upgrade degraded TERM values before anything else
case "${TERM:-vt100}" in
    vt100|dumb|"") export TERM=xterm-256color ;;
esac

# Payload bin on PATH
_bbx_bin="${BUSIERBOX_PAYLOAD_DIR:-$HOME/..}/bin"
case ":${PATH}:" in
    *":${_bbx_bin}:"*) ;;
    *) export PATH="${_bbx_bin}:${PATH}" ;;
esac
unset _bbx_bin

# Terminfo from payload (for ncurses-aware tools like tmux, htop)
if [ -n "${BUSIERBOX_PAYLOAD_DIR:-}" ] && [ -d "$BUSIERBOX_PAYLOAD_DIR/share/terminfo" ]; then
    export TERMINFO_DIRS="$BUSIERBOX_PAYLOAD_DIR/share/terminfo:/usr/share/terminfo:/lib/terminfo"
fi

# History
HISTFILE="${ZDOTDIR:-$HOME}/.zsh_history"
HISTSIZE=10000
SAVEHIST=10000
setopt hist_ignore_dups hist_ignore_space share_history append_history extended_history

# Shell options
setopt autocd extendedglob no_beep prompt_subst interactive_comments

# Colors
autoload -Uz colors && colors 2>/dev/null

# Prompt: green user@host, cyan path, yellow right-side clock
PROMPT='%F{green}%n@%m%f:%F{cyan}%~%f%# '
RPROMPT='%F{yellow}%*%f'

# Terminal title
precmd() { print -Pn "\e]0;%n@%m: %~\a" }

# History search on up/down arrows (prefix-aware)
autoload -Uz up-line-or-beginning-search down-line-or-beginning-search 2>/dev/null
zle -N up-line-or-beginning-search
zle -N down-line-or-beginning-search
bindkey "^[[A" up-line-or-beginning-search
bindkey "^[[B" down-line-or-beginning-search
# Home / End / Delete
bindkey "^[[H"  beginning-of-line
bindkey "^[[F"  end-of-line
bindkey "^[[3~" delete-char
# Ctrl-Left / Ctrl-Right word jump
bindkey "^[[1;5D" backward-word
bindkey "^[[1;5C" forward-word

# Tab completion
autoload -Uz compinit 2>/dev/null && compinit -u 2>/dev/null
zstyle ':completion:*' menu select
zstyle ':completion:*' list-colors ''
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Z}'

# ls colors (GNU coreutils and busybox both understand --color=auto)
alias ls='ls --color=auto 2>/dev/null || ls'
alias ll='ls -lh'
alias la='ls -lha'
alias l='ls -CF'

# Colorize grep and diff where available
alias grep='grep --color=auto'
alias fgrep='fgrep --color=auto'
alias egrep='egrep --color=auto'

# BusierBox shortcuts
alias bbx='busierbox'
alias bbx-doctor='busierbox doctor'
alias bbx-survey='busierbox survey'
alias bbx-list='busierbox list'

# Convenience
alias ..='cd ..'
alias ...='cd ../..'
alias path='print -rl -- ${(s/:/)PATH}'
