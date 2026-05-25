PREFIX ?= /usr/local
CONFIG ?= configs/native-linux.example
OUT ?= dist/busierbox.core
PAYLOAD_FORMAT ?= tgz
CC ?= cc
CFLAGS ?= -Os -Wall -Wextra -std=c99
CPPFLAGS ?=
LDFLAGS ?=

SRC := src/busierbox.c src/applet_payload.c src/applet_survey.c src/applet_envfix.c

.PHONY: all build buildroot busybox payload package package-full package-all package-all-presets package-native release verify-artifact check-buildroot-tool-mappings target-summary clean menuconfig fetch-sources verify-sources offline-pack offline-unpack detect-host smoke smoke-test test-qemu-user test-qemu-system test-glinet test-all

all: build

build: busybox
	@CONFIG="$(CONFIG)" CC="$(CC)" CFLAGS="$(CFLAGS)" CPPFLAGS="$(CPPFLAGS)" LDFLAGS="$(LDFLAGS)" OUT="$(OUT)" scripts/build-native

busybox:
	@scripts/build-busybox

buildroot: fetch-sources
	@scripts/buildroot-build-payload --prepare-only
	@printf '%s\n' "Buildroot source is available via dl/ and extracted on demand by scripts/buildroot-build-payload"

payload:
	@if [ "$(if $(TARGET),$(TARGET),native)" = "native" ]; then $(MAKE) busybox; fi
	@TARGET="$(if $(TARGET),$(TARGET),native)" PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" scripts/build-payload

package:
	@TARGET="$(TARGET)" PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" STRICT="$(STRICT)" VERIFY="$(VERIFY)" scripts/package-selected

package-full:
	@BB_BUILD_FULL=yes BB_BUILD_STAGER=no BB_BUILD_INTERNAL_CORE=no TARGET="$(TARGET)" PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" STRICT="$(STRICT)" VERIFY="$(VERIFY)" scripts/package-selected

package-all: package

package-all-presets:
	@scripts/resolve-target --list | while IFS='	' read -r preset status desc; do \
	  if [ "$$status" = supported ]; then \
	    printf '%s\n' "package preset $$preset"; \
	    PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" scripts/package-target "$$preset"; \
	  else \
	    printf '%s\n' "skip preset $$preset ($$status): $$desc"; \
	  fi; \
	done

package-native:
	@PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" scripts/package-target native

release:
	@PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" BB_RELEASE_NAME="$(BB_RELEASE_NAME)" scripts/release-current "$(if $(TARGET),$(TARGET),--config)"

verify-artifact:
	@if [ -n "$(TARGET)" ]; then artifact="dist/busierbox-$(TARGET)-full"; else artifact="dist/busierbox-native-full"; fi; \
	  scripts/verify-artifact "$$artifact"

check-buildroot-tool-mappings:
	@scripts/check-buildroot-tool-mappings

target-summary:
	@scripts/resolve-target --config

menuconfig:
	@scripts/menuconfig ${CFG:+--config "$(CFG)"}

fetch-sources:
	@scripts/fetch-sources

verify-sources:
	@scripts/verify-sources

offline-pack:
	@scripts/offline-pack

offline-unpack:
	@printf '%s\n' "Usage: scripts/offline-unpack dist/busierbox-sdk-YYYYMMDD.tar.gz"

detect-host:
	@scripts/detect-host

smoke: smoke-test

