#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}
tmp=${TMPDIR:-local/tmp}/manifest-metadata

[ -x "$bb" ] || {
    printf '%s\n' "manifest-metadata: missing executable $bb" >&2
    exit 1
}

case "$bb" in
    /*) bb_abs=$bb ;;
    *) bb_abs=$(pwd)/$bb ;;
esac

python3 - "$bb" <<'PY'
import json
import subprocess
import sys

bb = sys.argv[1]
manifest = json.loads(subprocess.check_output([bb, "manifest", "--json"], text=True))
config = {}
for line in subprocess.check_output([bb, "config-info"], text=True).splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        config[k] = v

required = [
    ("busierbox", "payload_version"),
    ("busierbox", "artifact_tier"),
    ("busierbox", "build_timestamp"),
    ("busierbox", "git_commit"),
    ("target", "preset"),
    ("target", "name"),
    ("target", "arch"),
    ("target", "endian"),
    ("target", "cpu"),
    ("target", "abi"),
    ("target", "libc"),
    ("target", "kernel_floor"),
    ("target", "static_policy"),
    ("payload", "preset"),
    ("payload", "gdbserver_provider"),
    ("runtime", "mode"),
    ("runtime", "root"),
    ("zero_arg", "mode"),
    ("rshell", "transport"),
    ("rshell", "operator_host"),
    ("rshell", "operator_shell_port"),
    ("rshell", "operator_ssh_port"),
    ("rshell", "remote_forward_port"),
    ("rshell", "target_dropbear"),
    ("rshell", "authkeys_mode"),
    ("rshell", "retry"),
    ("dotfiles", "enabled"),
    ("overlay", "enabled"),
]
for section, field in required:
    if section not in manifest or field not in manifest[section]:
        raise SystemExit(f"manifest-metadata: missing {section}.{field}")

checks = [
    (manifest["busierbox"]["artifact_tier"], config.get("artifact_tier"), "artifact_tier"),
    (manifest["busierbox"]["payload_version"], config.get("payload_version"), "payload_version"),
    (manifest["payload"]["gdbserver_provider"], config.get("gdbserver_provider"), "gdbserver_provider"),
    (manifest["runtime"]["mode"], config.get("runtime_mode"), "runtime_mode"),
    (manifest["runtime"]["root"], config.get("runtime_root"), "runtime_root"),
    (manifest["zero_arg"]["mode"], config.get("zero_arg_mode"), "zero_arg_mode"),
    (manifest["rshell"]["transport"], config.get("rshell_transport"), "rshell_transport"),
    (manifest["rshell"]["operator_shell_port"], config.get("rshell_socat_port"), "rshell_socat_port"),
    (manifest["rshell"]["remote_forward_port"], config.get("operator_reverse_ssh_catch_hint", "").split()[2] if config.get("operator_reverse_ssh_catch_hint") else None, "remote_forward_port"),
]
for got, want, name in checks:
    if got != want:
        raise SystemExit(f"manifest-metadata: {name} mismatch: manifest={got!r} config-info={want!r}")

retry = manifest["rshell"]["retry"]
for key in ["count", "interval_sec", "jitter_pct", "backoff", "max_interval_sec"]:
    if key not in retry:
        raise SystemExit(f"manifest-metadata: missing rshell.retry.{key}")

print("manifest-metadata ok")
PY

rm -rf "$tmp"
mkdir -p "$tmp"
(
    cd "$tmp"
    "$bb_abs" extract --force >/dev/null
    test -f ./.busierbox/manifest/artifact.json
    python3 -m json.tool ./.busierbox/manifest/artifact.json >/dev/null
)
rm -rf "$tmp"

printf '%s\n' "manifest artifact file ok"
