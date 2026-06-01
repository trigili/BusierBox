#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/release-bundles.XXXXXX")
failure_artifact_saved=
failure_sha_saved=
failure_artifact=
failure_sha=

restore_hidden_failure_artifact() {
    if [ -n "$failure_artifact_saved" ] && [ -e "$failure_artifact_saved" ]; then
        mv "$failure_artifact_saved" "$failure_artifact"
        failure_artifact_saved=
    fi
    if [ -n "$failure_sha_saved" ] && [ -e "$failure_sha_saved" ]; then
        mv "$failure_sha_saved" "$failure_sha"
        failure_sha_saved=
    fi
}

hide_failure_artifact() {
    failure_target=${failure_target:-armv7-linux-3.x-musl}
    failure_artifact="dist/grit-$failure_target-eabihf-full"
    failure_sha="$failure_artifact.sha256"
    if [ -e "$failure_artifact" ] && [ -z "$failure_artifact_saved" ]; then
        failure_artifact_saved="$work/$(basename "$failure_artifact").saved"
        mv "$failure_artifact" "$failure_artifact_saved"
    fi
    if [ -e "$failure_sha" ] && [ -z "$failure_sha_saved" ]; then
        failure_sha_saved="$work/$(basename "$failure_sha").saved"
        mv "$failure_sha" "$failure_sha_saved"
    fi
}

cleanup() {
    restore_hidden_failure_artifact
    rm -rf "$work"
}

trap cleanup EXIT HUP INT TERM

export GRIT_RSHELL_SESSION_POLICY=single

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
built = {
    "by-tuple/armv7/musl/4.x/generic": {
        "tuple": {
            "arch": "armv7",
            "libc": "musl",
            "kernel_floor": "4.x",
            "discriminator": "generic",
        }
    }
}
device_tuple = mod.tuple_metadata({
    "TARGET_ARCH": "armv7",
    "TARGET_LIBC": "musl",
    "TARGET_KERNEL_FLOOR": "4.x",
    "TARGET_CPU": "cortex-a7",
    "TARGET_ABI": "eabi",
})
if mod.preferred_tuple_path_for_alias(device_tuple, built) != "by-tuple/armv7/musl/4.x/generic":
    raise SystemExit("device tuple did not fall back to generic tuple")
PY
scripts/make-release --name reverse-smoke --targets native --payload-presets survey-core --reverse-access-profiles builtin,ssh,socat --dry-run >"$work/reverse-dry-run.out"
grep -q 'would build target=native payload=survey-core format=tgz' "$work/reverse-dry-run.out"
grep -q 'would build target=native payload=builtin-core-shell format=tgz' "$work/reverse-dry-run.out"
grep -q 'would build target=native payload=ssh-operator format=tgz' "$work/reverse-dry-run.out"
grep -q 'would build target=native payload=socat-rescue format=tgz' "$work/reverse-dry-run.out"
scripts/make-release --name full-smoke --matrix tests/matrix/release-full.json --dry-run >"$work/full-dry-run.out"
python3 - "$work/full-dry-run.out" <<'PY'
import sys

lines = [line for line in open(sys.argv[1], encoding="utf-8") if line.startswith("would build ")]
if len(lines) != 112:
    raise SystemExit(f"release-full should be 16 generic targets x 7 presets, got {len(lines)}")
for forbidden in ("glinet-", "tplink-", "asus-", "dlink-", "linksys-", "netgear-"):
    if any(f"target={forbidden}" in line for line in lines):
        raise SystemExit(f"release-full built device-specific target: {forbidden}")
for expected in (
    "target=mips-linux-2.4-uclibc",
    "target=mipsel-linux-3.x-musl",
    "target=aarch64-linux-3.x-musl",
    "payload=full-debug",
    "payload=socat-rescue",
):
    if not any(expected in line for line in lines):
        raise SystemExit(f"release-full missing {expected}")
PY
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
GRIT_ZERO_ARG_MODE="help"
GRIT_RUNTIME_MODE="extract"
EOF
cat >"$work/base-b.conf" <<'EOF'
GRIT_ZERO_ARG_MODE="help"
GRIT_RUNTIME_MODE="core-only"
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

if [ ! -x dist/grit-native-full ]; then
    GRIT_CONFIG=presets/payload/default.conf GRIT_BUSYBOX_GROUPS="shell fileops disk process network text system" make package-native >/dev/null
fi

scripts/make-release \
    --name smoke \
    --targets native \
    --payload-presets default \
    --skip-build \
    --out-dir "$work/release" >"$work/release.out"

