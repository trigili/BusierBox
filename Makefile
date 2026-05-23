PREFIX ?= /usr/local
CONFIG ?= configs/native-linux.example
OUT ?= dist/busierbox
CC ?= cc
CFLAGS ?= -Os -Wall -Wextra -std=c99
CPPFLAGS ?=
LDFLAGS ?=

SRC := src/busierbox.c src/applet_sh.c src/applet_survey.c src/applet_envfix.c src/applet_basic.c src/applet_net.c

.PHONY: all build clean menuconfig fetch-sources verify-sources offline-pack offline-unpack detect-host smoke smoke-test test-qemu-user test-qemu-system test-all

all: build

build:
	@CONFIG="$(CONFIG)" CC="$(CC)" CFLAGS="$(CFLAGS)" CPPFLAGS="$(CPPFLAGS)" LDFLAGS="$(LDFLAGS)" OUT="$(OUT)" scripts/build-native

menuconfig:
	@printf '%s\n' "No interactive menuconfig yet. Start from configs/native-linux.example or pass CONFIG=..."

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

smoke-test: build
	@./dist/busierbox list >/dev/null
	@if command -v python3 >/dev/null 2>&1; then ./dist/busierbox survey --json | python3 -m json.tool >/dev/null; else printf '%s\n' "skip: python3 json validation unavailable"; fi
	@./dist/busierbox survey >/dev/null
	@./dist/busierbox envfix >/dev/null
	@printf 'abc\n' | ./dist/busierbox cat >/dev/null
	@printf 'abc\n' | ./dist/busierbox hexdump >/dev/null
	@printf 'xxabcdyy\n' | ./dist/busierbox strings >/dev/null
	@printf 'abc' | ./dist/busierbox sha256sum >/dev/null
	@printf 'abc' | ./dist/busierbox base64 >/dev/null
	@./dist/busierbox http --help >/dev/null
	@./dist/busierbox serve --help >/dev/null
	@./dist/busierbox nc --help >/dev/null
	@if command -v python3 >/dev/null 2>&1; then tmp=$$(mktemp -d); ./dist/busierbox survey --json > $$tmp/survey.json; tests/smoke/validate-survey-json.py $$tmp/survey.json >/dev/null; scripts/config-from-survey $$tmp/survey.json >/dev/null; rm -rf $$tmp; else printf '%s\n' "skip: python3 survey config validation unavailable"; fi
	@printf '%s\n' "smoke-test ok"

test-qemu-user: build
	@tests/qemu-user/run-qemu-user-matrix

test-qemu-system: build
	@tests/qemu-system/run-qemu-system-matrix

test-all: smoke-test test-qemu-user test-qemu-system

clean:
	@rm -f dist/busierbox dist/busierbox.*.tmp dist/busierbox.tmp
