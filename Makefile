PREFIX ?= /usr/local
CONFIG ?= configs/native-linux.example
OUT ?= dist/grit.core
PAYLOAD_FORMAT ?= tgz
CC ?= cc
CFLAGS ?= -Os -Wall -Wextra -std=c99
CPPFLAGS ?=
LDFLAGS ?=

SRC := src/grit.c src/payload_runtime.c src/applet_extract.c src/applet_list.c src/applet_manifest.c src/applet_doctor.c src/applet_reality_test.c src/applet_config_info.c src/applet_clean.c src/applet_plan.c src/applet_recovery.c src/applet_survey.c src/applet_envfix.c src/applet_fetch.c src/applet_rshell.c src/applet_upload.c src/applet_command_queue.c src/command_queue_policy.c src/ledger.c src/runtime_paths.c src/runtime_probe.c src/json_helpers.c src/payload_extract.c src/payload_dispatch.c src/trailer_config.c src/runtime_config.c src/sha256.c

.PHONY: all build buildroot busybox payload package package-full package-all package-all-presets package-native release release-full source-mirror source-release verify-artifact check-buildroot-tool-mappings check-licensing target-summary clean menuconfig fetch-sources verify-sources offline-pack offline-unpack detect-host smoke smoke-test smoke-grit-console smoke-grit-console-sections smoke-grit-console-preflight smoke-grit-console-probe-delivery smoke-grit-console-integration smoke-grit-console-integration-bridge-probe smoke-grit-console-integration-command-queue smoke-grit-console-integration-daemon-status smoke-grit-console-line-console smoke-grit-console-transcript unit-test unit-test-console unit-test-qemu unit-test-all test-qemu-user test-qemu-system test-qemu-flaky-network test-release-qemu-penguin test-glinet test-all

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

# Full release: generic supported kernel-era tuple targets × all payload presets.
# Output: dist/releases/full-VERSION-COMMIT/
# Usage:  make release-full            (build everything)
#         make release-full GRIT_RELEASE_NAME=my-label
#         make release-full DRY_RUN=1  (preview jobs without building)
#         make release-full JOBS=4     (build different targets concurrently)
#         make release-full jobs=4     (lowercase alias for command-line use)
GRIT_RELEASE_NAME ?= full-$(shell cat VERSION 2>/dev/null | tr -d '[:space:]')-$(shell git rev-parse --short HEAD 2>/dev/null || printf dev)
RELEASE_JOBS := $(or $(JOBS),$(jobs))
release-full:
	@scripts/make-release \
	  --name "$(GRIT_RELEASE_NAME)" \
	  --matrix tests/matrix/release-full.json \
	  --strict \
	  $(if $(DRY_RUN),--dry-run,) \
	  $(if $(FAIL_FAST),--fail-fast,) \
	  $(if $(RELEASE_JOBS),--jobs "$(RELEASE_JOBS)",) \
	  $(if $(OUT_DIR),--out-dir "$(OUT_DIR)",)

SOURCE_MIRROR_DIR ?= dist/source-mirror/full
SOURCE_RELEASE_NAME ?= source-full-$(shell cat VERSION 2>/dev/null | tr -d '[:space:]')-$(shell git rev-parse --short HEAD 2>/dev/null || printf dev)
SOURCE_RELEASE_DIR ?= dist/releases
source-mirror:
	@scripts/lib/mirror-sources \
	  --matrix tests/matrix/release-full.json \
	  --source-only \
	  --include-buildroot-packages \
	  --all-supported-tools \
	  --out "$(SOURCE_MIRROR_DIR)" \
	  --strict \
	  $(if $(DRY_RUN),--dry-run,) \
	  $(if $(FAIL_FAST),--fail-fast,) \
	  $(if $(VERIFY),--verify,)

