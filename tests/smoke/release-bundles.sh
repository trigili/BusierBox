#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/release-bundles.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

scripts/make-release --name smoke --targets native --payload-presets default --dry-run >"$work/dry-run.out"
grep -q 'would build target=native payload=default format=tgz' "$work/dry-run.out"
grep -q '^layout=symlink$' "$work/dry-run.out"
scripts/make-release --name format-smoke --targets native --payload-presets default --formats tgz,tar --dry-run >"$work/format-dry-run.out"
grep -q 'would build target=native payload=default format=tgz' "$work/format-dry-run.out"
grep -q 'would build target=native payload=default format=tar' "$work/format-dry-run.out"
scripts/make-release --name smoke --targets native --payload-presets default --copy-layout --dry-run >"$work/dry-run-copy.out"
grep -q '^layout=copy$' "$work/dry-run-copy.out"
python3 - <<'PY'
import importlib.machinery
import sys

sys.path.insert(0, "scripts")
mod = importlib.machinery.SourceFileLoader("make_release", "scripts/make-release").load_module()
resolved = {
    "TARGET_NAME": "mipsel-linux-4.x-musl",
    "TARGET_ARCH": "mipsel",
    "TARGET_LIBC": "musl",
    "TARGET_KERNEL_FLOOR": "4.x",
    "TARGET_CPU": "mips32r2-24kc",
    "TARGET_ABI": "default",
}
tuple_info = mod.tuple_metadata(resolved)
if tuple_info["path"] != "by-tuple/mipsel/musl/4.x/mips32r2-24kc":
    raise SystemExit(f"tuple path mismatch: {tuple_info['path']}")
aliases = mod.target_aliases({"target": "glinet-mt7621-openwrt-musl"}, resolved)
for alias in ("glinet-mt7621-openwrt-musl", "mipsel-linux-4.x-musl", "glinet-mt7621", "glinet-mt1300"):
    if alias not in aliases:
        raise SystemExit(f"missing device alias {alias}")
PY
scripts/make-release --name reverse-smoke --targets native --payload-presets survey-core --reverse-access-profiles builtin,ssh,socat --dry-run >"$work/reverse-dry-run.out"
grep -q 'would build target=native payload=survey-core format=tgz' "$work/reverse-dry-run.out"
grep -q 'would build target=native payload=builtin-core-shell format=tgz' "$work/reverse-dry-run.out"
grep -q 'would build target=native payload=ssh-operator format=tgz' "$work/reverse-dry-run.out"
grep -q 'would build target=native payload=socat-rescue format=tgz' "$work/reverse-dry-run.out"
if scripts/make-release --name bad-reverse --targets native --reverse-access-profiles no-such-profile --dry-run >"$work/bad-reverse.out" 2>"$work/bad-reverse.err"; then
    printf '%s\n' "expected bad reverse profile to fail" >&2
    exit 1
fi
grep -q 'invalid reverse access profile(s): no-such-profile' "$work/bad-reverse.err"

scripts/make-release --name matrix-smoke --matrix release/matrices/iot-lab.json --dry-run >"$work/matrix-dry-run.out"
grep -q '^version=2026.05.25$' "$work/matrix-dry-run.out"
python3 - "$work/matrix-dry-run.out" release/matrices/iot-lab.json <<'PY'
import json
import sys

dry_run = open(sys.argv[1], "r", encoding="utf-8").read()
matrix = json.load(open(sys.argv[2], "r", encoding="utf-8"))
for target in matrix["targets"]:
    for payload in matrix["payload_presets"]:
        expected = f"would build target={target} payload={payload} format=tgz"
        if expected not in dry_run:
            raise SystemExit(f"missing dry-run job: {expected}")
PY

cat >"$work/bad-target.json" <<'JSON'
{
  "name": "bad-target",
  "targets": ["no-such-target"],
  "payload_presets": ["default"]
}
JSON
if scripts/make-release --name bad --matrix "$work/bad-target.json" --dry-run >"$work/bad-target.out" 2>"$work/bad-target.err"; then
    printf '%s\n' "expected bad target matrix to fail" >&2
    exit 1
fi
grep -q 'unresolved target no-such-target' "$work/bad-target.err"

