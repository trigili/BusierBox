#!/bin/sh
set -eu

tmp=$(mktemp -d "${TMPDIR:-/tmp}/busierbox-release-repo.XXXXXX")
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

make_release() {
    dir=$1
    name=$2
    preset=$3
    tool=$4
    sha=$5
    device=$6
    compatibility_label=${7:-exact}
    doom_wads_json=${8:-[]}
    mkdir -p "$dir/bin"
    printf '%s\n' "$name artifact" >"$dir/bin/busierbox-$name-full"
    cat >"$dir/release.json" <<JSON
{
  "schema": 1,
  "release_name": "$name",
  "git_commit": "test",
  "layout": {
    "devices": {
      "$device": {
        "tuple_path": "by-tuple/mipsel/musl/4.x/mips32r2-24kc",
        "artifacts": ["by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/busierbox-$name-full"]
      }
    },
    "tuples": {
      "by-tuple/mipsel/musl/4.x/mips32r2-24kc": {
        "tuple": {
          "arch": "mipsel",
          "libc": "musl",
          "kernel_floor": "4.x",
          "cpu": "mips32r2-24kc",
          "abi": "default"
        },
        "artifacts": ["by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/busierbox-$name-full"]
      }
    }
  },
  "artifacts": []
}
JSON
    cat >"$dir/release-index.json" <<JSON
{
  "schema": 1,
  "release_name": "$name",
  "git_commit": "test",
  "devices": {
    "$device": {
      "tuple_path": "by-tuple/mipsel/musl/4.x/mips32r2-24kc",
      "artifacts": ["by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/busierbox-$name-full"]
    }
  },
  "tuples": {
    "by-tuple/mipsel/musl/4.x/mips32r2-24kc": {
      "tuple": {
        "arch": "mipsel",
        "libc": "musl",
        "kernel_floor": "4.x",
        "cpu": "mips32r2-24kc",
        "abi": "default"
      },
      "artifacts": ["by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/busierbox-$name-full"]
    }
  },
  "artifacts": [
    {
      "artifact": "bin/busierbox-$name-full",
      "tuple_artifact": "by-tuple/mipsel/musl/4.x/mips32r2-24kc/bin/busierbox-$name-full",
      "tuple_path": "by-tuple/mipsel/musl/4.x/mips32r2-24kc",
      "tuple": {
        "arch": "mipsel",
        "libc": "musl",
        "kernel_floor": "4.x",
        "cpu": "mips32r2-24kc",
        "abi": "default"
      },
      "payload_preset": "$preset",
      "runtime_mode": "extract",
      "reverse_access": {"transport": "ssh"},
      "sha256": "$sha",
      "size": 123,
      "tools": ["sh", "$tool"],
      "tool_provider_status": {"$tool": {"schema": 1, "overall": "found", "search_paths": []}},
      "doom_wads": $doom_wads_json,
      "trailer_support": true,
      "compatibility": {"schema": 1, "label": "$compatibility_label", "reasons": ["fixture"]}
    }
  ]
}
JSON
    cat >"$dir/release-self-test.json" <<JSON
{
  "schema": 1,
  "status": "pass",
  "release_name": "$name",
  "checked_artifact_count": 1,
  "release_tuple_count": 1,
  "release_device_count": 1,
  "command_queue_enabled_count": 0,
  "command_queue_execution_supported_count": 0
}
JSON
}

same_sha=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
make_release "$tmp/releases/one" one survey-core tcpdump "$same_sha" glinet-mt1300 exact '[{"filename":"doom.wad","size":9,"sha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}]'
make_release "$tmp/releases/two" two ssh-operator strace "$same_sha" lab-router
make_release "$tmp/releases/three" three full-debug gdbserver fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210 lab-router unsafe

scripts/index-release-repo "$tmp/releases" >"$tmp/index.json"
python3 -m json.tool "$tmp/index.json" >/dev/null
python3 - "$tmp/index.json" <<'PY'
import json
import sys

index = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert index["release_count"] == 3
assert index["artifact_count"] == 3
assert index["release_self_test_count"] == 3
assert index["deduplicated_artifact_count"] == 2
assert index["device_count"] == 2
assert index["device_record_count"] == 3
assert index["tuple_count"] == 1
assert index["tuple_record_count"] == 3
assert "tcpdump" in index["tools_present"]
assert "ssh-operator" in index["payload_presets"]
assert "trailer" in index["features"]
sha, rec = next(iter(index["dedupe"].items()))
assert rec["count"] == 2
assert len(index["artifacts_by_sha"][sha]) == 2
assert {item["release_name"] for item in index["artifacts_by_sha"][sha]} == {"one", "two"}
assert index["release_self_tests_by_release"]["one"][0]["status"] == "pass"
assert len(index["release_self_tests_by_status"]["pass"]) == 3
assert index["artifacts_by_release"]["one"][0]["release_self_test_status"] == "pass"
assert index["artifacts_by_release"]["one"][0]["release_self_test"]["checked_artifact_count"] == 1
assert len(index["artifacts_by_release"]["one"]) == 1
tuple_rows = index["artifacts_by_tuple_path"]["by-tuple/mipsel/musl/4.x/mips32r2-24kc"]
assert len(tuple_rows) == 3
assert index["artifacts_by_tool"]["tcpdump"][0]["release_name"] == "one"
assert index["artifacts_by_tool"]["tcpdump"][0]["doom_wads"][0]["filename"] == "doom.wad"
assert index["artifacts_by_payload_preset"]["ssh-operator"][0]["release_name"] == "two"
assert index["artifacts_by_feature"]["reverse-ssh"][0]["release_name"] in {"one", "two", "three"}
assert index["artifacts_by_tool_payload_preset"]["tcpdump:survey-core"][0]["release_name"] == "one"
assert index["artifacts_by_feature_payload_preset"]["reverse-ssh:ssh-operator"][0]["release_name"] == "two"
assert len(index["artifacts_by_tuple_payload_preset"]["by-tuple/mipsel/musl/4.x/mips32r2-24kc:full-debug"]) == 1
assert index["artifacts_by_provider_tool"]["gdbserver"][0]["release_name"] == "three"
assert index["artifacts_by_provider_status"]["gdbserver:found"][0]["payload_preset"] == "full-debug"
assert index["artifacts_by_doom_wad_filename"]["doom.wad"][0]["release_name"] == "one"
assert index["artifacts_by_doom_wad_sha256"]["0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"][0]["payload_preset"] == "survey-core"
assert len(index["device_records"]) == 3
assert index["device_records_by_alias"]["lab-router"][0]["alias"] == "lab-router"
assert len(index["device_records_by_tuple_path"]["by-tuple/mipsel/musl/4.x/mips32r2-24kc"]) == 3
assert index["device_records_by_release"]["one"][0]["alias"] == "glinet-mt1300"
assert len(index["tuple_records"]) == 3
assert len(index["tuple_records_by_tuple_path"]["by-tuple/mipsel/musl/4.x/mips32r2-24kc"]) == 3
assert index["tuple_records_by_release"]["three"][0]["tuple"]["arch"] == "mipsel"
recs = index["recommendations"]
assert recs["schema"] == 1
assert "lowest compatibility risk label" in recs["selection_policy"]
assert recs["by_device"]["lab-router"]["release_name"] == "two"
assert recs["by_device"]["glinet-mt1300"]["release_name"] == "one"
assert recs["by_tuple_path"]["by-tuple/mipsel/musl/4.x/mips32r2-24kc"]["release_name"] in {"one", "two"}
assert recs["by_tool"]["gdbserver"]["release_name"] == "three"
assert recs["by_tool"]["strace"]["release_name"] == "two"
assert recs["by_payload_preset"]["ssh-operator"]["release_name"] == "two"
assert recs["by_feature"]["reverse-ssh"]["release_name"] in {"one", "two"}
assert recs["by_tool_payload_preset"]["tcpdump:survey-core"]["release_name"] == "one"
assert recs["by_feature_payload_preset"]["reverse-ssh:ssh-operator"]["release_name"] == "two"
assert recs["by_tuple_payload_preset"]["by-tuple/mipsel/musl/4.x/mips32r2-24kc:full-debug"]["release_name"] == "three"
assert index["recommendation_count"] == sum(
    len(recs[name]) for name in (
        "by_device",
        "by_tuple_path",
        "by_tool",
        "by_payload_preset",
        "by_feature",
        "by_tool_payload_preset",
        "by_feature_payload_preset",
        "by_tuple_payload_preset",
    )
)
api = index["api_collections"]
assert api["artifacts"]["name"] == "artifacts"
assert api["artifacts"]["count"] == index["artifact_count"]
assert api["artifacts"]["summary_key"] == "artifact_count"
assert api["artifacts"]["count_summary_key"] == "artifact_count"
assert api["artifacts"]["primary_key"] == "artifact_path"
assert "artifacts_by_tool" in api["artifacts"]["indexes"]
assert "artifacts_by_provider_status" in api["artifacts"]["indexes"]
assert "artifacts_by_doom_wad_filename" in api["artifacts"]["indexes"]
assert api["release_self_tests"]["count"] == index["release_self_test_count"]
assert api["release_self_tests"]["summary_key"] == "release_self_test_count"
assert api["release_self_tests"]["count_summary_key"] == "release_self_test_count"
assert api["release_self_tests"]["primary_key"] == "release_name"
assert "release_self_tests_by_release" in api["release_self_tests"]["indexes"]
assert "release_self_tests_by_status" in api["release_self_tests"]["indexes"]
assert api["dedupe"]["count"] == index["deduplicated_artifact_count"]
assert api["dedupe"]["summary_key"] == "deduplicated_artifact_count"
assert api["dedupe"]["count_summary_key"] == "deduplicated_artifact_count"
assert api["dedupe"]["primary_key"] == "sha256"
assert api["devices"]["count"] == index["device_record_count"]
assert api["devices"]["summary_key"] == "device_record_count"
assert api["devices"]["count_summary_key"] == "device_record_count"
assert api["devices"]["primary_key"] == "alias"
assert "device_records_by_alias" in api["devices"]["indexes"]
assert "device_records_by_tuple_path" in api["devices"]["indexes"]
assert api["tuples"]["count"] == index["tuple_record_count"]
assert api["tuples"]["summary_key"] == "tuple_record_count"
assert api["tuples"]["count_summary_key"] == "tuple_record_count"
assert api["tuples"]["primary_key"] == "tuple_path"
assert "tuple_records_by_tuple_path" in api["tuples"]["indexes"]
assert "tuple_records_by_release" in api["tuples"]["indexes"]
assert api["recommendations"]["count"] == index["recommendation_count"]
assert api["recommendations"]["summary_key"] == "recommendation_count"
assert api["recommendations"]["count_summary_key"] == "recommendation_count"
assert api["recommendations"]["primary_key"] == "key"
assert "by_device" in api["recommendations"]["indexes"]
assert "by_tool_payload_preset" in api["recommendations"]["indexes"]
PY