test -x "$work/release/bin/grit-native-default-full"
test -d "$work/release/by-tuple/native/host/host/host"
test -x "$work/release/by-tuple/native/host/host/host/bin/grit-native-default-full"
test -L "$work/release/by-tuple/native/host/host/host/bin/grit-native-default-full"
test -f "$work/release/by-tuple/native/host/host/host/README.txt"
test -f "$work/release/by-tuple/native/host/host/host/MANIFEST.txt"
test -f "$work/release/by-tuple/native/host/host/host/MANIFEST.json"
test -f "$work/release/by-tuple/native/host/host/host/configs/native-default.conf"
test -f "$work/release/by-tuple/native/host/host/host/manifests/grit-native-default-full.manifest.json"
test -f "$work/release/by-tuple/native/host/host/host/manifests/grit-native-default-full.payload-manifest.json"
test -d "$work/release/devices/native"
test -L "$work/release/devices/native/artifacts"
test -f "$work/release/devices/native/target.json"
test -f "$work/release/devices/native/README.txt"
test -f "$work/release/devices/native/notes.md"
test -x "$work/release/scripts/lib/artifact-config"
test -x "$work/release/scripts/grit-server"
test -x "$work/release/scripts/configure-artifact"
test -x "$work/release/scripts/configure-all"
test -x "$work/release/scripts/verify-checksums"
test -x "$work/release/scripts/lib/release-index"
test -x "$work/release/scripts/lib/release-find"
test -x "$work/release/scripts/lib/release-self-test"
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
test -f "$work/release/LICENSE.grit"
test -f "$work/release/NOTICE"
test -f "$work/release/LICENSES/busybox.txt"
test -f "$work/release/LICENSES/buildroot.txt"
test -f "$work/release/LICENSES/doom-ascii.txt"
test -f "$work/release/LICENSES/miniz.txt"
test -f "$work/release/release.json"
test -f "$work/release/release-index.json"
test -f "$work/release/manifests/license-policy.json"
test -f "$work/release/sources.lock.json"
test -f "$work/release/manifests/sources.lock.json"
cmp "$work/release/sources.lock.json" "$work/release/manifests/sources.lock.json"
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
grep -q 'scripts/grit-server --transport tls-shell' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'GPL-2.0-or-later' "$work/release/LICENSE.grit"
grep -q 'GPL-2.0-or-later' "$work/release/NOTICE"
grep -q 'third_party/busybox/LICENSE' "$work/release/LICENSES/busybox.txt"
grep -q 'manifests/sources.lock.json' "$work/release/LICENSES/buildroot.txt"
grep -q 'GRIT_DOOM_WAD_PATH' "$work/release/LICENSES/doom-ascii.txt"
grep -q 'third_party/miniz/LICENSE' "$work/release/LICENSES/miniz.txt"
grep -q 'GPL compatibility summary' "$work/release/docs/licensing.md"
python3 -m json.tool "$work/release/manifests/license-policy.json" >/dev/null
grep -q '"combined_gplv2_compatible": true' "$work/release/manifests/license-policy.json"
grep -q 'scripts/grit-server --file-service --file-port 22204' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'scripts/grit-server --tui' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'scripts/grit-server --transport probe --probe-port 22207' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'probe --start' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'probe config --write-config configs/grit.conf' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'release stage SELECTOR' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'release stage by_device_payload_preset:glinet-mt1300:survey-core' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'release stage by_tuple_payload_preset:by-tuple/mipsel/musl/4.x/mips32r2-24kc:ssh-operator' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'serve-binary --start bin/grit-...-full grit' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'configure grit --operator-host 192.168.8.241 --transport builtin --shell-port 22203' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'configure grit --zero-arg-mode rshell --retry-count 12 --retry-interval 60' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'configure grit --command-queue-enable yes --command-queue-poll-interval 300' "$work/release/RELEASE-QUICKSTART.txt"
grep -q './grit survey push' "$work/release/RELEASE-QUICKSTART.txt"
grep -q './grit reality-test push' "$work/release/RELEASE-QUICKSTART.txt"
grep -q './grit config-push' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'stage release artifacts' "$work/release/RELEASE-QUICKSTART.txt"
grep -q 'queue commands for targets that' "$work/release/RELEASE-QUICKSTART.txt"
if grep -q 'not an artifact sender' "$work/release/RELEASE-QUICKSTART.txt"; then
    printf '%s\n' "release-bundles: quickstart still says grit-server cannot send artifacts" >&2
    exit 1
fi
if grep -q -- '--survey-bootstrap-port' "$work/release/RELEASE-QUICKSTART.txt"; then
    printf '%s\n' "release-bundles: quickstart advertised stale probe port flag" >&2
    exit 1
fi
grep -q 'configure grit --operator-host 192.168.8.241 --transport builtin --shell-port 22203' "$work/release/docs/README-release.md"
grep -q 'release stage by_device_payload_preset:glinet-mt1300:survey-core' "$work/release/docs/README-release.md"
grep -q 'release stage by_tuple_payload_preset:by-tuple/mipsel/musl/4.x/mips32r2-24kc:ssh-operator' "$work/release/docs/README-release.md"
grep -q 'original release artifact remains pristine' "$work/release/docs/README-release.md"
grep -q 'scripts/grit-server' "$work/release/release-index.json"

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
summary = data["artifacts"][0].get("tuple_summary") or {}
if not isinstance(summary.get("tool_provider_status"), dict):
    raise SystemExit("release tuple summary lacks provider status object")
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
if artifact.get("tuple_artifact") != "by-tuple/native/host/host/host/bin/grit-native-default-full":
    raise SystemExit("artifact tuple artifact missing")
summary = artifact.get("tuple_summary") or {}
for key in ("payload_manifest", "native_applets", "busybox_applets", "core_extraction_behavior", "trailer_overridable_fields", "command_queue", "noresidue_policy", "recovery_workflows", "doom_wads"):
    if key not in summary:
        raise SystemExit(f"tuple summary missing {key}")
reverse = summary.get("reverse_access") or {}
reverse_policy = reverse.get("session_policy_summary") or {}
if (reverse.get("session_policy") != "single" or
        reverse.get("session_policy_valid") is not True or
        reverse.get("session_policy_errors") != [] or
        reverse_policy.get("retry_scope") != "pre-connect" or
        reverse_policy.get("retry_until_first_connection") is not True or
        reverse_policy.get("stop_after_first_success") is not True or
        reverse_policy.get("reconnect_after_disconnect") is not False or
        reverse_policy.get("persistent_lifecycle") is not False or
        reverse_policy.get("fresh_session_on_reconnect") is not False or
        reverse_policy.get("session_resume_supported") is not False or
        reverse_policy.get("post_disconnect_retry_count") != "0"):
    raise SystemExit(f"tuple summary reverse access policy missing: {reverse!r}")