cat >"$work/bad-payload.json" <<'JSON'
{
  "name": "bad-payload",
  "targets": ["native"],
  "payload_presets": ["no-such-payload"]
}
JSON
if scripts/make-release --name bad --matrix "$work/bad-payload.json" --dry-run >"$work/bad-payload.out" 2>"$work/bad-payload.err"; then
    printf '%s\n' "expected bad payload matrix to fail" >&2
    exit 1
fi
grep -q 'missing payload preset no-such-payload' "$work/bad-payload.err"

cat >"$work/base-a.conf" <<'EOF'
BB_ZERO_ARG_MODE="help"
BB_RUNTIME_MODE="extract"
EOF
cat >"$work/base-b.conf" <<'EOF'
BB_ZERO_ARG_MODE="help"
BB_RUNTIME_MODE="core-only"
EOF
cat >"$work/config-matrix.json" <<EOF
{
  "name": "config-matrix",
  "targets": ["native"],
  "payload_presets": ["default"],
  "configs": ["$work/base-a.conf", "$work/base-b.conf"]
}
EOF
scripts/make-release --name config-matrix --matrix "$work/config-matrix.json" --dry-run >"$work/config-matrix.out"
grep -q "would build target=native payload=default format=tgz config=$work/base-a.conf" "$work/config-matrix.out"
grep -q "would build target=native payload=default format=tgz config=$work/base-b.conf" "$work/config-matrix.out"

cat >"$work/bad-config.json" <<EOF
{
  "name": "bad-config",
  "targets": ["native"],
  "payload_presets": ["default"],
  "configs": ["$work/no-such.conf"]
}
EOF
if scripts/make-release --name bad --matrix "$work/bad-config.json" --dry-run >"$work/bad-config.out" 2>"$work/bad-config.err"; then
    printf '%s\n' "expected bad config matrix to fail" >&2
    exit 1
fi
grep -q "missing config $work/no-such.conf" "$work/bad-config.err"

cat >"$work/reverse-matrix.json" <<'JSON'
{
  "name": "reverse-matrix",
  "targets": ["native"],
  "payload_presets": ["survey-core"],
  "reverse_access_profiles": ["ssh"]
}
JSON
scripts/make-release --name reverse-matrix --matrix "$work/reverse-matrix.json" --dry-run >"$work/reverse-matrix.out"
grep -q 'would build target=native payload=survey-core format=tgz' "$work/reverse-matrix.out"
grep -q 'would build target=native payload=ssh-operator format=tgz' "$work/reverse-matrix.out"

if [ ! -x dist/busierbox-native-full ]; then
    BUSIERBOX_CONFIG=presets/payload/default.conf BB_BUSYBOX_GROUPS="shell fileops disk process network text system" make package-native >/dev/null
fi

scripts/make-release \
    --name smoke \
    --targets native \
    --payload-presets default \
    --skip-build \
    --out-dir "$work/release" >"$work/release.out"

test -x "$work/release/bin/busierbox-native-default-full"
test -d "$work/release/by-tuple/native/host/host/host"
test -x "$work/release/by-tuple/native/host/host/host/bin/busierbox-native-default-full"
test -L "$work/release/by-tuple/native/host/host/host/bin/busierbox-native-default-full"
test -f "$work/release/by-tuple/native/host/host/host/README.txt"
test -f "$work/release/by-tuple/native/host/host/host/MANIFEST.txt"
test -f "$work/release/by-tuple/native/host/host/host/MANIFEST.json"
test -f "$work/release/by-tuple/native/host/host/host/configs/native-default.conf"
test -f "$work/release/by-tuple/native/host/host/host/manifests/busierbox-native-default-full.manifest.json"
test -f "$work/release/by-tuple/native/host/host/host/manifests/busierbox-native-default-full.payload-manifest.json"
test -d "$work/release/devices/native"
test -L "$work/release/devices/native/artifacts"
test -f "$work/release/devices/native/target.json"
test -f "$work/release/devices/native/README.txt"
test -f "$work/release/devices/native/notes.md"
test -x "$work/release/scripts/artifact-config"
test -x "$work/release/scripts/busierbox-server"
test -x "$work/release/scripts/configure-artifact"
test -x "$work/release/scripts/configure-all"
test -x "$work/release/scripts/verify-checksums"
test -x "$work/release/scripts/release-index"
test -x "$work/release/scripts/release-find"
test -x "$work/release/scripts/release-self-test"
"$work/release/scripts/configure-artifact" --help >"$work/configure-help.out" 2>&1 || test "$?" -eq 2
grep -q -- '--run-mode auto|foreground|background' "$work/configure-help.out"
grep -q -- '--session-policy single|reconnect|persistent' "$work/configure-help.out"
grep -q -- '--shell-provider auto|target-sh|payload-busybox-sh|payload-busybox-ash|payload-zsh|custom' "$work/configure-help.out"
grep -q -- '--zero-arg-log-mode none|quiet|status|verbose' "$work/configure-help.out"
grep -q -- '--noresidue-level best-effort|aggressive' "$work/configure-help.out"
if grep -q -- '--run-mode auto|oneshot' "$work/configure-help.out"; then
    printf '%s\n' "release-bundles: configure-artifact help advertised stale run mode" >&2
    exit 1
