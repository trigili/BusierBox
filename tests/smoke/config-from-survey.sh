#!/bin/sh
set -eu

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

scripts/config-from-survey --format shell tests/fixtures/survey/glinet-mt7621.json >"$tmp/glinet.conf"
grep -q '^# compatibility=exact$' "$tmp/glinet.conf"
grep -q '^# compatibility_reason: arch inferred mipsel$' "$tmp/glinet.conf"
grep -q '^BB_TARGET_PRESET=glinet-mt7621-openwrt-musl$' "$tmp/glinet.conf"
grep -q '^BB_TARGET_ARCH=mipsel$' "$tmp/glinet.conf"
grep -q '^BB_TARGET_LIBC=musl$' "$tmp/glinet.conf"
grep -q '^BB_RUNTIME_ALLOW_EXTERNAL_WRITES=no$' "$tmp/glinet.conf"
grep -q '^BB_NORESIDUE_LEVEL=best-effort$' "$tmp/glinet.conf"
grep -q '^BB_ZERO_ARG_MODE=help$' "$tmp/glinet.conf"

scripts/config-from-survey --format json tests/fixtures/survey/generic-openwrt-mipsel.json >"$tmp/openwrt.json"
python3 -m json.tool "$tmp/openwrt.json" >/dev/null
grep -q '"BB_TARGET_ARCH": "mipsel"' "$tmp/openwrt.json"
grep -q '"BB_TARGET_LIBC": "musl"' "$tmp/openwrt.json"
python3 - "$tmp/openwrt.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
compat = doc["compatibility"]
assert compat["schema"] == 1
assert compat["label"] in {"exact", "likely", "heuristic"}
assert any(reason.startswith("arch inferred ") for reason in compat["reasons"])
assert any(reason.startswith("libc inferred ") for reason in compat["reasons"])
PY

scripts/config-from-survey --format shell tests/fixtures/survey/ancient-mipsel-uclibc-2.4.json >"$tmp/ancient.conf"
grep -q '^BB_TARGET_PRESET='"'"''"'"'$' "$tmp/ancient.conf"
grep -q '^BB_TARGET_ARCH=mipsel$' "$tmp/ancient.conf"
grep -q '^BB_TARGET_ENDIAN=little$' "$tmp/ancient.conf"
grep -q '^BB_TARGET_LIBC=uclibc$' "$tmp/ancient.conf"
grep -q '^BB_KERNEL_FLOOR=2.4$' "$tmp/ancient.conf"
grep -q '^# compatibility=heuristic$' "$tmp/ancient.conf"
grep -q '^# compatibility_reason: no target preset selected$' "$tmp/ancient.conf"

scripts/config-from-survey --format json tests/fixtures/survey/bigendian-mips-uclibc-2.6.json >"$tmp/mipseb.json"
python3 - "$tmp/mipseb.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
cfg = doc["recommendations"]
assert cfg["BB_TARGET_PRESET"] == ""
assert cfg["BB_TARGET_ARCH"] == "mips"
assert cfg["BB_TARGET_ENDIAN"] == "big"
assert cfg["BB_TARGET_LIBC"] == "uclibc"
assert cfg["BB_KERNEL_FLOOR"] == "2.6"
compat = doc["compatibility"]
assert compat["label"] == "heuristic"
assert "arch inferred mips" in compat["reasons"]
assert "libc inferred uclibc" in compat["reasons"]
assert "kernel floor 2.6" in compat["reasons"]
assert "no target preset selected" in compat["reasons"]
PY

cat >"$tmp/reality-bad-runtime.json" <<'EOF'
{
  "schema": 1,
  "checks": [
    {"name": "runtime_root_writable", "type": "capability", "status": "pass", "ok": true, "available": true, "skipped": false, "detail": "ok"},
    {"name": "runtime_root_executable", "type": "capability", "status": "fail", "ok": false, "available": false, "skipped": false, "detail": "permission denied"},
    {"name": "temporary_file", "type": "capability", "status": "fail", "ok": false, "available": false, "skipped": false, "detail": "read-only filesystem"},
    {"name": "extract_core_payload", "type": "capability", "status": "fail", "ok": false, "available": false, "skipped": false, "detail": "extract failed"},
    {"name": "exec_payload_busybox", "type": "capability", "status": "fail", "ok": false, "available": false, "skipped": false, "detail": "exec failed"},
    {"name": "tmp_noexec", "type": "constraint", "status": "pass", "ok": true, "detected": true, "skipped": false, "detail": "detected"},
    {"name": "rootfs_read_only", "type": "constraint", "status": "pass", "ok": true, "detected": true, "skipped": false, "detail": "detected"},
    {"name": "procfs_partial", "type": "constraint", "status": "pass", "ok": true, "detected": true, "skipped": false, "detail": "detected"},
    {"name": "ptrace", "type": "capability", "status": "fail", "ok": false, "available": false, "skipped": false, "detail": "not permitted"}
  ],
  "summary": {
    "operator_pass": 0,
    "operator_fail": 0,
    "operator_skipped": 3,
    "constraints": {
      "tmp_noexec": true,
      "rootfs_read_only": true,
      "procfs_partial": true
    }
  }
}
EOF
scripts/config-from-survey --format shell --reality-json "$tmp/reality-bad-runtime.json" tests/fixtures/survey/glinet-mt7621.json >"$tmp/reality.conf"
grep -q '^BB_RUNTIME_MODE=core-only$' "$tmp/reality.conf"
grep -q '^# WARNING: reality-test could not execute from the runtime root; prefer core-only$' "$tmp/reality.conf"
grep -q '^# WARNING: reality-test detected /tmp noexec; avoid extracting there$' "$tmp/reality.conf"
scripts/config-from-survey --format json --reality-json "$tmp/reality-bad-runtime.json" tests/fixtures/survey/glinet-mt7621.json >"$tmp/reality.json"
python3 -m json.tool "$tmp/reality.json" >/dev/null
python3 - "$tmp/reality.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert doc["compatibility"]["label"] == "unsafe"
assert "runtime root execution failed in reality-test" in doc["compatibility"]["reasons"]
assert "core payload extraction failed in reality-test" in doc["compatibility"]["reasons"]
assert "read-only rootfs constraint" in doc["compatibility"]["reasons"]
assert "procfs partial/broken: survey evidence may be incomplete" in doc["compatibility"]["reasons"]
assert "ptrace unavailable: avoid debugger payloads" in doc["compatibility"]["reasons"]
assert doc["recommendations"]["BB_RUNTIME_MODE"] == "core-only"
facts = doc["facts"]
assert facts["payload_possible"] is False
assert facts["reality"]["runtime_root_executable"] == "fail"
assert facts["reality"]["tmp_noexec_detected"] is True
assert facts["reality"]["rootfs_read_only_detected"] is True
assert facts["reality"]["procfs_partial_detected"] is True
assert facts["reality"]["ptrace"] == "fail"
assert facts["reality"]["operator_skipped"] == 3
PY