queue = summary.get("command_queue") or {}
if (queue.get("enabled") != "no" or
        queue.get("default_enabled") is not False or
        queue.get("token_required") is not True or
        queue.get("token_configured") is not False or
        queue.get("policy_valid") is not True or
        queue.get("policy_errors") != [] or
        queue.get("arbitrary_policy_requested") is not False or
        queue.get("arbitrary_execution_allowed") is not False or
        queue.get("poll_interval_sec") != "5" or
        queue.get("poll_jitter_pct") != "0" or
        queue.get("poll_backoff") != "none" or
        queue.get("poll_max_interval_sec") != "300" or
        queue.get("max_polls") != "0" or
        not str(queue.get("daemon_state_file", "")).endswith("/run/command-queue-daemon.state") or
        queue.get("daemon_state_file_supported") is not True or
        queue.get("daemon_status_supported") is not True or
        queue.get("daemon_stop_supported") is not True or
        queue.get("poll_transport_supported") is not True or
        queue.get("live_polling_supported") is not True or
        queue.get("delivery_supported") is not False or
        queue.get("result_upload_supported") is not True or
        queue.get("executes_commands") is not False):
    raise SystemExit(f"tuple summary command queue policy unsafe/missing: {queue!r}")
mode_records = queue.get("mode_records") or []
mode_summary = queue.get("mode_summary") or {}
mode_api = (queue.get("api_collections") or {}).get("mode_records") or {}
if (len(mode_records) != 5 or
        mode_records[1].get("mode") != "poll" or
        mode_records[1].get("target_polling_supported") is not True or
        mode_records[1].get("execution_supported") is not False or
        queue.get("mode_records_by_mode", {}).get("poll") != [1] or
        queue.get("mode_records_by_lifecycle", {}).get("single-poll") != [1] or
        queue.get("mode_records_by_would_poll_if_configured", {}).get("true") != [1, 2, 3] or
        queue.get("mode_records_by_target_polling_supported", {}).get("true") != [1, 2, 3] or
        queue.get("mode_records_by_delivery_supported", {}).get("false") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_result_upload_supported", {}).get("true") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_execution_supported", {}).get("false") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_active_control_channel", {}).get("false") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_operator_supplied_command_execution", {}).get("false") != [0, 1, 2, 3, 4] or
        mode_summary.get("mode_count") != 5 or
        mode_summary.get("target_polling_supported_mode_count") != 3 or
        mode_summary.get("delivery_supported_mode_count") != 0 or
        mode_summary.get("result_upload_supported_mode_count") != 5 or
        mode_summary.get("operator_supplied_command_execution_mode_count") != 0 or
        mode_summary.get("execution_supported_mode_count") != 0 or
        mode_api.get("primary_key") != "mode" or
        "mode_records_by_delivery_supported" not in (mode_api.get("indexes") or []) or
        "mode_records_by_result_upload_supported" not in (mode_api.get("indexes") or []) or
        "mode_records_by_operator_supplied_command_execution" not in (mode_api.get("indexes") or [])):
    raise SystemExit(f"tuple summary command queue mode metadata missing: {queue!r}")
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
for key in ("payload_preset", "runtime_mode", "noresidue_level", "payload_manifest", "native_applets", "busybox_applets", "heavy_tools", "sha256", "config", "command_queue", "noresidue_policy", "recovery_workflows", "doom_wads"):
    if key not in summary:
        raise SystemExit(f"tuple artifact summary missing {key}")
reverse = summary.get("reverse_access") or {}
reverse_policy = reverse.get("session_policy_summary") or {}
if (reverse.get("session_policy") != "single" or
        reverse.get("session_policy_valid") is not True or
        reverse.get("session_policy_errors") != [] or
        reverse_policy.get("retry_scope") != "pre-connect" or
        reverse_policy.get("retry_until_first_connection") is not True or
        reverse_policy.get("stop_after_first_success") is not True or
        reverse_policy.get("reconnect_after_disconnect") is not False or
        reverse_policy.get("persistent_lifecycle") is not False or
        reverse_policy.get("fresh_session_on_reconnect") is not False or
        reverse_policy.get("session_resume_supported") is not False or
        reverse_policy.get("post_disconnect_retry_count") != "0"):
    raise SystemExit(f"tuple manifest reverse access policy missing: {reverse!r}")
queue = summary.get("command_queue") or {}
if (queue.get("enabled") != "no" or
        queue.get("default_enabled") is not False or
        queue.get("token_required") is not True or
        queue.get("token_configured") is not False or
        queue.get("policy_valid") is not True or
        queue.get("policy_errors") != [] or
        queue.get("arbitrary_policy_requested") is not False or
        queue.get("arbitrary_execution_allowed") is not False or
        queue.get("poll_interval_sec") != "5" or
        queue.get("poll_jitter_pct") != "0" or
        queue.get("poll_backoff") != "none" or
        queue.get("poll_max_interval_sec") != "300" or
        queue.get("max_polls") != "0" or
        not str(queue.get("daemon_state_file", "")).endswith("/run/command-queue-daemon.state") or
        queue.get("daemon_state_file_supported") is not True or
        queue.get("daemon_status_supported") is not True or
        queue.get("daemon_stop_supported") is not True or
        queue.get("poll_transport_supported") is not True or
        queue.get("live_polling_supported") is not True or
        queue.get("delivery_supported") is not False or
        queue.get("result_upload_supported") is not True or
        queue.get("executes_commands") is not False):
    raise SystemExit(f"tuple manifest command queue policy unsafe/missing: {queue!r}")