fi
test -f "$work/release/SHA256SUMS.original"
test -f "$work/release/RELEASE-QUICKSTART.txt"
test -f "$work/release/LICENSE"
test -f "$work/release/NOTICE"
test -f "$work/release/release.json"
test -f "$work/release/release-index.json"
test -f "$work/release/docs/README-release.md"
test -f "$work/release/docs/trailer-overrides.md"
test -f "$work/release/docs/cleanup-ledger.md"
test -f "$work/release/docs/command-queue.md"
test -f "$work/release/docs/gdbserver-workflow.md"
test -f "$work/release/docs/licensing.md"
test -f "$work/release/docs/manifest.md"
test -f "$work/release/docs/recovery.md"
test -f "$work/release/docs/survey-and-bringup.md"
test -f "$work/release.tar.gz"
grep -q 'scripts/busierbox-server --transport tls-shell' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'GPL-2.0-or-later' "$work/release/NOTICE"
grep -q 'GPL compatibility summary' "$work/release/docs/licensing.md"
grep -q 'scripts/busierbox-server --file-service --file-port 22204' "$work/release/RELEASE-QUICKSTART.txt"
grep -q './busierbox survey push' "$work/release/RELEASE-QUICKSTART.txt"
grep -q './busierbox config-push' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'receive-only file uploads' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'not an artifact sender' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'scripts/busierbox-server' "$work/release/release-index.json"

python3 -m json.tool "$work/release/release.json" >/dev/null
grep -q '"release_name": "smoke"' "$work/release/release.json"
grep -q '"build_status": "copied"' "$work/release/release.json"
python3 - "$work/release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
layout = data.get("layout", {})
if layout.get("mode") != "symlink":
    raise SystemExit("expected default symlink layout")
tuples = layout.get("tuples", {})
native_tuple = tuples.get("by-tuple/native/host/host/host")
if not native_tuple:
    raise SystemExit("missing native tuple layout metadata")
if native_tuple.get("manifest") != "by-tuple/native/host/host/host/MANIFEST.json":
    raise SystemExit("native tuple manifest metadata mismatch")
tuple_meta = native_tuple.get("tuple") or {}
if tuple_meta.get("discriminator") != "host":
    raise SystemExit("native tuple discriminator mismatch")
if tuple_meta.get("path_components", {}).get("kernel_floor") != "host":
    raise SystemExit("native tuple path component mismatch")
devices = layout.get("devices", {})
if devices.get("native", {}).get("tuple_path") != "by-tuple/native/host/host/host":
    raise SystemExit("native device alias mismatch")
artifact = data["artifacts"][0]
if artifact.get("tuple_path") != "by-tuple/native/host/host/host":
    raise SystemExit("artifact tuple path missing")
if artifact.get("tuple", {}).get("path") != artifact.get("tuple_path"):
    raise SystemExit("artifact tuple path drift")
if artifact.get("tuple_artifact") != "by-tuple/native/host/host/host/bin/busierbox-native-default-full":
    raise SystemExit("artifact tuple artifact missing")
summary = artifact.get("tuple_summary") or {}
for key in ("payload_manifest", "native_applets", "busybox_applets", "core_extraction_behavior", "trailer_overridable_fields", "command_queue", "noresidue_policy", "recovery_workflows"):
    if key not in summary:
        raise SystemExit(f"tuple summary missing {key}")
