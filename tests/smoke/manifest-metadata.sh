#!/bin/sh
set -eu

bb=${1:-dist/busierbox-native-full}

[ -x "$bb" ] || {
    printf '%s\n' "manifest-metadata: missing executable $bb" >&2
    exit 1
}

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
    ("runtime", "mode"),
    ("runtime", "root"),
    ("zero_arg", "mode"),
    ("rshell", "transport"),
    ("dotfiles", "enabled"),
    ("overlay", "enabled"),
]
for section, field in required:
    if section not in manifest or field not in manifest[section]:
        raise SystemExit(f"manifest-metadata: missing {section}.{field}")

checks = [
    (manifest["busierbox"]["artifact_tier"], config.get("artifact_tier"), "artifact_tier"),
    (manifest["busierbox"]["payload_version"], config.get("payload_version"), "payload_version"),
    (manifest["runtime"]["mode"], config.get("runtime_mode"), "runtime_mode"),
    (manifest["runtime"]["root"], config.get("runtime_root"), "runtime_root"),
    (manifest["zero_arg"]["mode"], config.get("zero_arg_mode"), "zero_arg_mode"),
    (manifest["rshell"]["transport"], config.get("rshell_transport"), "rshell_transport"),
]
for got, want, name in checks:
    if got != want:
        raise SystemExit(f"manifest-metadata: {name} mismatch: manifest={got!r} config-info={want!r}")

print("manifest-metadata ok")
PY
