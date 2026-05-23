PREFIX ?= /usr/local
CONFIG ?= configs/native-linux.example
OUT ?= dist/busierbox.core
PAYLOAD_FORMAT ?= tgz
TARGET ?= native
CC ?= cc
CFLAGS ?= -Os -Wall -Wextra -std=c99
CPPFLAGS ?=
LDFLAGS ?=

SRC := src/busierbox.c src/applet_payload.c src/applet_survey.c src/applet_envfix.c

.PHONY: all build buildroot busybox payload package clean menuconfig fetch-sources verify-sources offline-pack offline-unpack detect-host smoke smoke-test test-qemu-user test-qemu-system test-all

all: build

build: busybox
	@CONFIG="$(CONFIG)" CC="$(CC)" CFLAGS="$(CFLAGS)" CPPFLAGS="$(CPPFLAGS)" LDFLAGS="$(LDFLAGS)" OUT="$(OUT)" scripts/build-native

busybox:
	@scripts/build-busybox

buildroot: fetch-sources
	@scripts/buildroot-build-payload --prepare-only
	@printf '%s\n' "Buildroot source is available via dl/ and extracted on demand by scripts/buildroot-build-payload"

payload:
	@if [ "$(TARGET)" = "native" ]; then $(MAKE) busybox; fi
	@TARGET="$(TARGET)" PAYLOAD_FORMAT="$(PAYLOAD_FORMAT)" scripts/build-payload

package: payload
	@$(MAKE) build
	@scripts/embed-payload dist/busierbox.core dist/payload.$(if $(filter tar,$(PAYLOAD_FORMAT)),tar,tar.gz) dist/busierbox

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

smoke-test: package
	@./dist/busierbox list >/dev/null
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox survey --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 json validation unavailable"; fi
	@./dist/busierbox survey >/dev/null
	@./dist/busierbox envfix >/dev/null
	@./dist/busierbox extract >/dev/null
	@./dist/busierbox extract >/dev/null
	@./dist/busierbox sh -c 'echo ok' >/dev/null
	@./dist/busierbox cp --help >/dev/null 2>&1
	@./dist/busierbox dd --help >/dev/null 2>&1
	@./dist/busierbox nc --help >/dev/null 2>&1
	@./dist/busierbox config-info >/dev/null
	@if command -v python3 >/dev/null 2>&1; then tmp=$$(mktemp -d); ./dist/busierbox survey --json > $$tmp/survey.json; tests/smoke/validate-survey-json.py $$tmp/survey.json >/dev/null; scripts/config-from-survey $$tmp/survey.json >/dev/null; rm -rf $$tmp; else printf '%s\n' "skip: python3 survey config validation unavailable"; fi
	@printf '%s\n' "smoke: testing out-of-cwd embedded extraction (catches exe-wipe bugs)..."
	@_bbx_tmp=$$(mktemp -d) && \
	  cp dist/busierbox "$$_bbx_tmp/busierbox" && \
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
	@rm -f dist/busierbox dist/busierbox.core dist/busierbox.*.tmp dist/busierbox.tmp dist/payload.tar dist/payload.tar.sha256 dist/payload.tar.gz dist/payload.tar.gz.sha256
	@rm -f src/bbx_busybox_applets.h src/bbx_heavy_tools.h
	@rm -rf .busierbox
