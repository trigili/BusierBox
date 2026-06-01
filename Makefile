PREFIX ?= /usr/local
CONFIG ?= configs/native-linux.example
OUT ?= dist/grit.core
PAYLOAD_FORMAT ?= tgz
CC ?= cc
CFLAGS ?= -Os -Wall -Wextra -std=c99
CPPFLAGS ?=
LDFLAGS ?=

SRC := src/grit.c src/payload_runtime.c src/applet_extract.c src/applet_list.c src/applet_manifest.c src/applet_doctor.c src/applet_reality_test.c src/applet_config_info.c src/applet_clean.c src/applet_plan.c src/applet_recovery.c src/applet_survey.c src/applet_envfix.c src/applet_fetch.c src/applet_rshell.c src/applet_upload.c src/applet_command_queue.c src/command_queue_policy.c src/ledger.c src/runtime_paths.c src/runtime_probe.c src/json_helpers.c src/payload_extract.c src/payload_dispatch.c src/trailer_config.c src/runtime_config.c src/sha256.c

.PHONY: all build buildroot busybox payload package package-full package-all package-all-presets package-native release release-full verify-artifact check-buildroot-tool-mappings check-licensing target-summary clean menuconfig fetch-sources verify-sources offline-pack offline-unpack detect-host smoke smoke-test smoke-grit-server smoke-grit-server-preflight smoke-grit-server-line-console test-qemu-user test-qemu-system test-qemu-flaky-network test-glinet test-all

all: build

build: busybox
	@CONFIG="$(CONFIG)" CC="$(CC)" CFLAGS="$(CFLAGS)" CPPFLAGS="$(CPPFLAGS)" LDFLAGS="$(LDFLAGS)" OUT="$(OUT)" scripts/lib/build-native

busybox:
	@scripts/lib/build-busybox

buildroot: fetch-sources
	@scripts/lib/buildroot-build-payload --prepare-only
	@printf '%s\n' "Buildroot source is available via dl/ and extracted on demand by scripts/lib/buildroot-build-payload"

payload:
	@if [ "$(if $(TARGET),$(TARGET),native)" = "native" ]; then $(MAKE) busybox; fi
	@TARGET="$(if $(TARGET),$(TARGET),native)" PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" scripts/lib/build-payload

package:
	@TARGET="$(TARGET)" PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" STRICT="$(STRICT)" VERIFY="$(VERIFY)" scripts/lib/package-selected

package-full:
	@GRIT_BUILD_FULL=yes GRIT_BUILD_STAGER=no GRIT_BUILD_INTERNAL_CORE=no TARGET="$(TARGET)" PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" STRICT="$(STRICT)" VERIFY="$(VERIFY)" scripts/lib/package-selected

package-all: package

package-all-presets:
	@scripts/lib/resolve-target --list | while IFS='	' read -r preset status desc; do \
	  if [ "$$status" = supported ]; then \
	    printf '%s\n' "package preset $$preset"; \
	    PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" scripts/lib/package-target "$$preset"; \
	  else \
	    printf '%s\n' "skip preset $$preset ($$status): $$desc"; \
	  fi; \
	done

package-native:
	@PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" scripts/lib/package-target native

release:
	@PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" GRIT_RELEASE_NAME="$(GRIT_RELEASE_NAME)" scripts/lib/release-current "$(if $(TARGET),$(TARGET),--config)"

# Full release: all supported targets × survey-core / default / ssh-operator.
# Output: dist/releases/full-VERSION-COMMIT/
# Usage:  make release-full            (build everything)
#         make release-full GRIT_RELEASE_NAME=my-label
#         make release-full DRY_RUN=1  (preview jobs without building)
GRIT_RELEASE_NAME ?= full-$(shell cat VERSION 2>/dev/null | tr -d '[:space:]')-$(shell git rev-parse --short HEAD 2>/dev/null || printf dev)
release-full:
	@scripts/make-release \
	  --name "$(GRIT_RELEASE_NAME)" \
	  --matrix tests/matrix/release-full.json \
	  $(if $(DRY_RUN),--dry-run,) \
	  $(if $(FAIL_FAST),--fail-fast,) \
	  $(if $(OUT_DIR),--out-dir "$(OUT_DIR)",)

verify-artifact:
	@if [ -n "$(TARGET)" ]; then artifact="dist/grit-$(TARGET)-full"; else artifact="dist/grit-native-full"; fi; \
	  scripts/lib/verify-artifact "$$artifact"

