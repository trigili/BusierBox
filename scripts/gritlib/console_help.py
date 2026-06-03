"""Static help text printers for grit-console."""


def print_concise_help():
    print("""\
usage: grit-console [--config CONFIG] [mode] [options]

griTTYkit operator control plane.

Start here:
  grit-console --tui
  grit-console --status
  grit-console --json-status

Common operator workflows:
  --daemon --daemon-service file-service --daemon-service command-queue
  --systemd-user-action print|install|start|stop|restart|status
  --serve-file ./grit --as grit
  --stage-release-artifact SELECTOR
  --list-staged
  --target-id TARGET --queue-command COMMAND
  --list-command-queue
  --save-bridge-profile NAME --bridge-port PORT --bridge-dest-host HOST --bridge-dest-port PORT
  --transport bridge --bridge-profile NAME
  --transport probe
  --transport probe-tftp
  --transport probe-ftp
  --transport probe-dns

Interactive console:
  --tui opens the full-screen curses workbench for targets, mailbox work, files, bridges,
  daemon/service lifecycle, generated commands, and build config.

Reference:
  --help-console prints interactive console commands and examples.
  --help-all prints every compatibility/API flag.
""")


def print_console_help_reference():
    print("""\
usage: grit-console --tui

griTTYkit operator console reference.

Discovery:
  workspace                     show fleet/listener/session overview
  search TERM                   search agents, listeners, modules, sessions, jobs, files, queue
  complete [PREFIX]             show command/resource completions
  commands, copy N              list or copy generated target commands
  events [-n N] [FILTER=VALUE]  browse the operator event log
  show agents|listeners|routes  list common operator resources
  show categories               summarize runnable module kinds
  show service|daemon modules   browse modules by operator category
  show modules [FILTER]         browse modules by kind, id, workflow, or text
  show stagers|loot|sessions    inspect files and sessions
  help COMMAND                  focused help inside the console

Context:
  use N                         select a numbered search/list/module result
  use agent ID|LABEL|NUMBER     select a target device
  agent ID|LABEL|NUMBER         select a target device
  use listener SERVICE          select a service module
  listener SERVICE              inspect/select a listener service
  use route NAME|NUMBER         select a bridge route
  route NAME                    inspect/select a bridge route
  use module ACTION             select an action module
  useagent/usemodule NAME       Empire-style context selection aliases
  use session SESSION           select a session context
  use job ID|NUMBER             select a background job context
  next                          show suggested commands for current context
  rename|note|alias VALUE       edit selected agent metadata
  main, home, root              clear selected target/module context
  back, background              clear selected module context
  clear target                  return to all targets

Operations:
  serve-binary [--start] [PATH] [NAME]
                                stage and optionally serve a griTTYkit binary
  configure NAME|PATH KEY=VALUE...
                                apply runtime trailer overrides to a binary
  configure NAME --operator-host HOST --transport builtin
                                guided trailer override flags for staged payloads
  upload [--start] LOCAL [NAME] stage and optionally serve a local file
  release, release stage SELECTOR
                                list or stage release artifacts
                                selectors include by_device:NAME,
                                by_device_payload_preset:NAME:PRESET,
                                by_tuple_path:PATH, and
                                by_tuple_payload_preset:PATH:PRESET
  fetch [--queue] [--start] NAME
                                show or queue target fetch of a staged file
  download [--queue] TARGET_PATH
                                show or queue a target-to-operator upload command
  probe [--start|--queue], probe delivery, probe paste
                                show, serve, queue, or print probe delivery commands
                                listeners: probe-http, probe-tftp, probe-ftp, probe-dns
  downloads                     list target-fetchable staged files
  unstage NAME                  remove a staged file request
  view PATH, cat PATH           view a local session/artifact path
  listeners [-v]                list listener services and start/stop commands
  routes [-v], route print      list bridge routes and hop details
  route add NAME LPORT HOST DPORT [HOP ...]
                                create a reusable bridge route profile
                                model: operator listens on LPORT; bridge delivers to HOST:DPORT from target side
                                hop: FROM=TO, FROM->TO, or FROM,TO; labels are target/jump/operator endpoints
                                direct: route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222
                                meaning: connect to operator:2222, bridge to target-side 127.0.0.1:22
                                multi-hop: route add web-hop 8080 192.168.1.1 80 target:8080=jump:9001 jump:9001=operator:8080
  route start NAME, route stop NAME
                                control a reusable bridge route profile
  route delete NAME              remove a reusable bridge route profile
  queue COMMAND                 queue work for the selected/offline target
  queue list|result|clear       inspect results or clear queued work
  events service=NAME           filter event log by service, event, level, target, or --since
  run [MODULE] [--dry-run]      run selected or named module
  execute, exploit              aliases for run
  check [MODULE]                dry-run selected or named module
  run -j                        start selected background-capable action as a job
  jobs, jobs -i ID, job ID      list/select managed background jobs
  jobs -k ID, kill, cancel      cancel managed background jobs
  sessions [-l|-v]              list sessions
  sessions -i SESSION           inspect a session
  interact                      inspect selected session or selected-agent work context
  interact agent ID|LABEL       select and inspect an agent work context
  daemon [-v]                   list daemon/systemd workflows; -v shows commands
  daemon ACTION [--dry-run]     preview or run daemon/systemd workflow

Automation:
  resource FILE                 run console commands from a file
  makerc FILE                   save command history as a resource script
  history [LIMIT]               show recent console commands
  !!, !N, repeat N              replay previous commands
  build, build set KEY VALUE    show or update binary build config
  set KEY VALUE                 set selected target/build option
  setg KEY VALUE                set global build/workbench option

Headless equivalents remain available through --help-all.
""")
