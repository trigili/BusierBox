#!/bin/sh
set -eu

tmp_root=${TMPDIR:-local/tmp}
mkdir -p "$tmp_root"
work=$(mktemp -d "$tmp_root/release-bundles.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM

scripts/make-release --name smoke --targets native --payload-presets default --dry-run >"$work/dry-run.out"
grep -q 'would build target=native payload=default format=tgz' "$work/dry-run.out"
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
test -x "$work/release/scripts/artifact-config"
test -x "$work/release/scripts/configure-artifact"
test -x "$work/release/scripts/configure-all"
test -x "$work/release/scripts/verify-checksums"
test -f "$work/release/SHA256SUMS.original"
test -f "$work/release/release.json"
test -f "$work/release.tar.gz"

python3 -m json.tool "$work/release/release.json" >/dev/null
grep -q '"release_name": "smoke"' "$work/release/release.json"
grep -q '"build_status": "copied"' "$work/release/release.json"
python3 - "$work/release/release.json" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
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

(
    cd "$work/release"
    scripts/verify-checksums --original >/dev/null
)

"$work/release/scripts/configure-artifact" \
    "$work/release/bin/busierbox-native-default-full" \
    --operator-host 192.0.2.55 \
    --transport builtin \
    --shell-port 22203 >/dev/null

"$work/release/scripts/artifact-config" show "$work/release/bin/busierbox-native-default-full" >"$work/show.out"
grep -q '^trailer_present=yes$' "$work/show.out"
grep -q '^BB_OPERATOR_SERVER_HOST=192.0.2.55$' "$work/show.out"
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
