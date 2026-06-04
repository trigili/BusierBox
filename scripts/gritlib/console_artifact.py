"""Artifact subcommand dispatch shared by grit-console and compatibility wrappers."""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "lib"


def print_artifact_usage(program="grit-console artifact"):
    print(f"""\
usage: {program} <command> [options] ARTIFACT

Commands:
  inspect PATH              parse and display artifact metadata
  verify  PATH [options]    verify artifact integrity and execution
  config  PATH [options]    inspect or edit runtime override trailer

  inspect --help, verify --help, config --help  for per-command options

Examples:
  {program} inspect dist/grit-native-full
  {program} verify  dist/grit-native-full
  {program} config  dist/grit-native-full
  {program} config set dist/grit-native-full GRIT_OPERATOR_SERVER_HOST=192.168.1.10
""")


def print_artifact_command_usage(cmd, program="grit-console artifact"):
    if cmd == "inspect":
        print(f"""\
usage: {program} inspect ARTIFACT

Parse embedded payload/trailer metadata without executing the artifact.
""")
        return 0
    if cmd == "verify":
        print(f"""\
usage: {program} verify ARTIFACT [options]

Verify payload structure, checksums, and executable behavior.
""")
        return 0
    if cmd == "config":
        return subprocess.run([sys.executable, str(LIB / "artifact-config"), "--help"]).returncode
    print_artifact_usage(program)
    return 2


def handle_artifact_command(argv, program="grit-console artifact"):
    args = list(argv or [])
    if not args or args[0] in ("-h", "--help", "help"):
        print_artifact_usage(program)
        return 0

    cmd = args[0]
    rest = args[1:]
    if rest and rest[0] in ("-h", "--help", "help"):
        return print_artifact_command_usage(cmd, program=program)

    dispatch = {
        "inspect": LIB / "inspect-artifact",
        "verify": LIB / "verify-artifact",
        "config": LIB / "artifact-config",
    }
    target = dispatch.get(cmd)
    if target is None:
        print(f"{program}: unknown command '{cmd}'  -  see --help", file=sys.stderr)
        return 2
    return subprocess.run([sys.executable, str(target)] + rest).returncode
