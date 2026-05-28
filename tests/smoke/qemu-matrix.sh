#!/bin/sh
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TARGET_MATRIX=${1:-"$ROOT/tests/matrix/targets.example.json"}
SYSTEM_MATRIX=${2:-"$ROOT/tests/matrix/environments.example.json"}

grep -q '^test-qemu-user: package-native$' "$ROOT/Makefile"
grep -q '^test-qemu-system:$' "$ROOT/Makefile"
if grep -q '^test-qemu-\(user\|system\): package$' "$ROOT/Makefile"; then
    printf '%s\n' "qemu-matrix: QEMU tests must not build the active configured target before matrix skips" >&2
    exit 1
fi
grep -q 'summary.json' "$ROOT/tests/qemu-user/run-qemu-user-matrix"
grep -q '"records_by_status"' "$ROOT/tests/qemu-user/run-qemu-user-matrix"
grep -q 'summary.json' "$ROOT/tests/qemu-system/run-qemu-system-matrix"
grep -q '"records_by_status"' "$ROOT/tests/qemu-system/run-qemu-system-matrix"

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "skip: python3 qemu matrix smoke unavailable"
    exit 0
fi

python3 - "$TARGET_MATRIX" "$SYSTEM_MATRIX" <<'PY'
import json
import sys

target_path, system_path = sys.argv[1], sys.argv[2]


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def require(condition, message):
    if not condition:
        raise SystemExit(message)


targets = load_json(target_path)
systems = load_json(system_path)

require(targets.get("schema") == 1, "targets matrix schema must be 1")
require(systems.get("schema") == 1, "system matrix schema must be 1")

target_entries = targets.get("targets", [])
system_entries = systems.get("environments", [])
require(target_entries, "targets matrix has no targets")
require(system_entries, "system matrix has no environments")

target_arches = {entry.get("arch") for entry in target_entries}
required_target_arches = {
    "native",
    "x86_64",
    "i386",
    "aarch64",
    "armv7",
    "armv5",
    "mipsel",
    "mips",
}
missing_arches = sorted(required_target_arches - target_arches)
require(not missing_arches, "targets matrix missing arch coverage: " + ", ".join(missing_arches))

kernel_floors = {entry.get("kernel_floor") for entry in target_entries}
required_kernel_floors = {"host", "current", "2.6", "3.x", "4.x"}
missing_floors = sorted(required_kernel_floors - kernel_floors)
require(not missing_floors, "targets matrix missing kernel floor coverage: " + ", ".join(missing_floors))

libcs = {entry.get("libc_family") for entry in target_entries}
missing_libcs = sorted({"host", "musl", "uclibc"} - libcs)
require(not missing_libcs, "targets matrix missing libc coverage: " + ", ".join(missing_libcs))

endian = {(entry.get("arch"), entry.get("endian")) for entry in target_entries}
require(("mipsel", "little") in endian, "targets matrix missing little-endian MIPS coverage")
require(("mips", "big") in endian, "targets matrix missing big-endian MIPS coverage")

names = set()
for entry in target_entries:
    name = entry.get("name", "")
    require(name, "target entry missing name")
    require(name not in names, "duplicate target name: " + name)
    names.add(name)
    require(entry.get("binary", "").startswith("dist/busierbox-"), name + " binary must point at dist/busierbox-*")
    require(entry.get("binary", "").endswith("-full"), name + " binary must be a full self-extracting artifact")
    qemu = entry.get("qemu_user", "")
    if entry.get("arch") == "native":
        require(qemu == "native", name + " native target must use qemu_user=native")
    else:
        require(qemu.startswith("qemu-"), name + " missing qemu-user interpreter")

system_arches = {entry.get("arch") for entry in system_entries}
required_system_arches = {"x86_64", "aarch64", "armv7", "armv5", "mipsel", "mips"}
missing_system_arches = sorted(required_system_arches - system_arches)
require(not missing_system_arches, "system matrix missing arch coverage: " + ", ".join(missing_system_arches))

system_kernel_floors = {entry.get("kernel_floor") for entry in system_entries}
missing_system_floors = sorted({"current", "2.6", "3.x", "4.x"} - system_kernel_floors)
require(not missing_system_floors, "system matrix missing kernel floor coverage: " + ", ".join(missing_system_floors))

system_libcs = {entry.get("libc_family") for entry in system_entries}
missing_system_libcs = sorted({"musl", "uclibc"} - system_libcs)
require(not missing_system_libcs, "system matrix missing libc coverage: " + ", ".join(missing_system_libcs))

system_names = set()
for entry in system_entries:
    name = entry.get("name", "")
    require(name, "system environment missing name")
    require(name not in system_names, "duplicate system environment: " + name)
    system_names.add(name)
    for field in (
        "kernel_path",
        "rootfs_path",
        "busierbox_path",
        "qemu_binary",
        "qemu_machine",
        "qemu_cpu",
        "append_args",
        "kernel_floor",
        "libc_family",
    ):
        require(entry.get(field), name + " missing " + field)
    require(entry.get("enabled") is False, name + " must stay disabled in the example matrix")
    require(entry.get("busierbox_path", "").startswith("dist/busierbox-"), name + " busierbox_path must point at dist/busierbox-*")

print("qemu-matrix ok")
PY