queue = summary.get("command_queue") or {}
if queue.get("enabled") != "no" or queue.get("default_enabled") is not False or queue.get("executes_commands") is not False:
    raise SystemExit(f"tuple summary command queue policy unsafe/missing: {queue!r}")
noresidue = summary.get("noresidue_policy") or {}
if noresidue.get("best_effort_cleanup") is not True or noresidue.get("forensic_no_trace") is not False:
    raise SystemExit(f"tuple summary no-residue policy unsafe/missing: {noresidue!r}")
recovery = summary.get("recovery_workflows") or {}
if (recovery.get("available") is not True or
        "evidence-push" not in recovery.get("evidence_actions", []) or
        recovery.get("requires_apply") is not True or
        recovery.get("stealth") is not False):
    raise SystemExit(f"tuple summary recovery workflows unsafe/missing: {recovery!r}")
compat = summary.get("compatibility") or {}
if compat.get("label") != "exact":
    raise SystemExit(f"tuple summary compatibility missing/exact mismatch: {compat!r}")
if "missing_tools" in summary or "missing_tool_reasons" in summary:
    raise SystemExit("tuple summary should default to positive inventory only")
host = data.get("build_host", {})
for key in ("system", "machine", "python_version"):
    if not host.get(key):
        raise SystemExit(f"missing build_host.{key}")
lock = data.get("source_lock", {})
if not lock.get("present"):
    raise SystemExit("source_lock metadata missing")
if lock.get("path") != "manifests/sources.lock.json":
    raise SystemExit("source_lock path mismatch")
if len(lock.get("sha256", "")) != 64:
    raise SystemExit("source_lock sha256 missing")
sources = {item.get("name"): item for item in lock.get("sources", [])}
for name in ("buildroot", "miniz", "doom-ascii"):
    if name not in sources:
        raise SystemExit(f"missing source lock entry: {name}")
    if not sources[name].get("version") or not sources[name].get("sha256"):
        raise SystemExit(f"incomplete source lock entry: {name}")
PY

python3 - "$work/release/by-tuple/native/host/host/host/MANIFEST.json" "$work/release/by-tuple/native/host/host/host/MANIFEST.txt" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if manifest.get("tuple", {}).get("path") != "by-tuple/native/host/host/host":
    raise SystemExit("tuple manifest path mismatch")
artifacts = manifest.get("artifacts", [])
if len(artifacts) != 1:
    raise SystemExit("tuple manifest artifact count mismatch")
summary = artifacts[0]
for key in ("payload_preset", "runtime_mode", "noresidue_level", "payload_manifest", "native_applets", "busybox_applets", "heavy_tools", "sha256", "config", "command_queue", "noresidue_policy", "recovery_workflows"):
    if key not in summary:
        raise SystemExit(f"tuple artifact summary missing {key}")
queue = summary.get("command_queue") or {}
if queue.get("enabled") != "no" or queue.get("default_enabled") is not False or queue.get("executes_commands") is not False:
    raise SystemExit(f"tuple manifest command queue policy unsafe/missing: {queue!r}")
noresidue = summary.get("noresidue_policy") or {}
if noresidue.get("best_effort_cleanup") is not True or noresidue.get("forensic_no_trace") is not False:
    raise SystemExit(f"tuple manifest no-residue policy unsafe/missing: {noresidue!r}")
recovery = summary.get("recovery_workflows") or {}
if (recovery.get("available") is not True or
        "evidence-push" not in recovery.get("evidence_actions", []) or
        recovery.get("requires_apply") is not True or
        recovery.get("stealth") is not False):
    raise SystemExit(f"tuple manifest recovery workflows unsafe/missing: {recovery!r}")
if (summary.get("compatibility") or {}).get("label") != "exact":
    raise SystemExit("tuple artifact compatibility baseline missing")
if "missing_tools" in summary or "missing_tool_reasons" in summary:
    raise SystemExit("tuple manifest should default to positive inventory only")