check-buildroot-tool-mappings:
	@scripts/lib/check-buildroot-tool-mappings

check-licensing:
	@scripts/lib/check-licensing

target-summary:
	@scripts/lib/resolve-target --config

menuconfig:
	@scripts/menuconfig ${CFG:+--config "$(CFG)"}

fetch-sources:
	@scripts/lib/fetch-sources

verify-sources:
	@scripts/lib/verify-sources

offline-pack:
	@scripts/lib/offline-pack

offline-unpack:
	@printf '%s\n' "Usage: scripts/lib/offline-unpack dist/grit-sdk-YYYYMMDD.tar.gz"

detect-host:
	@scripts/lib/detect-host

smoke: smoke-test

smoke-grit-server:
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/grit-server.py $(if $(GRIT_SERVER_SMOKE_SECTION),--section "$(GRIT_SERVER_SMOKE_SECTION)",); else printf '%s\n' "skip: python3 server smoke unavailable"; fi

smoke-grit-server-preflight:
	@$(MAKE) smoke-grit-server GRIT_SERVER_SMOKE_SECTION=preflight

smoke-grit-server-line-console:
	@$(MAKE) smoke-grit-server GRIT_SERVER_SMOKE_SECTION=line-console

smoke-test:
	@GRIT_CONFIG=presets/payload/default.conf GRIT_BUSYBOX_GROUPS="shell fileops disk process network text system" $(MAKE) package-native
	@scripts/lib/inspect-artifact dist/grit-native-full >/dev/null
	@scripts/lib/verify-artifact dist/grit-native-full
	@tests/smoke/artifact-tiers.sh
	@tests/smoke/native-help.sh dist/grit-native-full
	@tests/smoke/target-resolution.sh
	@tests/smoke/tuple-consistency.sh
	@tests/smoke/busybox-selection.sh
	@tests/smoke/payload-reality.sh
	@tests/smoke/menuconfig-autoexec.sh
	@tests/smoke/menuconfig-validation.sh
	@tests/smoke/validation-matrix.sh
	@tests/smoke/rehosted-router-presets.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/config-from-survey.sh; else printf '%s\n' "skip: python3 config-from-survey smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/preset-from-survey.sh; else printf '%s\n' "skip: python3 preset-from-survey smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/survey-shell.sh dist/grit-native-full; else printf '%s\n' "skip: python3 shell survey smoke unavailable"; fi
	@tests/smoke/payload-presets.sh
	@tests/smoke/wolfssl-detection.sh
	@tests/smoke/wolfssl-cross-preflight.sh
	@tests/smoke/build-native-wolfssl.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/artifact-config.sh dist/grit-native-full; else printf '%s\n' "skip: python3 artifact-config smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/heavy-tool-triage.sh; else printf '%s\n' "skip: python3 heavy-tool-triage smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/gdbserver-workflow.sh; else printf '%s\n' "skip: python3 gdbserver workflow smoke unavailable"; fi
	@tests/smoke/rshell-menu-structure.sh
	@tests/smoke/rshell-transport-names.sh
	@tests/smoke/rshell-external-writes.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/rshell-status-json.sh dist/grit-native-full; else printf '%s\n' "skip: python3 rshell status json smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/plan-json.sh dist/grit-native-full; else printf '%s\n' "skip: python3 plan json smoke unavailable"; fi
	@tests/smoke/stale-ux-text.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/integration-glinet-harness.sh; else printf '%s\n' "skip: python3 integration harness smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/integration-report.sh; else printf '%s\n' "skip: python3 integration report smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/build-matrix.sh; else printf '%s\n' "skip: python3 build matrix smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/qemu-matrix.sh; else printf '%s\n' "skip: python3 qemu matrix smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/qemu-flaky-network-lab.sh; else printf '%s\n' "skip: python3 qemu flaky network lab smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/release-bundles.sh; else printf '%s\n' "skip: python3 release bundle smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/release-repo-index.sh; else printf '%s\n' "skip: python3 release repo index smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/offline-tools.sh; else printf '%s\n' "skip: python3 offline tools smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/licensing.sh; else printf '%s\n' "skip: python3 licensing smoke unavailable"; fi
	@tests/smoke/dotfiles-by-app.sh
	@tests/smoke/zsh-dotfiles.sh
	@tests/smoke/runtime-modes.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/clean-json.sh dist/grit-native-full; else printf '%s\n' "skip: python3 clean json smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/recovery.sh dist/grit-native-full; else printf '%s\n' "skip: python3 recovery smoke unavailable"; fi
	@tests/smoke/rshell-lifecycle.sh
	@$(MAKE) smoke-grit-server
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/flaky-network-harness.sh; else printf '%s\n' "skip: python3 flaky network harness smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then python3 tests/smoke/operator-upload.py dist/grit-native-full; else printf '%s\n' "skip: python3 operator upload smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/command-queue.sh dist/grit-native-full; else printf '%s\n' "skip: python3 command queue smoke unavailable"; fi
	@tests/smoke/zero-arg-autorun.sh dist/grit-native-full
	@./dist/grit-native-full list >/dev/null
	@if command -v python3 >/dev/null 2>&1; then ./dist/grit-native-full survey --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then ./dist/grit-native-full survey --json --shell-probe | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 shell survey json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then ./dist/grit-native-full manifest --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 manifest json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/manifest-metadata.sh dist/grit-native-full; else printf '%s\n' "skip: python3 manifest metadata smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/open-memstream-fallback.sh; else printf '%s\n' "skip: python3 open_memstream fallback smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/support-token.sh dist/grit-native-full; else printf '%s\n' "skip: python3 support token smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/doctor-json.sh dist/grit-native-full; else printf '%s\n' "skip: python3 doctor json smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/reality-test.sh dist/grit-native-full; else printf '%s\n' "skip: python3 reality-test smoke unavailable"; fi
	@tests/smoke/core-extraction.sh dist/grit-native-full
	@if command -v python3 >/dev/null 2>&1; then ./dist/grit-native-full cleanup-ledger --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 cleanup ledger json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then ./dist/grit-native-full rshell status --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 rshell status json validation unavailable"; fi
	@./dist/grit-native-full survey >/dev/null
	@./dist/grit-native-full envfix >/dev/null
	@./dist/grit-native-full extract >/dev/null
	@./dist/grit-native-full extract >/dev/null
	@./dist/grit-native-full sh -c 'echo ok' >/dev/null
	@./dist/grit-native-full cp --help >/dev/null 2>&1
	@./dist/grit-native-full dd --help >/dev/null 2>&1
	@./dist/grit-native-full nc --help >/dev/null 2>&1
	@./dist/grit-native-full config-info >/dev/null
	@if command -v python3 >/dev/null 2>&1; then tmp=$$(mktemp -d); ./dist/grit-native-full survey --json > $$tmp/survey.json; python3 tests/smoke/validate-survey-json.py $$tmp/survey.json >/dev/null; scripts/lib/config-from-survey $$tmp/survey.json >/dev/null; rm -rf $$tmp; else printf '%s\n' "skip: python3 survey config validation unavailable"; fi
	@printf '%s\n' "smoke: testing out-of-cwd embedded extraction (catches exe-wipe bugs)..."
	@_grit_tmp=$$(mktemp -d) && \
	  cp dist/grit-native-full "$$_grit_tmp/grit" && \
	  chmod +x "$$_grit_tmp/grit" && \
	  cd "$$_grit_tmp" && \
	  ./grit extract >/dev/null && \
	  ./grit sh -c 'echo dispatch-ok' >/dev/null && \
	  ./grit cp --help >/dev/null 2>&1 && \
	  ./grit touch --help >/dev/null 2>&1 && \
	  ./grit ls --help >/dev/null 2>&1 && \
	  ./grit extract >/dev/null && \
	  printf '%s\n' "smoke: out-of-cwd ok" && \
	  cd - >/dev/null && rm -rf "$$_grit_tmp"
	@printf '%s\n' "smoke-test ok"

test-qemu-user: package-native
	@tests/qemu-user/run-qemu-user-matrix

test-qemu-system:
	@tests/qemu-system/run-qemu-system-matrix

test-qemu-flaky-network:
	@tests/qemu-system/run-flaky-network-lab --run

test-glinet:
	@tests/integration/glinet/run

test-all: smoke-test test-qemu-user test-qemu-system test-qemu-flaky-network

clean:
	@rm -f dist/grit dist/grit.sha256 dist/grit-*
	@rm -f dist/*.core dist/*.tmp dist/payload*.tar dist/payload*.tar.sha256 dist/payload*.tar.gz dist/payload*.tar.gz.sha256
	@rm -rf dist/internal
	@rm -f src/grit_busybox_applets.h src/grit_heavy_tools.h
	@rm -rf .grit
