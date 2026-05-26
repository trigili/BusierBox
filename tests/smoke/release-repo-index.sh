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
      "trailer_support": true,
      "compatibility": {"schema": 1, "label": "exact", "reasons": ["fixture"]}
    }
  ]
}
JSON
}

same_sha=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
make_release "$tmp/releases/one" one survey-core tcpdump "$same_sha" glinet-mt1300
make_release "$tmp/releases/two" two ssh-operator strace "$same_sha" lab-router

scripts/index-release-repo "$tmp/releases" >"$tmp/index.json"
python3 -m json.tool "$tmp/index.json" >/dev/null
python3 - "$tmp/index.json" <<'PY'
import json
import sys

index = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert index["release_count"] == 2
assert index["artifact_count"] == 2
assert index["deduplicated_artifact_count"] == 1
assert "tcpdump" in index["tools_present"]
assert "ssh-operator" in index["payload_presets"]
assert "trailer" in index["features"]
sha, rec = next(iter(index["dedupe"].items()))
assert rec["count"] == 2
PY

scripts/index-release-repo "$tmp/releases" --write "$tmp/repo-index.json" >/dev/null
test -f "$tmp/repo-index.json"
scripts/find-artifact --index "$tmp/repo-index.json" --device glinet-mt1300 --tool tcpdump >"$tmp/find-device.out"
grep -q '^release_name=one$' "$tmp/find-device.out"
grep -q '^payload_preset=survey-core$' "$tmp/find-device.out"
grep -q '^dedupe_count=2$' "$tmp/find-device.out"
scripts/find-artifact --index "$tmp/repo-index.json" --payload-preset ssh-operator --feature reverse-ssh --json >"$tmp/find-json.out"
python3 - "$tmp/find-json.out" <<'PY'
import json
import sys

row = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert row["release_name"] == "two"
assert row["payload_preset"] == "ssh-operator"
assert "reverse-ssh" in row["features"]
PY
scripts/find-artifact --index "$tmp/repo-index.json" --device lab-router --recommendation-json >"$tmp/recommend-json.out"
python3 - "$tmp/recommend-json.out" <<'PY'
import json
import sys

doc = json.load(open(sys.argv[1], "r", encoding="utf-8"))
assert doc["schema"] == 1
assert doc["command"] == "find-artifact"
assert doc["filters"]["device"] == "lab-router"
assert doc["match_count"] == 1
assert doc["selected"]["release_name"] == "two"
assert doc["index"]["deduplicated_artifact_count"] == 1
assert "newest release_mtime" in doc["selection_policy"]
PY
grep -q -- '--recommendation-json' docs/release-bundles.md
grep -q 'policy used to prefer lower-risk compatibility labels' docs/release-bundles.md

printf '%s\n' "release-repo-index ok"