mode_records = queue.get("mode_records") or []
mode_summary = queue.get("mode_summary") or {}
mode_api = (queue.get("api_collections") or {}).get("mode_records") or {}
if (len(mode_records) != 5 or
        mode_records[1].get("mode") != "poll" or
        mode_records[1].get("target_polling_supported") is not True or
        mode_records[1].get("execution_supported") is not False or
        queue.get("mode_records_by_mode", {}).get("poll") != [1] or
        queue.get("mode_records_by_lifecycle", {}).get("single-poll") != [1] or
        queue.get("mode_records_by_would_poll_if_configured", {}).get("true") != [1, 2, 3] or
        queue.get("mode_records_by_target_polling_supported", {}).get("true") != [1, 2, 3] or
        queue.get("mode_records_by_delivery_supported", {}).get("false") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_result_upload_supported", {}).get("true") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_execution_supported", {}).get("false") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_active_control_channel", {}).get("false") != [0, 1, 2, 3, 4] or
        queue.get("mode_records_by_operator_supplied_command_execution", {}).get("false") != [0, 1, 2, 3, 4] or
        mode_summary.get("mode_count") != 5 or
        mode_summary.get("target_polling_supported_mode_count") != 3 or
        mode_summary.get("delivery_supported_mode_count") != 0 or
        mode_summary.get("result_upload_supported_mode_count") != 5 or
        mode_summary.get("operator_supplied_command_execution_mode_count") != 0 or
        mode_summary.get("execution_supported_mode_count") != 0 or
        mode_api.get("primary_key") != "mode" or
        "mode_records_by_delivery_supported" not in (mode_api.get("indexes") or []) or
        "mode_records_by_result_upload_supported" not in (mode_api.get("indexes") or []) or
        "mode_records_by_operator_supplied_command_execution" not in (mode_api.get("indexes") or [])):
    raise SystemExit(f"tuple manifest command queue mode metadata missing: {queue!r}")
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
    "doom_wads=",
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

"$work/release/scripts/lib/release-index" >/dev/null
scripts/lib/release-index --release-dir "$work/release" >/dev/null
"$work/release/scripts/lib/release-find" --arch native --libc host --kernel host --payload-preset default >"$work/release-find.out"
scripts/lib/release-find --release-dir "$work/release" --arch native --libc host --kernel host --payload-preset default >"$work/release-find.wrapper.out"
cmp "$work/release-find.out" "$work/release-find.wrapper.out"
grep -q '^recommended_artifact=by-tuple/native/host/host/host/bin/grit-native-default-full$' "$work/release-find.out"
grep -q '^compatibility=exact$' "$work/release-find.out"
"$work/release/scripts/lib/release-find" --device native --json >"$work/release-find.json"
python3 -m json.tool "$work/release-find.json" >/dev/null
python3 - "$work/release-find.json" <<'PY'
import json
import sys

row = json.load(open(sys.argv[1], "r", encoding="utf-8"))
selection = row.get("selection") or {}
if selection.get("selected_artifact") != row.get("tuple_artifact"):
    raise SystemExit(f"selection selected artifact mismatch: {selection!r}")
if selection.get("candidate_count", 0) < 1 or selection.get("eligible_count", 0) < 1:
    raise SystemExit(f"release-find selection counts missing: {selection!r}")
filters = selection.get("filters") or {}
if filters.get("device") != "native":
    raise SystemExit(f"release-find selection filters missing device: {filters!r}")
policy = "\n".join(selection.get("policy") or [])
if "prefer lower-risk compatibility labels" not in policy:
    raise SystemExit(f"release-find selection policy missing: {policy}")
PY
cp "$work/release/release-index.json" "$work/release/release-index.json.orig"
python3 - "$work/release/release-index.json" <<'PY'
import json
import sys

path = sys.argv[1]
index = json.load(open(path, "r", encoding="utf-8"))
row = index["artifacts"][0]
if row.get("tuple", {}).get("path") != row.get("tuple_path"):
    raise SystemExit("release-index tuple path drift")
if row.get("tuple", {}).get("path_components", {}).get("discriminator") != "host":
    raise SystemExit("release-index tuple components missing")
if (row.get("compatibility") or {}).get("label") != "exact":
    raise SystemExit("release-index compatibility baseline missing")
if sorted(index.get("tuples", {})) != ["by-tuple/native/host/host/host"]:
    raise SystemExit("release-index tuple keys mismatch")