source-release: source-mirror
	@if [ -n "$(DRY_RUN)" ]; then \
	  printf '%s\n' "would create $(SOURCE_RELEASE_DIR)/$(SOURCE_RELEASE_NAME).tar.gz from $(SOURCE_MIRROR_DIR)"; \
	else \
	  mkdir -p "$(SOURCE_RELEASE_DIR)"; \
	  tar -C "$$(dirname "$(SOURCE_MIRROR_DIR)")" -czf "$(SOURCE_RELEASE_DIR)/$(SOURCE_RELEASE_NAME).tar.gz" "$$(basename "$(SOURCE_MIRROR_DIR)")"; \
	  printf '%s\n' "$(SOURCE_RELEASE_DIR)/$(SOURCE_RELEASE_NAME).tar.gz"; \
	fi

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

define run_if_python3
	@if command -v python3 >/dev/null 2>&1; then $(1); else printf '%s\n' "skip: $(2)"; fi
endef

smoke-grit-console:
	$(call run_if_python3,tests/smoke/grit-console.py $(if $(GRIT_CONSOLE_SMOKE_SECTION),--section "$(GRIT_CONSOLE_SMOKE_SECTION)",),python3 server smoke unavailable)

smoke-grit-console-sections:
	$(call run_if_python3,tests/smoke/grit-console.py --list-sections,python3 server smoke unavailable)

smoke-grit-console-preflight:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=preflight

smoke-grit-console-probe-delivery:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=probe-delivery

smoke-grit-console-integration:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=integration

smoke-grit-console-integration-bridge-probe:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=integration-bridge-probe

smoke-grit-console-integration-command-queue:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=integration-command-queue

smoke-grit-console-integration-daemon-status:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=integration-daemon-status

smoke-grit-console-line-console:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=line-console

smoke-grit-console-transcript:
	@$(MAKE) smoke-grit-console GRIT_CONSOLE_SMOKE_SECTION=line-console-transcript

unit-test: unit-test-console

unit-test-console:
	@$(MAKE) smoke-grit-console-transcript

unit-test-qemu: test-qemu-user test-qemu-system test-qemu-flaky-network

unit-test-all: unit-test-console unit-test-qemu