text = open(sys.argv[2], "r", encoding="utf-8").read()
for needle in (
    "compatibility_baseline=exact",
    "Payload variants:",
    "payload_manifest=",
    "compatibility=exact",
    "noresidue_level=",
    "noresidue_policy=",
    "recovery_workflows=",
    "busybox_applets=",
    "core_extraction=",
    "trailer_overridable_fields=",
    "reverse_access_defaults=",
    "command_queue_policy=",
    "Tuple quickstart:",
    "configure_trailer:",
    "first_contact:",
    "rshell_status:",
    "cleanup_ledger:",
    "recovery_plan:",
):
    if needle not in text:
        raise SystemExit(f"tuple MANIFEST.txt missing {needle}")
if "missing_tools=" in text:
    raise SystemExit("tuple MANIFEST.txt should not include missing tools by default")
PY

"$work/release/scripts/release-index" >/dev/null
scripts/release-index --release-dir "$work/release" >/dev/null
"$work/release/scripts/release-find" --arch native --libc host --kernel host --payload-preset default >"$work/release-find.out"
scripts/release-find --release-dir "$work/release" --arch native --libc host --kernel host --payload-preset default >"$work/release-find.wrapper.out"
cmp "$work/release-find.out" "$work/release-find.wrapper.out"
grep -q '^recommended_artifact=by-tuple/native/host/host/host/bin/busierbox-native-default-full$' "$work/release-find.out"
grep -q '^compatibility=exact$' "$work/release-find.out"
"$work/release/scripts/release-find" --device native --json >"$work/release-find.json"
python3 -m json.tool "$work/release-find.json" >/dev/null
python3 - "$work/release/release-index.json" <<'PY'
import json
import sys

index = json.load(open(sys.argv[1], "r", encoding="utf-8"))
row = index["artifacts"][0]
if row.get("tuple", {}).get("path") != row.get("tuple_path"):
    raise SystemExit("release-index tuple path drift")
if row.get("tuple", {}).get("path_components", {}).get("discriminator") != "host":
    raise SystemExit("release-index tuple components missing")
if (row.get("compatibility") or {}).get("label") != "exact":
    raise SystemExit("release-index compatibility baseline missing")
if sorted(index.get("tuples", {})) != ["by-tuple/native/host/host/host"]:
    raise SystemExit("release-index tuple keys mismatch")
PY
cat >"$work/survey-mipsel.json" <<'JSON'
{
  "schema": 2,
  "arch": "mipsel",
  "endianness": "little",
  "kernel": "4.14.221",
  "recommendations": {
    "target_arch_guess": "mipsel",
    "endian_guess": "little",
    "kernel_floor_guess": "4.x",
    "libc_guess": "musl"
  },
  "dirs": [
    {"path": "/tmp", "writable": true, "executable": false, "noexec": true, "free_bytes": 1048576}
  ]
}
JSON
"$work/release/scripts/release-find" --survey-json "$work/survey-mipsel.json" --json >"$work/release-find-survey.json"
python3 - "$work/release-find-survey.json" <<'PY'
import json
import sys

row = json.load(open(sys.argv[1], "r", encoding="utf-8"))
compat = row.get("compatibility") or {}
if compat.get("label") != "incompatible":
    raise SystemExit(f"expected incompatible native artifact for mipsel survey, got {compat!r}")
reasons = "\n".join(compat.get("reasons") or [])
if "arch mismatch" not in reasons or "/tmp noexec" not in reasons:
    raise SystemExit(f"survey compatibility reasons missing: {reasons}")
if "storage low" not in reasons:
    raise SystemExit(f"survey low-storage reason missing: {reasons}")
if compat.get("facts", {}).get("low_storage_free_bytes") != 1048576:
    raise SystemExit(f"survey low-storage fact missing: {compat.get('facts')!r}")
PY
cat >"$work/reality-unsafe.json" <<'JSON'
{
  "schema": 1,
  "checks": [
    {"name": "runtime_root_executable", "status": "fail", "ok": false, "detail": "permission denied"},
    {"name": "temporary_file", "status": "pass", "ok": true, "detail": "ok"}
  ]
}
JSON
"$work/release/scripts/release-find" --arch native --libc host --kernel host --reality-json "$work/reality-unsafe.json" >"$work/release-find-reality.out"
grep -q '^compatibility=unsafe$' "$work/release-find-reality.out"
grep -q '^compatibility_reason=runtime root execution failed in reality-test$' "$work/release-find-reality.out"
"$work/release/scripts/release-self-test" >/dev/null
scripts/release-self-test --release-dir "$work/release" >/dev/null