row["doom_wads"] = [
    {
        "filename": "doom.wad",
        "size": 9,
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    }
]
with open(path, "w", encoding="utf-8") as fh:
    json.dump(index, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
"$work/release/scripts/lib/release-find" --doom-wad doom.wad >"$work/release-find-doom.out"
grep -q '^recommended_artifact=by-tuple/native/host/host/host/bin/grit-native-default-full$' "$work/release-find-doom.out"
grep -q '^doom_wad=doom.wad size=9 sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef$' "$work/release-find-doom.out"
"$work/release/scripts/lib/release-find" --doom-wad-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef --json >"$work/release-find-doom-sha.json"
python3 - "$work/release-find-doom-sha.json" <<'PY'
import json
import sys

row = json.load(open(sys.argv[1], "r", encoding="utf-8"))
selection = row.get("selection") or {}
filters = selection.get("filters") or {}
if filters.get("doom_wad_sha256") != "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef":
    raise SystemExit(f"release-find Doom WAD filter missing: {filters!r}")
if (row.get("doom_wads") or [{}])[0].get("filename") != "doom.wad":
    raise SystemExit("release-find did not preserve Doom WAD metadata")
PY
mv "$work/release/release-index.json.orig" "$work/release/release-index.json"
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
"$work/release/scripts/lib/release-find" --survey-json "$work/survey-mipsel.json" --json >"$work/release-find-survey.json"
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
cat >"$work/reality-advisory.json" <<'JSON'
{
  "schema": 1,
  "checks": [
    {"name": "ptrace", "status": "fail", "ok": false, "available": false, "detail": "operation not permitted"},
    {"name": "dmesg_readable", "status": "fail", "ok": false, "available": false, "detail": "kernel message buffer not readable"},
    {"name": "spawn_sh", "status": "fail", "ok": false, "available": false, "detail": "missing shell"},
    {"name": "pty", "status": "fail", "ok": false, "available": false, "detail": "no devpts"}
  ]
}
JSON
"$work/release/scripts/lib/release-find" --arch native --libc host --kernel host --reality-json "$work/reality-advisory.json" --json >"$work/release-find-reality-advisory.json"
python3 - "$work/release-find-reality-advisory.json" <<'PY'
import json
import sys

row = json.load(open(sys.argv[1], "r", encoding="utf-8"))
compat = row.get("compatibility") or {}
if compat.get("label") != "likely":
    raise SystemExit(f"expected advisory reality failures to score likely, got {compat!r}")
reasons = "\n".join(compat.get("reasons") or [])
if "ptrace unavailable: debugger payloads may be limited" not in reasons:
    raise SystemExit(f"ptrace advisory reason missing: {reasons}")
if "dmesg unreadable: crash evidence may be limited" not in reasons:
    raise SystemExit(f"dmesg advisory reason missing: {reasons}")
if "shell spawn unavailable: shell-oriented payloads may be limited" not in reasons:
    raise SystemExit(f"spawn_sh advisory reason missing: {reasons}")
if "PTY unavailable: interactive tools may be degraded" not in reasons:
    raise SystemExit(f"pty advisory reason missing: {reasons}")
facts = compat.get("facts") or {}
if (facts.get("ptrace_unavailable") is not True or
        facts.get("dmesg_unreadable") is not True or
        facts.get("spawn_sh_unavailable") is not True or
        facts.get("pty_unavailable") is not True):
    raise SystemExit(f"advisory reality facts missing: {facts!r}")
PY
cat >"$work/reality-procfs-read.json" <<'JSON'
{
  "schema": 1,
  "checks": [
    {"name": "read_proc", "status": "fail", "ok": false, "available": false, "detail": "/proc present but key procfs files are unreadable"}
  ]
}
JSON
"$work/release/scripts/lib/release-find" --arch native --libc host --kernel host --reality-json "$work/reality-procfs-read.json" --json >"$work/release-find-reality-procfs.json"
python3 - "$work/release-find-reality-procfs.json" <<'PY'
import json
import sys

row = json.load(open(sys.argv[1], "r", encoding="utf-8"))
compat = row.get("compatibility") or {}
if compat.get("label") != "heuristic":
    raise SystemExit(f"expected failed read_proc to score heuristic, got {compat!r}")
reasons = "\n".join(compat.get("reasons") or [])
if "procfs partial/broken: static survey evidence may be incomplete" not in reasons:
    raise SystemExit(f"read_proc procfs reason missing: {reasons}")
facts = compat.get("facts") or {}
if facts.get("procfs_partial") is not True:
    raise SystemExit(f"read_proc procfs fact missing: {facts!r}")
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
"$work/release/scripts/lib/release-find" --arch native --libc host --kernel host --reality-json "$work/reality-unsafe.json" >"$work/release-find-reality.out"
grep -q '^compatibility=unsafe$' "$work/release-find-reality.out"
grep -q '^compatibility_reason=runtime root execution failed in reality-test$' "$work/release-find-reality.out"
grep -q '^candidate_count=1$' "$work/release-find-reality.out"
grep -q '^eligible_count=1$' "$work/release-find-reality.out"
grep -q '^selection_policy=.*prefer lower-risk compatibility labels' "$work/release-find-reality.out"
if "$work/release/scripts/lib/release-find" --arch native --libc host --kernel host --reality-json "$work/reality-unsafe.json" --max-compatibility likely >"$work/release-find-threshold.out" 2>"$work/release-find-threshold.err"; then
    printf '%s\n' "release-bundles: max compatibility threshold accepted unsafe artifact" >&2
    exit 1
fi
grep -q 'no matching artifact within compatibility threshold' "$work/release-find-threshold.err"
"$work/release/scripts/lib/release-self-test" >/dev/null
scripts/lib/release-self-test --release-dir "$work/release" >/dev/null
"$work/release/scripts/lib/release-self-test" --json >"$work/release-self-test.json"
python3 -m json.tool "$work/release-self-test.json" >/dev/null
python3 - "$work/release-self-test.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if doc.get("status") != "pass" or doc.get("release_name") != "smoke":
    raise SystemExit(f"unexpected release self-test status/name: {doc!r}")
if doc.get("checksum_original_verified") is not True:
    raise SystemExit("release self-test did not report checksum verification")
if doc.get("project_license") != "GPL-2.0-or-later":
    raise SystemExit(f"release self-test project license missing: {doc!r}")
if doc.get("combined_gplv2_compatible") is not True:
    raise SystemExit(f"release self-test GPL compatibility missing: {doc!r}")
if doc.get("corresponding_source_required") is not True:
    raise SystemExit(f"release self-test corresponding source requirement missing: {doc!r}")
if doc.get("corresponding_source_status") != "required_for_distribution":
    raise SystemExit(f"release self-test corresponding source status missing: {doc!r}")
if doc.get("corresponding_source_requires_package_license_audit") is not True:
    raise SystemExit(f"release self-test package license audit requirement missing: {doc!r}")
if doc.get("corresponding_source_release_input_count", 0) < 7:
    raise SystemExit(f"release self-test corresponding source release inputs missing: {doc!r}")
if doc.get("corresponding_source_reconstruction_input_count", 0) < 4:
    raise SystemExit(f"release self-test corresponding source reconstruction inputs missing: {doc!r}")
if doc.get("license_evidence_source_count", 0) < 4:
    raise SystemExit(f"release self-test license evidence sources missing: {doc!r}")
if not doc.get("license_evidence_verified_at"):
    raise SystemExit(f"release self-test license evidence verification date missing: {doc!r}")
if "BusyBox" not in (doc.get("license_evidence_source_names") or []):
    raise SystemExit(f"release self-test BusyBox license evidence missing: {doc!r}")
if (doc.get("license_evidence_source_licenses") or {}).get("BusyBox") != "GPL-2.0":
    raise SystemExit(f"release self-test BusyBox license evidence mismatch: {doc!r}")
if (doc.get("license_evidence_source_urls") or {}).get("Buildroot") != "https://buildroot.org/downloads/manual/manual.html":
    raise SystemExit(f"release self-test Buildroot license evidence URL missing: {doc!r}")
if doc.get("license_notice_count") != 11:
    raise SystemExit(f"release self-test license notice count missing: {doc!r}")
notice_files = doc.get("license_notice_files") or []
for rel in ("LICENSES/busybox.txt", "LICENSES/buildroot.txt", "LICENSES/doom-ascii.txt", "LICENSES/miniz.txt"):
    if rel not in notice_files:
        raise SystemExit(f"release self-test license notice files missing {rel}: {doc!r}")
for rel in ("docs/licensing.md", "sources.lock.json", "manifests/sources.lock.json"):
    if rel not in notice_files:
        raise SystemExit(f"release self-test license notice files missing {rel}: {doc!r}")
if doc.get("checked_artifact_count") != 1 or doc.get("native_manifest_checked_count") != 1:
    raise SystemExit(f"release self-test artifact checks missing: {doc!r}")
if doc.get("release_failure_count") != 0:
    raise SystemExit(f"release self-test accepted recorded failures: {doc!r}")
if doc.get("matrix_target_count") != 1 or doc.get("matrix_payload_preset_count") != 1 or doc.get("matrix_format_count") != 1:
    raise SystemExit(f"release self-test matrix counts missing: {doc!r}")
if doc.get("matrix_targets") != ["native"] or doc.get("matrix_payload_presets") != ["default"] or doc.get("matrix_formats") != ["tgz"]:
    raise SystemExit(f"release self-test matrix details missing: {doc!r}")
if doc.get("matrix_expected_job_count") != 1 or doc.get("matrix_present_job_count") != 1 or doc.get("matrix_missing_job_count") != 0 or doc.get("matrix_missing_jobs") != []:
    raise SystemExit(f"release self-test matrix completeness missing: {doc!r}")
if doc.get("tuple_manifest_count") != 1 or doc.get("device_alias_count") != 1:
    raise SystemExit(f"release self-test layout diagnostics missing: {doc!r}")
if doc.get("artifact_config_roundtrip_count") != 1:
    raise SystemExit(f"release self-test artifact-config roundtrip missing: {doc!r}")
if (doc.get("command_queue_enabled_count") != 0 or
        doc.get("command_queue_token_required_count") != 1 or
        doc.get("command_queue_token_configured_count") != 0 or
        doc.get("command_queue_execution_supported_count") != 0 or
        doc.get("command_queue_operator_supplied_command_execution_count") != 0):
    raise SystemExit(f"release self-test command queue safety counts unsafe: {doc!r}")
if doc.get("command_queue_mode_count", 0) < 5:
    raise SystemExit(f"release self-test command queue mode diagnostics missing: {doc!r}")
if doc.get("compatibility_counts", {}).get("exact") != 1:
    raise SystemExit(f"release self-test compatibility counts missing: {doc!r}")
if doc.get("payload_preset_counts", {}).get("default") != 1:
    raise SystemExit(f"release self-test payload preset counts missing: {doc!r}")
records = doc.get("diagnostic_records") or []
by_name = doc.get("diagnostic_records_by_name") or {}
by_category = doc.get("diagnostic_records_by_category") or {}
by_status = doc.get("diagnostic_records_by_status") or {}
api = (doc.get("api_collections") or {}).get("diagnostic_records") or {}
api_meta = doc.get("api") or {}
api_resources = doc.get("api_resources") or []
api_resources_by_name = doc.get("api_resources_by_name") or {}
api_resources_by_records_key = doc.get("api_resources_by_records_key") or {}
api_resources_by_summary_key = doc.get("api_resources_by_summary_key") or {}
api_resources_by_primary_key = doc.get("api_resources_by_primary_key") or {}
if doc.get("diagnostic_record_count") != len(records) or len(records) < 10:
    raise SystemExit(f"release self-test diagnostic records missing: {doc!r}")
if by_name.get("command_queue_safety", {}).get("status") != "pass":
    raise SystemExit(f"release self-test command queue diagnostic missing: {by_name!r}")
matrix_diag = by_name.get("release_matrix") or {}
if (matrix_diag.get("status") != "pass" or
        matrix_diag.get("details", {}).get("target_count") != 1 or
        matrix_diag.get("details", {}).get("expected_job_count") != 1 or
        matrix_diag.get("details", {}).get("present_job_count") != 1 or
        matrix_diag.get("details", {}).get("missing_job_count") != 0):
    raise SystemExit(f"release self-test release_matrix diagnostic missing: {by_name!r}")
license_diag = by_name.get("license_inventory") or {}
if license_diag.get("status") != "pass" or license_diag.get("details", {}).get("project_license") != "GPL-2.0-or-later":
    raise SystemExit(f"release self-test license diagnostic missing: {by_name!r}")
if license_diag.get("details", {}).get("corresponding_source_required") is not True:
    raise SystemExit(f"release self-test license diagnostic corresponding source missing: {by_name!r}")
if license_diag.get("details", {}).get("corresponding_source_status") != "required_for_distribution":
    raise SystemExit(f"release self-test license diagnostic corresponding source status missing: {by_name!r}")
if license_diag.get("details", {}).get("corresponding_source_requires_package_license_audit") is not True:
    raise SystemExit(f"release self-test license diagnostic package audit missing: {by_name!r}")
if license_diag.get("details", {}).get("license_evidence_source_count", 0) < 4:
    raise SystemExit(f"release self-test license diagnostic evidence sources missing: {by_name!r}")
if (license_diag.get("details", {}).get("license_evidence_source_licenses") or {}).get("BusyBox") != "GPL-2.0":
    raise SystemExit(f"release self-test license diagnostic evidence license mismatch: {by_name!r}")
if by_name["command_queue_safety"]["details"].get("execution_supported_count") != 0:
    raise SystemExit(f"release self-test command queue execution diagnostic unsafe: {by_name!r}")
if by_name.get("compatibility_labels", {}).get("details", {}).get("counts", {}).get("exact") != 1:
    raise SystemExit(f"release self-test compatibility diagnostic missing: {by_name!r}")
if not by_category.get("command_queue") or not by_category.get("licensing") or not by_status.get("pass"):
    raise SystemExit(f"release self-test diagnostic indexes missing: {doc!r}")
if (api.get("count") != len(records) or
        api.get("summary_key") != "diagnostic_record_count" or
        api.get("count_summary_key") != "diagnostic_record_count" or
        api.get("primary_key") != "name" or
        "diagnostic_records_by_category" not in (api.get("indexes") or [])):
    raise SystemExit(f"release self-test diagnostic api collection missing: {api!r}")
if (api_meta.get("schema") != 1 or
        api_meta.get("resource_count") != len(api_resources) or
        api_meta.get("resources_key") != "api_resources" or
        api_meta.get("collections_key") != "api_collections"):
    raise SystemExit(f"release self-test api metadata missing: {doc!r}")
if (api_resources_by_name.get("diagnostic_records", {}).get("records_key") != "diagnostic_records" or
        api_resources_by_records_key.get("diagnostic_records", [{}])[0].get("collection_key") != "api_collections.diagnostic_records" or
        api_resources_by_summary_key.get("diagnostic_record_count", [{}])[0].get("primary_key") != "name" or
        api_resources_by_primary_key.get("name", [{}])[0].get("summary_key") != "diagnostic_record_count"):
    raise SystemExit(f"release self-test api resource indexes missing: {doc!r}")
PY
scripts/lib/release-self-test --release-dir "$work/release" --json >"$work/release-self-test-wrapper.json"
python3 - "$work/release-self-test-wrapper.json" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if doc.get("status") != "pass" or doc.get("checked_artifact_count") != 1:
    raise SystemExit("release-self-test wrapper did not forward --json diagnostics")
PY

cp -a "$work/release" "$work/matrix-gap-release"
python3 - "$work/matrix-gap-release/release.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, "r", encoding="utf-8"))
data["matrix"]["payload_presets"].append("survey-core")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
(
    cd "$work/matrix-gap-release"
    tmp=SHA256SUMS.original.tmp
    : >"$tmp"
    find . -type f \
        ! -name 'SHA256SUMS' \
        ! -name 'SHA256SUMS.original' \
        ! -name 'SHA256SUMS.original.tmp' \
        ! -name 'SHA256SUMS.configured' \
        ! -name 'SHA256SUMS.configured.tmp' \
        ! -name '*.tar.gz' |
    LC_ALL=C sort |
    while IFS= read -r item; do
        item=${item#./}
        sha256sum "$item"
    done >"$tmp"
    mv "$tmp" SHA256SUMS.original
    cp SHA256SUMS.original SHA256SUMS
)
if "$work/matrix-gap-release/scripts/lib/release-self-test" >"$work/matrix-gap-self-test.out" 2>"$work/matrix-gap-self-test.err"; then
    printf '%s\n' "release-bundles: release-self-test accepted an incomplete matrix" >&2
    exit 1
fi
grep -q 'release matrix missing artifact builds: native/survey-core/tgz' "$work/matrix-gap-self-test.err"

failure_target=armv7-linux-3.x-musl
hide_failure_artifact
scripts/make-release \
    --name failure-smoke \
    --targets "native,$failure_target" \
    --payload-presets default \
    --skip-build \
    --out-dir "$work/failure-release" >"$work/failure-release.out"
restore_hidden_failure_artifact
test -x "$work/failure-release/bin/grit-native-default-full"
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
if "$work/failure-release/scripts/lib/release-self-test" >"$work/failure-self-test.out" 2>"$work/failure-self-test.err"; then
    printf '%s\n' "release-bundles: release-self-test accepted a release with failed artifacts" >&2
    exit 1
fi
grep -q 'release contains failed artifact builds' "$work/failure-self-test.err"

scripts/make-release \
    --name copy-layout \
    --targets native \
    --payload-presets default \
    --skip-build \
    --copy-layout \
    --out-dir "$work/copy-release" >"$work/copy-release.out"
test -x "$work/copy-release/by-tuple/native/host/host/host/bin/grit-native-default-full"
test ! -L "$work/copy-release/by-tuple/native/host/host/host/bin/grit-native-default-full"
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

if [ -f dist/grit-mipsel-linux-4.x-musl-full ]; then
    scripts/make-release \
        --name glinet-layout \
        --targets glinet-mt7621-openwrt-musl \
        --payload-presets default \
        --skip-build \
        --out-dir "$work/glinet-release" >"$work/glinet-release.out"
    test -d "$work/glinet-release/by-tuple/mipsel/musl/4.x/mips32r2-24kc"
    test -L "$work/glinet-release/devices/glinet-mt1300/artifacts"
    test -f "$work/glinet-release/by-tuple/mipsel/musl/4.x/mips32r2-24kc/manifests/grit-glinet-mt7621-openwrt-musl-default-full.payload-manifest.json"
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

hide_failure_artifact
if scripts/make-release \
    --name strict-failure \
    --targets "native,$failure_target" \
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
restore_hidden_failure_artifact

hide_failure_artifact
scripts/make-release \
    --name fail-fast \
    --targets "$failure_target,native" \
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
restore_hidden_failure_artifact

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
test -f "$work/source-lock-release/manifests/sources.lock.json"
cmp "$work/source-lock-release/sources.lock.json" "$work/source-lock-release/manifests/sources.lock.json"
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
    --name source-lock-default \
    --targets native \
    --payload-presets default \
    --skip-build \
    --out-dir "$work/source-lock-default-release" >"$work/source-lock-default-release.out"
test -f "$work/source-lock-default-release/sources.lock.json"
test -f "$work/source-lock-default-release/manifests/sources.lock.json"
cmp "$work/source-lock-default-release/sources.lock.json" "$work/source-lock-default-release/manifests/sources.lock.json"
python3 - "$work/source-lock-default-release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
if data.get("include_sources_manifest") is not True:
    raise SystemExit("default release did not include source lock")
PY

scripts/make-release \
    --name reverse-smoke \
    --matrix "$work/reverse-matrix.json" \
    --skip-build \
    --out-dir "$work/reverse-release" >"$work/reverse-release.out"
test -x "$work/reverse-release/bin/grit-native-survey-core-full"
test -x "$work/reverse-release/bin/grit-native-ssh-operator-full"
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
test -x "$work/config-release/bin/grit-native-default-base-a-full"
test -x "$work/config-release/bin/grit-native-default-base-b-full"
test -f "$work/config-release/configs/native-default-base-a.conf"
test -f "$work/config-release/configs/native-default-base-b.conf"
grep -q '^GRIT_RUNTIME_MODE="extract"$' "$work/config-release/configs/native-default-base-a.conf"
grep -q '^GRIT_RUNTIME_MODE="core-only"$' "$work/config-release/configs/native-default-base-b.conf"
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
test -x "$work/format-release/bin/grit-native-default-full"
test -x "$work/format-release/bin/grit-native-default-tar-full"
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
    "bin/grit-native-default-full",
    "bin/grit-native-default-tar-full",
}
if set(paths) != expected:
    raise SystemExit(f"format artifact names mismatch: {paths}")
PY

(
    cd "$work/release"
    scripts/verify-checksums --original >/dev/null
)

"$work/release/scripts/configure-artifact" \
    "$work/release/bin/grit-native-default-full" \
    --operator-host 192.0.2.55 \
    --transport builtin \
    --noresidue-level aggressive \
    --shell-port 22203 >/dev/null

"$work/release/scripts/lib/artifact-config" show "$work/release/bin/grit-native-default-full" >"$work/show.out"
grep -q '^trailer_present=yes$' "$work/show.out"
grep -q '^GRIT_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/show.out"
grep -q '^GRIT_NORESIDUE_LEVEL=aggressive$' "$work/show.out"
test -x "$work/release/bin/grit-native-default-full"
"$work/release/scripts/configure-artifact" \
    "$work/release/bin/grit-native-default-full" \
    --show >"$work/wrapper-show.out"
grep -q '^trailer_present=yes$' "$work/wrapper-show.out"
"$work/release/scripts/configure-artifact" \
    "$work/release/bin/grit-native-default-full" \
    --export "$work/export.env"
grep -q '^GRIT_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/export.env"
test -f "$work/release/SHA256SUMS.configured"
(
    cd "$work/release"
    scripts/verify-checksums --configured >/dev/null
)

"$work/release/scripts/configure-all" --clear >/dev/null
"$work/release/scripts/lib/artifact-config" show "$work/release/bin/grit-native-default-full" >"$work/clear.out"
grep -q '^trailer_present=no$' "$work/clear.out"

"$work/release/scripts/configure-artifact" \
    "$work/release/bin/grit-native-default-full" \
    --import "$work/export.env" \
    --obfuscation xor >"$work/import-xor.out"
grep -q 'not encryption' "$work/import-xor.out"
"$work/release/scripts/lib/artifact-config" show "$work/release/bin/grit-native-default-full" >"$work/xor-show.out"
grep -q '^trailer_present=yes$' "$work/xor-show.out"
grep -q '^encoding=xor$' "$work/xor-show.out"
grep -q '^GRIT_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/xor-show.out"
test -x "$work/release/bin/grit-native-default-full"
(
    cd "$work/release"
    scripts/verify-checksums --configured >/dev/null
)

printf '%s\n' "release-bundles ok"
