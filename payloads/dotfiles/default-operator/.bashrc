# BusierBox operator bash startup.
export BUSIERBOX_SHELL=bash
alias ll='ls -lah'
alias ports='netstat -tulpen 2>/dev/null || ss -tulpen 2>/dev/null'
alias procs='ps w 2>/dev/null || ps'
PS1='[bbx:\h \W]\$ '