scripts/make-release \
    --name failure-smoke \
    --targets native,armv7-linux-3.x-musl \
    --payload-presets default \
    --skip-build \
    --out-dir "$work/failure-release" >"$work/failure-release.out"
test -x "$work/failure-release/bin/busierbox-native-default-full"
python3 - "$work/failure-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
artifacts = data.get("artifacts", [])
failures = data.get("failures", [])
if len(artifacts) != 2:
    raise SystemExit("expected copied and failed artifacts")
if len(failures) != 1:
    raise SystemExit("expected one failure")
failure = failures[0]
if failure.get("target") != "armv7-linux-3.x-musl":
    raise SystemExit("failure target mismatch")
if "missing artifact" not in failure.get("reason", ""):
    raise SystemExit("failure reason missing")
for key in ("payload_preset", "format", "config", "artifact", "trailer_support"):
    if not failure.get(key):
        raise SystemExit(f"failure missing {key}")
PY

scripts/make-release \
    --name copy-layout \
    --targets native \
    --payload-presets default \
    --skip-build \
    --copy-layout \
    --out-dir "$work/copy-release" >"$work/copy-release.out"
test -x "$work/copy-release/by-tuple/native/host/host/host/bin/busierbox-native-default-full"
test ! -L "$work/copy-release/by-tuple/native/host/host/host/bin/busierbox-native-default-full"
test -d "$work/copy-release/devices/native/artifacts"
python3 - "$work/copy-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if data.get("layout", {}).get("mode") != "copy":
    raise SystemExit("copy layout metadata mismatch")
PY

scripts/make-release \
    --name missing-reports \
    --targets native \
    --payload-presets default \
    --skip-build \
    --include-missing-reports \
    --out-dir "$work/missing-release" >"$work/missing-release.out"
test -f "$work/missing-release/build-report.json"
python3 - "$work/missing-release/release.json" "$work/missing-release/by-tuple/native/host/host/host/MANIFEST.json" "$work/missing-release/by-tuple/native/host/host/host/MANIFEST.txt" <<'PY'
import json
import sys

release = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if release.get("include_missing_reports") is not True:
    raise SystemExit("include_missing_reports flag missing")
if release.get("build_report") != "build-report.json":
    raise SystemExit("build report path missing")
summary = release["artifacts"][0].get("tuple_summary") or {}
if "missing_tools" not in summary or "missing_tool_reasons" not in summary:
    raise SystemExit("missing reports release lacks missing-tool inventory")
manifest = json.load(open(sys.argv[2], "r", encoding="utf-8"))
if "missing_tools" not in manifest.get("artifacts", [{}])[0]:
    raise SystemExit("tuple manifest lacks opt-in missing tools")
text = open(sys.argv[3], "r", encoding="utf-8").read()
if "missing_tools=" not in text:
    raise SystemExit("tuple MANIFEST.txt lacks opt-in missing tools")
PY

if [ -f dist/busierbox-mipsel-linux-4.x-musl-full ]; then
    scripts/make-release \
        --name glinet-layout \
        --targets glinet-mt7621-openwrt-musl \
        --payload-presets default \
        --skip-build \
        --out-dir "$work/glinet-release" >"$work/glinet-release.out"
    test -d "$work/glinet-release/by-tuple/mipsel/musl/4.x/mips32r2-24kc"
    test -L "$work/glinet-release/devices/glinet-mt1300/artifacts"
    test -f "$work/glinet-release/by-tuple/mipsel/musl/4.x/mips32r2-24kc/manifests/busierbox-glinet-mt7621-openwrt-musl-default-full.payload-manifest.json"
    python3 - "$work/glinet-release/release.json" "$work/glinet-release/by-tuple/mipsel/musl/4.x/mips32r2-24kc/MANIFEST.json" <<'PY'
import json
import sys

release = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if release.get("layout", {}).get("devices", {}).get("glinet-mt1300", {}).get("tuple_path") != "by-tuple/mipsel/musl/4.x/mips32r2-24kc":
    raise SystemExit("glinet device alias tuple mismatch")