cat >"$tmp/reality-indexed.json" <<'EOF'
{
  "schema": 1,
  "checks": [
    {"name": "tmp_noexec", "type": "constraint", "status": "pass", "ok": true, "detected": true, "skipped": false, "detail": "indexed true"},
    {"name": "runtime_root_executable", "type": "capability", "status": "fail", "ok": false, "available": false, "skipped": false, "detail": "permission denied"},
    {"name": "tmp_noexec", "type": "constraint", "status": "pass", "ok": true, "detected": false, "skipped": false, "detail": "stale duplicate"}
  ],
  "checks_by_name": {
    "tmp_noexec": [0]
  },
  "summary": {
    "operator_pass": 0,
    "operator_fail": 0,
    "operator_skipped": 0,
    "constraints": {
      "tmp_noexec": false
    }
  }
}
EOF
scripts/config-from-survey --format json --reality-json "$tmp/reality-indexed.json" tests/fixtures/survey/glinet-mt7621.json >"$tmp/reality-indexed.out"
python3 - "$tmp/reality-indexed.out" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
facts = doc["facts"]["reality"]
assert facts["tmp_noexec_detected"] is True
assert facts["runtime_root_executable"] == "fail"
assert doc["recommendations"]["BB_RUNTIME_MODE"] == "core-only"
PY

cat >"$tmp/reality-summary-only.json" <<'EOF'
{
  "schema": 1,
  "checks": [],
  "summary": {
    "operator_pass": 0,
    "operator_fail": 0,
    "operator_skipped": 3,
    "constraints": {
      "tmp_noexec": true,
      "rootfs_read_only": true,
      "procfs_partial": true
    }
  }
}
EOF
scripts/config-from-survey --format json --reality-json "$tmp/reality-summary-only.json" tests/fixtures/survey/glinet-mt7621.json >"$tmp/reality-summary-only.out"
python3 - "$tmp/reality-summary-only.out" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], encoding="utf-8"))
facts = doc["facts"]["reality"]
assert facts["tmp_noexec_detected"] is True
assert facts["rootfs_read_only_detected"] is True
assert facts["procfs_partial_detected"] is True
assert "read-only rootfs constraint" in doc["compatibility"]["reasons"]
assert "procfs partial/broken: survey evidence may be incomplete" in doc["compatibility"]["reasons"]
assert facts["operator_skipped"] == 3
PY

scripts/config-from-survey --write-config "$tmp/low.conf" tests/fixtures/survey/unknown-low-disk.json
grep -q '^BB_RUNTIME_MODE=core-only$' "$tmp/low.conf"
grep -q '^BB_RUNTIME_ROOT=/tmp/.busierbox$' "$tmp/low.conf"
grep -q '^# WARNING:' "$tmp/low.conf"

scripts/config-from-survey --format shell tests/fixtures/survey/native-rich-recommendations.json >"$tmp/native.conf"
grep -q '^BB_TARGET_PRESET='"'"''"'"'$' "$tmp/native.conf"
grep -q '^BB_PAYLOAD_PRESET=builtin-core-shell$' "$tmp/native.conf"
grep -q '^BB_RUNTIME_MODE=extract$' "$tmp/native.conf"
grep -q '^BB_RSHELL_TRANSPORT=none$' "$tmp/native.conf"
grep -q '^# WARNING: sample warning from native survey$' "$tmp/native.conf"
! grep -q '^BB_TARGET_PRESET=auto$' "$tmp/native.conf"

scripts/config-from-survey --format shell --prefer-rshell ssh --allow-network-autorun tests/fixtures/survey/glinet-mt7621.json >"$tmp/ssh.conf"
grep -q '^BB_PAYLOAD_PRESET=ssh-operator$' "$tmp/ssh.conf"
grep -q '^BB_ZERO_ARG_MODE=rshell$' "$tmp/ssh.conf"
grep -q '^BB_RSHELL_TRANSPORT=ssh$' "$tmp/ssh.conf"

printf '%s\n' "config-from-survey ok"
