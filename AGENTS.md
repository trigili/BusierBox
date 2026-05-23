# Agent Instructions

- Keep scripts POSIX-sh-compatible where practical. Use small helper programs only when the job is impractical or unsafe in shell, such as strict JSON parsing.
- Do not add network dependencies without updating `manifests/sources.lock.json` with pinned `version`, `url`, `sha256`, and `filename`.
- Preserve offline reproducibility. Anything required to rebuild should be fetchable into `dl/`, verifiable by hash, and packable by `scripts/offline-pack`.
- Avoid vendoring large third-party source trees in this repository.
- Add smoke checks or tests for new supervisor commands, dispatch behavior, and build scripts.
- Keep the core applets useful without assuming `/tmp` is writable.
- Do not fork or import BusyBox code into this repository.
- Do not reimplement standard Unix utilities in BusierBox core. Dispatch to BusyBox or another upstream payload tool instead.
- Keep native BusierBox code limited to supervisor functionality such as `survey`, `envfix`, `extract`, `clean`, `list`, and `config-info`.
- Prefer upstream tools and Buildroot-compatible packaging for payloads.
- Every native supervisor command must support `--help` and return success for help output.
- Prefer simple C and POSIX/Linux syscalls in the supervisor. Avoid external runtime dependencies in Tier 0 where practical.
- Preserve the static-first policy for BusierBox and payload tools.
- Bundled shared libraries in `runtime/payload/lib` are acceptable when fully static payload builds are unavailable, but builds must warn clearly.
- Run `make smoke-test` after applet changes. Add or extend smoke checks when adding behavior.
- Keep `survey --json` valid JSON and parse-check it when Python is available.