artifact = release["artifacts"][0]
if artifact.get("build_status") != "copied":
    raise SystemExit("glinet skip-build artifact was not copied")
summary = artifact.get("tuple_summary") or {}
if not summary.get("busybox_applets"):
    raise SystemExit("glinet tuple summary lacks static BusyBox applets")
if not summary.get("payload_manifest"):
    raise SystemExit("glinet tuple summary lacks payload manifest")
manifest = json.load(open(sys.argv[2], "r", encoding="utf-8"))
if not manifest.get("artifacts", [{}])[0].get("busybox_applets"):
    raise SystemExit("glinet tuple manifest lacks static BusyBox applets")
PY
fi

if scripts/make-release \
    --name strict-failure \
    --targets native,armv7-linux-3.x-musl \
    --payload-presets default \
    --skip-build \
    --strict \
    --out-dir "$work/strict-failure" >"$work/strict-failure.out" 2>"$work/strict-failure.err"; then
    printf '%s\n' "expected strict release failure to exit nonzero" >&2
    exit 1
fi
python3 - "$work/strict-failure/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if len(data.get("failures", [])) != 1:
    raise SystemExit("strict release did not record failure")
PY

scripts/make-release \
    --name fail-fast \
    --targets armv7-linux-3.x-musl,native \
    --payload-presets default \
    --skip-build \
    --fail-fast \
    --out-dir "$work/fail-fast-release" >"$work/fail-fast-release.out"
python3 - "$work/fail-fast-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
artifacts = data.get("artifacts", [])
if len(artifacts) != 1:
    raise SystemExit("fail-fast should stop after first failure")
if artifacts[0].get("target") != "armv7-linux-3.x-musl":
    raise SystemExit("fail-fast first target mismatch")
if artifacts[0].get("build_status") != "failed":
    raise SystemExit("fail-fast first artifact did not fail")
PY

scripts/make-release \
    --name iot-metadata \
    --matrix release/matrices/iot-lab.json \
    --targets native \
    --payload-presets default \
    --skip-build \
    --out-dir "$work/iot-release" >"$work/iot-release.out"
python3 - "$work/iot-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if data.get("release_version") != "2026.05.25":
    raise SystemExit("release_version missing")
matrix = data.get("matrix", {})
if matrix.get("version") != "2026.05.25":
    raise SystemExit("matrix version missing")
include = matrix.get("include", {})
for key in ("artifact_config_helper", "config_examples", "checksums", "manifest", "docs"):
    if include.get(key) is not True:
        raise SystemExit(f"matrix include.{key} missing")
PY

cat >"$work/source-lock-matrix.json" <<'JSON'
{
  "name": "source-lock-matrix",
  "version": "test",
  "targets": ["native"],
  "payload_presets": ["default"],
  "include": {
    "source_lock": true
  }
}
JSON
scripts/make-release \
    --name source-lock \
    --matrix "$work/source-lock-matrix.json" \
    --skip-build \
    --out-dir "$work/source-lock-release" >"$work/source-lock-release.out"
test -f "$work/source-lock-release/sources.lock.json"
python3 - "$work/source-lock-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if data.get("release_version") != "test":
    raise SystemExit("source lock release version missing")
if data.get("include_sources_manifest") is not True:
    raise SystemExit("source lock include flag missing")
if data.get("matrix", {}).get("include", {}).get("source_lock") is not True:
    raise SystemExit("matrix source_lock include missing")
PY

scripts/make-release \
    --name reverse-smoke \
    --matrix "$work/reverse-matrix.json" \
    --skip-build \
    --out-dir "$work/reverse-release" >"$work/reverse-release.out"
test -x "$work/reverse-release/bin/busierbox-native-survey-core-full"
test -x "$work/reverse-release/bin/busierbox-native-ssh-operator-full"
python3 - "$work/reverse-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
profiles = data.get("matrix", {}).get("reverse_access_profiles")
if profiles != ["ssh"]:
    raise SystemExit(f"reverse profile metadata mismatch: {profiles!r}")
payloads = {item.get("payload_preset") for item in data.get("artifacts", [])}
if {"survey-core", "ssh-operator"} - payloads:
    raise SystemExit(f"missing reverse profile payloads: {payloads!r}")
