# Agent Instructions

- Keep scripts POSIX-sh-compatible where practical. Use small helper programs only when the job is impractical or unsafe in shell, such as strict JSON parsing.
- Do not add network dependencies without updating `manifests/sources.lock.json` with pinned `version`, `url`, `sha256`, and `filename`.
- Preserve offline reproducibility. Anything required to rebuild should be fetchable into `dl/`, verifiable by hash, and packable by `scripts/offline-pack`.
- Avoid vendoring large third-party source trees in this repository.
- Add smoke checks or tests for new applets and build scripts.
- Keep the core applets useful without assuming `/tmp` is writable.
- Do not fork or import BusyBox code into this repository.
- Keep applets small and embedded-focused. Do not chase full GNU/coreutils compatibility unless the user explicitly asks for it.
- Every applet must support `--help` and return success for help output.
- Prefer simple C and POSIX/Linux syscalls. Avoid external runtime dependencies in Tier 0.
- Run `make smoke-test` after applet changes. Add or extend smoke checks when adding behavior.
- Keep `survey --json` valid JSON and parse-check it when Python is available.
