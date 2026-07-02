"""Static help text printers for grit-console."""


def print_concise_help():
    print("""\
usage: grit-console [--config CONFIG] [mode] [options]

griTTYkit operator control plane.

Start here:
  grit-console
  grit-console --status
  grit-console --json-status

Interactive workflow:
  use listener probe
  start
  results
  config
  profiles
  listener serve
  listener serve ssh start
  files
  stamp NAME operator-host HOST transport builtin

Headless/service examples:
  --daemon --daemon-service file-service --daemon-service command-queue
  --systemd-user-action status
  --systemd-user-action start
  --systemd-user-action stop
  --serve-file ./grit --as grit
  --stage-release-artifact SELECTOR
  artifact inspect ARTIFACT
  artifact verify ARTIFACT
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
  Running grit-console with no service action opens the line-oriented operator
console for targets, pending work, files, bridges, daemon/service lifecycle,
  generated commands, and build config.

Reference:
  --help-console prints interactive console commands and examples.
  --help-all prints every non-interactive and compatibility flag.
""")


def _console_help_header_text():
    return """\
usage: grit-console

griTTYkit operator console reference.
"""


def _console_help_discovery_text():
    return """\
Discovery:
workspace                     leave the current menu and show the main overview
  search listener               search targets, listeners, modules, sessions, jobs, files, queue
  complete listener             show command/resource completions
  commands                      list target commands
  copy N                        copy a numbered target command
  events                         browse the operator event log
  events n N                     show the last N operator events
  events FILTER=VALUE            browse the operator event log with filters
  show targets                 list known targets
  show listeners               list operator listeners
  show routes                  list bridge routes
  modules service               browse listener-service modules
  modules daemon                browse daemon modules
  modules target                browse target modules
  modules operator              browse operator modules
  show modules                  browse modules by kind, id, workflow, or text
  show modules service          browse matching service modules
show modules verbose          include command lines
show modules verbose service  include command lines for service modules
  show files                    inspect staged files
  show sessions                 inspect captured sessions
  help COMMAND                  focused help inside the console
"""


def _console_help_context_text():
    return """\
Context:
  use N                         select a numbered search/list/module result
  use target ID                 select a target device by id
  use target LABEL              select a target device by label
  use target N                  select a target device by number
  target ID                     select a target device by id
  target LABEL                  select a target device by label
  target N                      select a target device by number
  use listener NAME             select a listener
  listener NAME                 inspect and select a listener
  profile                       inspect the active target deployment profile
  profiles                      list target deployment profiles
  profile use NAME              set the active profile by name
  profile use N                 set the active profile by number
  use route NAME                select a bridge route by name
  use route N                   select a bridge route by number
  route NAME                    inspect and select a bridge route
  use module Inspect bridge status
                                select a console module by visible name
  use session SESSION           select a session context
use job job-1                 select a background job context by id
use job 1                     select a background job context by row number
  next                          show suggested commands for current context
  rename VALUE                  edit the current target label
  note VALUE                    edit the current target notes
  alias VALUE                   add a current target alias
  main                          return to grit[all]> without printing the overview
  home                          return to grit[all]> without printing the overview
  root                          return to grit[all]> without printing the overview
  back                          go up one breadcrumb level
  background                    go up one breadcrumb level
  clear target                  return to all targets
"""