for item in data.get("artifacts", []):
    if item.get("reverse_access_profiles") != ["ssh"]:
        raise SystemExit("artifact missing reverse profile metadata")
PY

scripts/make-release \
    --name config-smoke \
    --matrix "$work/config-matrix.json" \
    --skip-build \
    --out-dir "$work/config-release" >"$work/config-release.out"
test -x "$work/config-release/bin/busierbox-native-default-base-a-full"
test -x "$work/config-release/bin/busierbox-native-default-base-b-full"
test -f "$work/config-release/configs/native-default-base-a.conf"
test -f "$work/config-release/configs/native-default-base-b.conf"
grep -q '^BB_RUNTIME_MODE="extract"$' "$work/config-release/configs/native-default-base-a.conf"
grep -q '^BB_RUNTIME_MODE="core-only"$' "$work/config-release/configs/native-default-base-b.conf"
python3 - "$work/config-release/release.json" "$work/base-a.conf" "$work/base-b.conf" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
configs = data.get("matrix", {}).get("configs", [])
for expected in sys.argv[2:]:
    if expected not in configs:
        raise SystemExit(f"missing matrix config: {expected}")
artifacts = data.get("artifacts", [])
if len(artifacts) != 2:
    raise SystemExit("expected two config matrix artifacts")
for item in artifacts:
    if not item.get("base_config"):
        raise SystemExit("artifact missing base_config")
PY

scripts/make-release \
    --name format-smoke \
    --targets native \
    --payload-presets default \
    --formats tgz,tar \
    --skip-build \
    --out-dir "$work/format-release" >"$work/format-release.out"
test -x "$work/format-release/bin/busierbox-native-default-full"
test -x "$work/format-release/bin/busierbox-native-default-tar-full"
test -f "$work/format-release/configs/native-default.conf"
test -f "$work/format-release/configs/native-default-tar.conf"
python3 - "$work/format-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
artifacts = data.get("artifacts", [])
paths = [item.get("artifact") for item in artifacts]
configs = [item.get("config") for item in artifacts]
if len(artifacts) != 2:
    raise SystemExit("expected two format artifacts")
if len(paths) != len(set(paths)):
    raise SystemExit(f"duplicate artifact paths: {paths}")
if len(configs) != len(set(configs)):
    raise SystemExit(f"duplicate config paths: {configs}")
expected = {
    "bin/busierbox-native-default-full",
    "bin/busierbox-native-default-tar-full",
}
if set(paths) != expected:
    raise SystemExit(f"format artifact names mismatch: {paths}")
PY

(
    cd "$work/release"
    scripts/verify-checksums --original >/dev/null
)

"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --operator-host 192.0.2.55 \
    --transport builtin \
    --noresidue-level aggressive \
    --shell-port 22203 >/dev/null

"$work/release/scripts/artifact-config" show "$work/release/bin/busierbox-native-default-full" >"$work/show.out"
grep -q '^trailer_present=yes$' "$work/show.out"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/show.out"
grep -q '^BB_NORESIDUE_LEVEL=aggressive$' "$work/show.out"
test -x "$work/release/bin/busierbox-native-default-full"
"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --show >"$work/wrapper-show.out"
grep -q '^trailer_present=yes$' "$work/wrapper-show.out"
"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --export "$work/export.env"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/export.env"
test -f "$work/release/SHA256SUMS.configured"
(
    cd "$work/release"
    scripts/verify-checksums --configured >/dev/null
)

"$work/release/scripts/configure-all" --clear >/dev/null
"$work/release/scripts/artifact-config" show "$work/release/bin/busierbox-native-default-full" >"$work/clear.out"
grep -q '^trailer_present=no$' "$work/clear.out"

"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --import "$work/export.env" \
    --obfuscation xor >"$work/import-xor.out"
grep -q 'not encryption' "$work/import-xor.out"
"$work/release/scripts/artifact-config" show "$work/release/bin/busierbox-native-default-full" >"$work/xor-show.out"
grep -q '^trailer_present=yes$' "$work/xor-show.out"
grep -q '^encoding=xor$' "$work/xor-show.out"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/xor-show.out"
test -x "$work/release/bin/busierbox-native-default-full"
(
    cd "$work/release"
    scripts/verify-checksums --configured >/dev/null
)

printf '%s\n' "release-bundles ok"