smoke-test:
	@tests/smoke/root-grit-console.sh
	@GRIT_CONFIG=presets/payload/default.conf GRIT_BUSYBOX_GROUPS="shell fileops disk process network text system" $(MAKE) package-native
	@tests/smoke/native-artifact-verification.sh dist/grit-native-full
	@tests/smoke/artifact-tiers.sh
	@tests/smoke/native-help.sh dist/grit-native-full
	@tests/smoke/target-resolution.sh
	@tests/smoke/buildroot-host-tools.sh
	@tests/smoke/tuple-consistency.sh
	@tests/smoke/busybox-selection.sh
	@tests/smoke/payload-reality.sh
	@tests/smoke/menuconfig-autoexec.sh
	@tests/smoke/menuconfig-validation.sh
	@tests/smoke/validation-matrix.sh
	@tests/smoke/rehosted-router-presets.sh
	$(call run_if_python3,tests/smoke/config-from-survey.sh,python3 config-from-survey smoke unavailable)
	$(call run_if_python3,tests/smoke/preset-from-survey.sh,python3 preset-from-survey smoke unavailable)
	$(call run_if_python3,tests/smoke/survey-shell.sh dist/grit-native-full,python3 shell survey smoke unavailable)
	@tests/smoke/payload-presets.sh
	@tests/smoke/wolfssl-detection.sh
	@tests/smoke/wolfssl-cross-preflight.sh
	@tests/smoke/build-native-wolfssl.sh
	$(call run_if_python3,tests/smoke/artifact-config.sh dist/grit-native-full,python3 artifact-config smoke unavailable)
	$(call run_if_python3,tests/smoke/heavy-tool-triage.sh,python3 heavy-tool-triage smoke unavailable)
	$(call run_if_python3,tests/smoke/gdbserver-workflow.sh,python3 gdbserver workflow smoke unavailable)
	@tests/smoke/rshell-menu-structure.sh
	@tests/smoke/rshell-transport-names.sh
	@tests/smoke/rshell-external-writes.sh
	$(call run_if_python3,tests/smoke/rshell-status-json.sh dist/grit-native-full,python3 rshell status json smoke unavailable)
	$(call run_if_python3,tests/smoke/plan-json.sh dist/grit-native-full,python3 plan json smoke unavailable)
	@tests/smoke/stale-ux-text.sh
	$(call run_if_python3,tests/smoke/integration-glinet-harness.sh,python3 integration harness smoke unavailable)
	$(call run_if_python3,tests/smoke/integration-report.sh,python3 integration report smoke unavailable)
	$(call run_if_python3,tests/smoke/build-matrix.sh,python3 build matrix smoke unavailable)
	$(call run_if_python3,tests/smoke/qemu-matrix.sh,python3 qemu matrix smoke unavailable)
	$(call run_if_python3,tests/smoke/qemu-flaky-network-lab.sh,python3 qemu flaky network lab smoke unavailable)
	$(call run_if_python3,tests/smoke/release-qemu-penguin.sh,python3 release qemu penguin smoke unavailable)
	$(call run_if_python3,tests/smoke/release-bundles.sh,python3 release bundle smoke unavailable)
	$(call run_if_python3,tests/smoke/release-repo-index.sh,python3 release repo index smoke unavailable)
	$(call run_if_python3,tests/smoke/offline-tools.sh,python3 offline tools smoke unavailable)
	$(call run_if_python3,tests/smoke/licensing.sh,python3 licensing smoke unavailable)
	@tests/smoke/dotfiles-by-app.sh
	@tests/smoke/zsh-dotfiles.sh
	@tests/smoke/runtime-modes.sh
	$(call run_if_python3,tests/smoke/clean-json.sh dist/grit-native-full,python3 clean json smoke unavailable)
	$(call run_if_python3,tests/smoke/recovery.sh dist/grit-native-full,python3 recovery smoke unavailable)
	@tests/smoke/rshell-lifecycle.sh
	@$(MAKE) smoke-grit-console
	$(call run_if_python3,tests/smoke/flaky-network-harness.sh,python3 flaky network harness smoke unavailable)
	$(call run_if_python3,python3 tests/smoke/operator-upload.py dist/grit-native-full,python3 operator upload smoke unavailable)
	$(call run_if_python3,tests/smoke/command-queue.sh dist/grit-native-full,python3 command queue smoke unavailable)
	@tests/smoke/zero-arg-autorun.sh dist/grit-native-full
	@tests/smoke/native-basic-commands.sh dist/grit-native-full
	$(call run_if_python3,tests/smoke/native-json-commands.sh dist/grit-native-full,python3 native JSON smoke unavailable)
	$(call run_if_python3,tests/smoke/manifest-metadata.sh dist/grit-native-full,python3 manifest metadata smoke unavailable)
	$(call run_if_python3,tests/smoke/open-memstream-fallback.sh,python3 open_memstream fallback smoke unavailable)
	$(call run_if_python3,tests/smoke/support-token.sh dist/grit-native-full,python3 support token smoke unavailable)
	$(call run_if_python3,tests/smoke/doctor-json.sh dist/grit-native-full,python3 doctor json smoke unavailable)
	$(call run_if_python3,tests/smoke/reality-test.sh dist/grit-native-full,python3 reality-test smoke unavailable)
	@tests/smoke/core-extraction.sh dist/grit-native-full
	$(call run_if_python3,tests/smoke/survey-config-validation.sh dist/grit-native-full,python3 survey config validation unavailable)
	@tests/smoke/out-of-cwd-extraction.sh dist/grit-native-full
	@printf '%s\n' "smoke-test ok"

test-qemu-user: package-native
	@tests/qemu-user/run-qemu-user-matrix

test-qemu-system:
	@tests/qemu-system/run-qemu-system-matrix

test-qemu-flaky-network:
	@tests/qemu-system/run-flaky-network-lab --run

test-release-qemu-penguin:
	@tests/integration/release-qemu-penguin

test-glinet:
	@tests/integration/glinet/run

test-all: smoke-test test-qemu-user test-qemu-system test-qemu-flaky-network

clean:
	@rm -f dist/grit dist/grit.sha256 dist/grit-*
	@rm -f dist/*.core dist/*.tmp dist/payload*.tar dist/payload*.tar.sha256 dist/payload*.tar.gz dist/payload*.tar.gz.sha256
	@rm -rf dist/internal
	@rm -f src/grit_busybox_applets.h src/grit_heavy_tools.h
	@rm -rf .grit