scripts/index-release-repo "$tmp/releases" --write "$tmp/repo-index.json" >/dev/null
test -f "$tmp/repo-index.json"
scripts/find-artifact --index "$tmp/repo-index.json" --device glinet-mt1300 --tool tcpdump >"$tmp/find-device.out"
grep -q '^release_name=one$' "$tmp/find-device.out"
grep -q '^payload_preset=survey-core$' "$tmp/find-device.out"
grep -q '^compatibility=exact$' "$tmp/find-device.out"
grep -q '^compatibility_reason=fixture$' "$tmp/find-device.out"
grep -q '^release_self_test_status=pass$' "$tmp/find-device.out"
grep -q '^release_self_test_path=release-self-test.json$' "$tmp/find-device.out"
grep -q '^dedupe_count=2$' "$tmp/find-device.out"
grep -q '^provider_status_tcpdump=found$' "$tmp/find-device.out"
grep -q '^doom_wad=doom.wad size=9 sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef$' "$tmp/find-device.out"
scripts/find-artifact --index "$tmp/repo-index.json" --doom-wad doom.wad >"$tmp/find-doom-wad.out"
grep -q '^release_name=one$' "$tmp/find-doom-wad.out"
scripts/find-artifact --index "$tmp/repo-index.json" --doom-wad-sha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef >"$tmp/find-doom-sha.out"
grep -q '^payload_preset=survey-core$' "$tmp/find-doom-sha.out"
scripts/find-artifact --index "$tmp/repo-index.json" --tuple-path by-tuple/mipsel/musl/4.x/mips32r2-24kc --release one >"$tmp/find-tuple.out"
grep -q '^release_name=one$' "$tmp/find-tuple.out"
grep -q '^tuple_path=by-tuple/mipsel/musl/4.x/mips32r2-24kc$' "$tmp/find-tuple.out"
scripts/find-artifact --index "$tmp/repo-index.json" --payload-preset ssh-operator --feature reverse-ssh --json >"$tmp/find-json.out"
python3 - "$tmp/find-json.out" <<'PY'
import json
import sys

row = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert row["release_name"] == "two"
assert row["payload_preset"] == "ssh-operator"
assert "reverse-ssh" in row["features"]
assert row["release_self_test_status"] == "pass"
assert row["release_self_test"]["command_queue_execution_supported_count"] == 0
PY
scripts/find-artifact --index "$tmp/repo-index.json" --device lab-router --recommendation-json >"$tmp/recommend-json.out"
python3 - "$tmp/recommend-json.out" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert doc["schema"] == 1
assert doc["command"] == "find-artifact"
assert doc["filters"]["device"] == "lab-router"
assert doc["match_count"] == 2
assert doc["visible_match_count"] == 1
assert doc["selected"]["release_name"] == "two"
assert doc["api_collections"]["matches"]["summary_key"] == "visible_match_count"
assert doc["api_collections"]["matches"]["count_summary_key"] == "visible_match_count"
assert doc["api_collections"]["matches"]["primary_key"] == "artifact_path"
assert doc["api_collections"]["dedupe_alternatives"]["count_summary_key"] == "dedupe_count"
assert doc["api_collections"]["dedupe_alternatives"]["primary_key"] == "artifact_path"
assert "matches_by_payload_preset" in doc["api_collections"]["matches"]["indexes"]
assert "matches_by_provider_status" in doc["api_collections"]["matches"]["indexes"]
assert doc["matches_by_release"]["two"][0]["release_name"] == "two"
assert doc["matches_by_payload_preset"]["ssh-operator"][0]["release_name"] == "two"
assert doc["matches_by_compatibility"]["exact"][0]["release_name"] == "two"
assert doc["matches_by_provider_tool"]["strace"][0]["release_name"] == "two"
assert doc["matches_by_provider_status"]["strace:found"][0]["release_name"] == "two"
assert doc["index"]["deduplicated_artifact_count"] == 2
assert doc["index"]["release_self_test_count"] == 3
assert doc["index"]["artifacts_by_sha_count"] == 2
assert doc["index"]["artifacts_by_release_count"] == 3
assert doc["index"]["artifacts_by_tuple_path_count"] == 1
assert doc["index"]["artifacts_by_tool_count"] == 4
assert doc["index"]["artifacts_by_payload_preset_count"] == 3
assert doc["index"]["artifacts_by_feature_count"] >= 4
assert doc["index"]["artifacts_by_tool_payload_preset_count"] >= 4
assert doc["index"]["artifacts_by_feature_payload_preset_count"] >= 6
assert doc["index"]["artifacts_by_tuple_payload_preset_count"] == 3
assert doc["index"]["artifacts_by_provider_tool_count"] == 3
assert doc["index"]["artifacts_by_provider_status_count"] == 3
assert doc["index"]["artifacts_by_doom_wad_filename_count"] == 1
assert doc["index"]["artifacts_by_doom_wad_sha256_count"] == 1
assert doc["index"]["release_self_tests_by_release_count"] == 3
assert doc["index"]["release_self_tests_by_status_count"] == 1
assert doc["selected"]["release_self_test"]["status"] == "pass"
assert doc["dedupe_count"] == 2
assert {item["release_name"] for item in doc["dedupe_alternatives"]} == {"one", "two"}
assert "newest release_mtime" in doc["selection_policy"]
PY
scripts/find-artifact --index "$tmp/repo-index.json" --device lab-router --max-compatibility likely --recommendation-json >"$tmp/recommend-safe-json.out"
python3 - "$tmp/recommend-safe-json.out" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert doc["filters"]["max_compatibility"] == "likely"
assert doc["match_count"] == 1
assert doc["selected"]["release_name"] == "two"
assert doc["selected"]["compatibility"]["label"] == "exact"
PY
scripts/find-artifact --index "$tmp/repo-index.json" --tuple-path by-tuple/mipsel/musl/4.x/mips32r2-24kc --all --recommendation-json >"$tmp/recommend-tuple-json.out"
python3 - "$tmp/recommend-tuple-json.out" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert doc["filters"]["tuple_path"] == "by-tuple/mipsel/musl/4.x/mips32r2-24kc"
assert doc["match_count"] == 3
assert doc["visible_match_count"] == 3
assert doc["selected"]["tuple_path"] == "by-tuple/mipsel/musl/4.x/mips32r2-24kc"
assert len(doc["matches_by_tuple_path"]["by-tuple/mipsel/musl/4.x/mips32r2-24kc"]) == 3
assert doc["matches_by_tool"]["gdbserver"][0]["release_name"] == "three"
assert doc["matches_by_provider_status"]["gdbserver:found"][0]["release_name"] == "three"
assert doc["matches_by_doom_wad_filename"]["doom.wad"][0]["release_name"] == "one"
assert doc["matches_by_doom_wad_sha256"]["0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"][0]["payload_preset"] == "survey-core"
assert doc["matches_by_feature"]["reverse-ssh"]
PY
grep -q -- '--recommendation-json' docs/release-bundles.md
grep -q -- '--tuple-path by-tuple/' docs/release-bundles.md
grep -q 'policy used to prefer lower-risk compatibility labels' docs/release-bundles.md
grep -q 'recommendations' docs/release-bundles.md

printf '%s\n' "release-repo-index ok"
