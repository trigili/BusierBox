#!/bin/sh
set -eu

python3 - <<'PY'
import importlib.machinery
import sys

sys.path.insert(0, "scripts")
mod = importlib.machinery.SourceFileLoader("make_release", "scripts/make-release").load_module()

resolved = {
    "TARGET_NAME": "router",
    "TARGET_ARCH": " MIPSEL ",
    "TARGET_LIBC": " MUSL ",
    "TARGET_KERNEL_FLOOR": "4.X",
    "TARGET_CPU": "mips/24kc",
    "TARGET_ABI": "default",
    "TARGET_ENDIAN": " little ",
}
info = mod.tuple_metadata(resolved)
if info["path"] != "by-tuple/mipsel/musl/4.x/mips-24kc":
    raise SystemExit(f"tuple-consistency: normalized tuple path mismatch: {info['path']}")
if info["arch"] != "mipsel" or info["libc"] != "musl" or info["kernel_floor"] != "4.x":
    raise SystemExit("tuple-consistency: raw tuple fields were not normalized")
if info["path_components"]["discriminator"] != "mips-24kc":
    raise SystemExit("tuple-consistency: discriminator component mismatch")
mod.validate_tuple_metadata(info, "normalized")

abi_resolved = {
    "TARGET_ARCH": "armv7",
    "TARGET_LIBC": "musl",
    "TARGET_KERNEL_FLOOR": "3.x",
    "TARGET_CPU": "generic",
    "TARGET_ABI": "eabihf",
}
abi_info = mod.tuple_metadata(abi_resolved)
if abi_info["path"] != "by-tuple/armv7/musl/3.x/eabihf":
    raise SystemExit(f"tuple-consistency: ABI discriminator mismatch: {abi_info['path']}")

def quiet_die(_msg, code=1):
    raise SystemExit(code)

mod.die = quiet_die

bad = dict(abi_info)
bad["kernel_floor"] = "unknown"
try:
    mod.validate_tuple_metadata(bad, "bad")
except SystemExit:
    pass
else:
    raise SystemExit("tuple-consistency: incomplete tuple metadata was accepted")

drift = dict(abi_info)
drift["path"] = "by-tuple/armv7/musl/unknown/eabihf"
try:
    mod.validate_tuple_metadata(drift, "drift")
except SystemExit:
    pass
else:
    raise SystemExit("tuple-consistency: tuple path drift was accepted")
PY

printf '%s\n' "tuple-consistency ok"