def _console_help_operations_text():
    return """\
Operations:
  use listener probe             open the probe submenu
  config                         after `use listener probe`, populate from the latest result
  config 1                       after `use listener probe`, populate from probe result row 1
  profile from probe 1          populate the active profile from probe result row 1
  listener serve                stage a release artifact using the active profile
  listener serve start default
                                stage a release artifact and start file-service using the active profile
  listener serve ssh start      stage reverse SSH payload and start file-service
  stamp NAME KEY=VALUE
  stamp PATH KEY=VALUE
                                stamp embedded runtime settings into a staged file or artifact
  stamp NAME operator-host HOST transport builtin
                                guided embedded config fields for staged payloads
stage ./grit sample-file      stage a local file for deliver commands
stage start ./grit sample-file
                                stage a local file and start file-service
  release                       list release artifacts
  release stage by_device:NAME
                                stage a release artifact by known device name
  release stage start by_device:NAME
                                stage a release artifact and start file-service
  release stage dist/releases/lab/bin/grit-target-full
                                stage a specific local release artifact path
                                selectors include by_device:NAME,
                                by_device_payload_preset:NAME:PRESET,
                                by_tuple_path:PATH, and
                                by_tuple_payload_preset:PATH:PRESET
  deliver sample-file           show commands to run on the target for a staged file
  deliver start sample-file     start file-service and show commands to run on the target
  deliver queue sample-file     queue the staged-file command for the current target
  retrieve /etc/hosts           show target-to-operator file retrieval
  retrieve queue /etc/hosts     queue target-to-operator retrieval for the current target
  use listener probe            open the probe submenu
  start                         in the probe submenu, start listener and print commands to run on the target
  queue                         in the probe submenu, queue the probe command for the current target
  commands                      in the probe submenu, print commands to run on the target
  paste                         in the probe submenu, print serial or admin shell paste commands
                                listeners: probe-http, probe-tftp, probe-ftp, probe-dns
  compatibility aliases         accepted for scripts; prefer stage, deliver, retrieve, stamp, release stage, run, and use ...
  unstage NAME                  remove a staged file request
  view ./README.md              view a local session/artifact path
  cat ./README.md               print a local session/artifact path
  listeners verbose             list listeners and start and stop commands
  routes                        list bridge routes
  route print                   list bridge routes
  routes verbose                include hop details and route start commands
route add ssh-home 2222 127.0.0.1 22
route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222
                                create a reusable bridge route profile
                                model: target connects to operator:2222; operator forwards to 127.0.0.1:22
                                destination must be reachable from the machine running grit-console
                                hops document the target-to-operator path; they do not change the relay destination
                                hop labels are target/jump/operator endpoints, such as target:2222 and operator:2222
                                direct: route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222
                                meaning: target connects to operator:2222; operator forwards to 127.0.0.1:22
                                multi-hop: route add web-hop 8080 192.168.1.1 80 target:8080=jump:9001 jump:9001=operator:8080
  route start ssh-home          start a reusable bridge route by name
  route start N                 start a reusable bridge route by number
  route stop ssh-home           stop a reusable bridge route by name
  route stop N                  stop a reusable bridge route by number
  route delete ssh-home         preview route profile removal
  route delete ssh-home confirm remove a reusable bridge route profile
queue uname -a                queue work for the current/offline target
  queue list                    inspect queued work
  queue result ID               inspect a queued command result by id
  queue result 1                inspect the first queued command result
  queue clear                   preview clearing queued work
  events service=NAME           filter event log by service, event, level, target, or since
  run Inspect bridge status     run the current or named module
  preview Inspect bridge status preview the current or named module
  check Inspect bridge status   preflight the current or named module
  run job                       start the current module as a background job
  jobs                          list managed background jobs
  jobs info job-1               inspect a background job by id
  jobs info 1                   inspect a background job by row number
  job job-1                     inspect and select a background job by id
  job 1                         inspect and select a background job by row number
  jobs cancel job-1             cancel a managed background job by id
  jobs cancel 1                 cancel a managed background job by row number
  cancel                        cancel the current background job
  sessions                      list sessions
  sessions list                 list sessions
  sessions verbose              list sessions with details
  sessions interact 1           inspect a session by row number
  interact                      inspect the current session or target work context
  interact target ID            select and inspect a target work context by id
  interact target LABEL         select and inspect a target work context by label
  daemon verbose                list daemon controls with command lines
  daemon status                 show daemon health and managed listener state
  daemon status preview         preview the daemon status control
  daemon install confirm        install the user systemd unit after confirmation
"""


def _console_help_automation_text():
    return """\
Command files:
  resource ./commands.gritrc    run console commands from a command file
  makerc ./last-session.gritrc  save command history as a replayable command file
  history 50                    show recent console commands
  !!                            replay the previous command
  !1                            replay history entry 1
  repeat 1                      replay history entry 1
  build                         show build config
  build set GRIT_RUNTIME_ROOT ./.grit
                                update build config by key
  build set 16 ssh              update build config by row number
  set GRIT_RUNTIME_ROOT ./.grit set current build option from the build menu
"""


def _console_help_footer_text():
    return """\
Headless equivalents remain available through --help-all.
"""


def print_console_help_reference():
    print("".join((
        _console_help_header_text(),
        "\n",
        _console_help_discovery_text(),
        "\n",
        _console_help_context_text(),
        "\n",
        _console_help_operations_text(),
        "\n",
        _console_help_automation_text(),
        "\n",
        _console_help_footer_text(),
    )))