smoke-test:
	@BUSIERBOX_CONFIG=presets/payload/default.conf BB_BUSYBOX_GROUPS="shell fileops disk process network text system" $(MAKE) package-native
	@scripts/inspect-artifact dist/busierbox-native-full >/dev/null
	@scripts/verify-artifact dist/busierbox-native-full
	@tests/smoke/artifact-tiers.sh
	@tests/smoke/target-resolution.sh
	@tests/smoke/busybox-selection.sh
	@tests/smoke/payload-reality.sh
	@tests/smoke/menuconfig-autoexec.sh
	@tests/smoke/menuconfig-validation.sh
	@tests/smoke/validation-matrix.sh
	@tests/smoke/rehosted-router-presets.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/config-from-survey.sh; else printf '%s\n' "skip: python3 config-from-survey smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/survey-shell.sh dist/busierbox-native-full; else printf '%s\n' "skip: python3 shell survey smoke unavailable"; fi
	@tests/smoke/payload-presets.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/heavy-tool-triage.sh; else printf '%s\n' "skip: python3 heavy-tool-triage smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/gdbserver-workflow.sh; else printf '%s\n' "skip: python3 gdbserver workflow smoke unavailable"; fi
	@tests/smoke/rshell-transport-names.sh
	@tests/smoke/rshell-external-writes.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/rshell-status-json.sh dist/busierbox-native-full; else printf '%s\n' "skip: python3 rshell status json smoke unavailable"; fi
	@tests/smoke/stale-ux-text.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/integration-glinet-harness.sh; else printf '%s\n' "skip: python3 integration harness smoke unavailable"; fi
	@tests/smoke/dotfiles-by-app.sh
	@tests/smoke/zsh-dotfiles.sh
	@tests/smoke/runtime-modes.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/recovery.sh dist/busierbox-native-full; else printf '%s\n' "skip: python3 recovery smoke unavailable"; fi
	@tests/smoke/rshell-lifecycle.sh
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/busierbox-server.py; else printf '%s\n' "skip: python3 server smoke unavailable"; fi
	@tests/smoke/zero-arg-autorun.sh dist/busierbox-native-full
	@./dist/busierbox-native-full list >/dev/null
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox-native-full survey --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox-native-full survey --json --shell-probe | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 shell survey json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox-native-full manifest --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 manifest json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/manifest-metadata.sh dist/busierbox-native-full; else printf '%s\n' "skip: python3 manifest metadata smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then tests/smoke/doctor-json.sh dist/busierbox-native-full; else printf '%s\n' "skip: python3 doctor json smoke unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox-native-full cleanup-ledger --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 cleanup ledger json validation unavailable"; fi
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox-native-full rshell status --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 rshell status json validation unavailable"; fi
	@./dist/busierbox-native-full survey >/dev/null
	@./dist/busierbox-native-full envfix >/dev/null
	@./dist/busierbox-native-full extract >/dev/null
	@./dist/busierbox-native-full extract >/dev/null
	@./dist/busierbox-native-full sh -c 'echo ok' >/dev/null
	@./dist/busierbox-native-full cp --help >/dev/null 2>&1
	@./dist/busierbox-native-full dd --help >/dev/null 2>&1
	@./dist/busierbox-native-full nc --help >/dev/null 2>&1
	@./dist/busierbox-native-full config-info >/dev/null
	@if command -v python3 >/dev/null 2>&1; then tmp=$$(mktemp -d); ./dist/busierbox-native-full survey --json > $$tmp/survey.json; python3 tests/smoke/validate-survey-json.py $$tmp/survey.json >/dev/null; scripts/config-from-survey $$tmp/survey.json >/dev/null; rm -rf $$tmp; else printf '%s\n' "skip: python3 survey config validation unavailable"; fi
	@printf '%s\n' "smoke: testing out-of-cwd embedded extraction (catches exe-wipe bugs)..."
	@_bbx_tmp=$$(mktemp -d) && \
	  cp dist/busierbox-native-full "$$_bbx_tmp/busierbox" && \
	  chmod +x "$$_bbx_tmp/busierbox" && \
	  cd "$$_bbx_tmp" && \
	  ./busierbox extract >/dev/null && \
	  ./busierbox sh -c 'echo dispatch-ok' >/dev/null && \
	  ./busierbox cp --help >/dev/null 2>&1 && \
	  ./busierbox touch --help >/dev/null 2>&1 && \
	  ./busierbox ls --help >/dev/null 2>&1 && \
	  ./busierbox extract >/dev/null && \
	  printf '%s\n' "smoke: out-of-cwd ok" && \
	  cd - >/dev/null && rm -rf "$$_bbx_tmp"
	@printf '%s\n' "smoke-test ok"

test-qemu-user: package
	@tests/qemu-user/run-qemu-user-matrix

test-qemu-system: package
	@tests/qemu-system/run-qemu-system-matrix

test-glinet:
	@tests/integration/glinet/run

test-all: smoke-test test-qemu-user test-qemu-system

clean:
	@rm -f dist/busierbox dist/busierbox.sha256 dist/busierbox-*
	@rm -f dist/*.core dist/*.tmp dist/payload*.tar dist/payload*.tar.sha256 dist/payload*.tar.gz dist/payload*.tar.gz.sha256
	@rm -rf dist/internal
	@rm -f src/bbx_busybox_applets.h src/bbx_heavy_tools.h
	@rm -rf .busierbox
