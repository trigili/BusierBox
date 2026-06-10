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
  listener probe start
  listener probe results
  listener probe config
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
  console for targets, mailbox work, files, bridges, daemon/service lifecycle,
  generated commands, and build config.

Reference:
  --help-console prints interactive console commands and examples.
  --help-all prints every compatibility/API flag.
""")


def _console_help_header_text():
    return """\
usage: grit-console

griTTYkit operator console reference.
"""


def _console_help_discovery_text():
    return """\
Discovery:
  workspace                     show fleet/listener/session overview
  search TERM                   search targets, listeners, modules, sessions, jobs, files, queue
  complete PREFIX               show command/resource completions
  commands, copy N              list or copy generated target commands
  events                         browse the operator event log
  events n N                     show the last N operator events
  events FILTER=VALUE            browse the operator event log with filters
  show targets                 list known targets
  show listeners               list reverse-access listeners
  show routes                  list bridge routes
  show categories               summarize runnable module kinds
  show service modules          browse listener-service modules
  show daemon modules           browse daemon modules
  show target modules           browse target modules
  show workbench modules        browse workbench modules
  show modules                  browse modules by kind, id, workflow, or text
  show modules FILTER           browse matching modules
  show modules verbose          include generated run commands
  show modules verbose FILTER   include generated run commands for matches
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
  listener NAME                 inspect/select a listener
  profile, profiles             inspect or list target/deployment profiles
  profile use NAME              set the active profile by name
  profile use N                 set the active profile by number
  use route NAME                select a bridge route by name
  use route N                   select a bridge route by number
  route NAME                    inspect/select a bridge route
  use module MODULE             select a workflow module
  use session SESSION           select a session context
  use job ID                    select a background job context by id
  use job N                     select a background job context by number
  next                          show suggested commands for current context
  rename VALUE                  edit selected target label
  note VALUE                    edit selected target notes
  alias VALUE                   add selected target alias
  main, home, root              clear selected target/module context
  back, background              clear selected module context
  clear target                  return to all targets
"""


def _console_help_operations_text():
    return """\
Operations:
  listener probe config         populate the active profile from latest probe result
  listener probe config N       populate the active profile from numbered probe result
  profile from probe N          populate the active profile from numbered probe result
  listener serve                stage a release artifact using the active profile
  listener serve start PRESET
                                stage a release artifact using the active profile
  listener serve ssh start      stage ssh-operator payload using the active profile
  serve-binary PATH NAME        manual form: stage a local griTTYkit binary
  serve-binary start PATH NAME
                                manual form: stage and serve a local griTTYkit binary
  stamp NAME KEY=VALUE
  stamp PATH KEY=VALUE
                                stamp embedded runtime config into a binary
  stamp NAME operator-host HOST transport builtin
                                guided embedded config fields for staged payloads
  stage LOCAL NAME              stage a local file for target retrieval
  stage start LOCAL NAME        stage and serve a local file
  release, release stage SELECTOR
                                list or stage release artifacts
  release stage start SELECTOR
                                stage and serve a release artifact
                                selectors include by_device:NAME,
                                by_device_payload_preset:NAME:PRESET,
                                by_tuple_path:PATH, and
                                by_tuple_payload_preset:PATH:PRESET
  deliver NAME                  show target retrieval of a staged file
  deliver start NAME            start file-service and show target retrieval
  deliver queue NAME            queue target retrieval for selected target
  retrieve TARGET_PATH          show target-to-operator file retrieval
  retrieve queue TARGET_PATH    queue target-to-operator retrieval for selected target
  listener probe start          start probe listener and print target commands
  listener probe queue          queue the probe command for selected target
  listener probe delivery       print all probe delivery methods
  listener probe paste          print serial/admin-shell paste commands
                                listeners: probe-http, probe-tftp, probe-ftp, probe-dns
  compatibility aliases         accepted for scripts; prefer stage, deliver, retrieve, stamp, release stage, run, and use ...
  unstage NAME                  remove a staged file request
  view PATH                     view a local session/artifact path
  cat PATH                      print a local session/artifact path
  listeners verbose             list listeners and start/stop commands
  routes, route print           list bridge routes
  routes verbose                include hop details and generated start commands
  route add NAME LISTEN_PORT DEST_HOST DEST_PORT
  route add NAME LISTEN_PORT DEST_HOST DEST_PORT FROM=TO
                                create a reusable bridge route profile
                                model: target connects to operator LISTEN_PORT; operator forwards to DEST_HOST:DEST_PORT
                                DEST_HOST:DEST_PORT must be visible from the operator/server running grit-console
                                hops document the target-to-operator path; they do not change the relay destination
                                hop: FROM=TO, FROM->TO, or FROM,TO; labels are target/jump/operator endpoints
                                direct: route add ssh-home 2222 127.0.0.1 22 target:2222=operator:2222
                                meaning: target connects to operator:2222; operator forwards to 127.0.0.1:22
                                multi-hop: route add web-hop 8080 192.168.1.1 80 target:8080=jump:9001 jump:9001=operator:8080
  route start NAME              start a reusable bridge route by name
  route start N                 start a reusable bridge route by number
  route stop NAME               stop a reusable bridge route by name
  route stop N                  stop a reusable bridge route by number
  route delete NAME              remove a reusable bridge route profile
  queue COMMAND                 queue work for the selected/offline target
  queue list                    inspect queued work
  queue result ID               inspect a queued command result by id
  queue result N                inspect a queued command result by number
  queue clear                   preview clearing queued work
  events service=NAME           filter event log by service, event, level, target, or since
  run MODULE                    run selected or named module
  run MODULE dry-run            preview selected or named module
  check MODULE                  dry-run selected or named module
  run job                       start selected background-capable module as a job
  jobs, jobs info ID, job ID    list/select managed background jobs
  jobs cancel ID, kill, cancel  cancel managed background jobs
  sessions, sessions list       list sessions
  sessions verbose              list sessions with details
  sessions interact SESSION     inspect a session
  interact                      inspect selected session or selected-target work context
  interact target ID            select and inspect a target work context by id
  interact target LABEL         select and inspect a target work context by label
  daemon verbose                list daemon/systemd workflows with commands
  daemon MODULE                 run daemon/systemd workflow module
  daemon MODULE dry-run         preview daemon/systemd workflow module
"""


def _console_help_automation_text():
    return """\
Automation:
  resource FILE                 run console commands from a file
  makerc FILE                   save command history as a resource script
  history LIMIT                 show recent console commands
  !!, !N, repeat N              replay previous commands
  build                         show binary build config
  build set KEY VALUE           update binary build config by key
  build set ROW VALUE           update binary build config by row number
  set KEY VALUE                 set selected target/build option
  setg KEY VALUE                set global build/workbench option
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
