PREFIX ?= /usr/local
CONFIG ?= configs/native-linux.example
OUT ?= dist/busierbox.core
PAYLOAD_FORMAT ?= tgz
CC ?= cc
CFLAGS ?= -Os -Wall -Wextra -std=c99
CPPFLAGS ?=
LDFLAGS ?=

SRC := src/busierbox.c src/applet_payload.c src/applet_survey.c src/applet_envfix.c

.PHONY: all build buildroot busybox payload package package-all package-all-presets package-native verify-artifact target-summary clean menuconfig fetch-sources verify-sources offline-pack offline-unpack detect-host smoke smoke-test test-qemu-user test-qemu-system test-all

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

verify-artifact:
	@if [ -n "$(TARGET)" ]; then artifact="dist/busierbox-$(TARGET)"; else artifact="dist/busierbox-native"; fi; \
	  scripts/verify-artifact "$$artifact"

target-summary:
	@scripts/resolve-target --config

menuconfig:
	@scripts/menuconfig

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

smoke-test: package-native
	@scripts/verify-artifact dist/busierbox-native
	@tests/smoke/target-resolution.sh
	@tests/smoke/payload-reality.sh
	@./dist/busierbox-native list >/dev/null
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox-native survey --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 json validation unavailable"; fi
	@./dist/busierbox-native survey >/dev/null
	@./dist/busierbox-native envfix >/dev/null
	@./dist/busierbox-native extract >/dev/null
	@./dist/busierbox-native extract >/dev/null
	@./dist/busierbox-native sh -c 'echo ok' >/dev/null
	@./dist/busierbox-native cp --help >/dev/null 2>&1
	@./dist/busierbox-native dd --help >/dev/null 2>&1
	@./dist/busierbox-native nc --help >/dev/null 2>&1
	@./dist/busierbox-native config-info >/dev/null
	@if command -v python3 >/dev/null 2>&1; then tmp=$$(mktemp -d); ./dist/busierbox-native survey --json > $$tmp/survey.json; tests/smoke/validate-survey-json.py $$tmp/survey.json >/dev/null; scripts/config-from-survey $$tmp/survey.json >/dev/null; rm -rf $$tmp; else printf '%s\n' "skip: python3 survey config validation unavailable"; fi
	@printf '%s\n' "smoke: testing out-of-cwd embedded extraction (catches exe-wipe bugs)..."
	@_bbx_tmp=$$(mktemp -d) && \
	  cp dist/busierbox-native "$$_bbx_tmp/busierbox" && \
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

test-all: smoke-test test-qemu-user test-qemu-system

clean:
	@rm -f dist/busierbox dist/busierbox.sha256 dist/busierbox-*
	@rm -f dist/*.core dist/*.tmp dist/payload*.tar dist/payload*.tar.sha256 dist/payload*.tar.gz dist/payload*.tar.gz.sha256
	@rm -f src/bbx_busybox_applets.h src/bbx_heavy_tools.h
	@rm -rf .busierbox
