# Agent Instructions

- Keep scripts POSIX-sh-compatible where practical. Use small helper programs only when the job is impractical or unsafe in shell, such as strict JSON parsing.
- Do not add network dependencies without updating `manifests/sources.lock.json` with pinned `version`, `url`, `sha256`, and `filename`.
- Preserve offline reproducibility. Anything required to rebuild should be fetchable into `dl/`, verifiable by hash, and packable by `scripts/lib/offline-pack`.
- Avoid vendoring large third-party source trees in this repository.
- Add smoke checks or tests for new supervisor commands, dispatch behavior, and build scripts.
- Keep the core applets useful without assuming `/tmp` is writable.
- Do not fork or import BusyBox code into this repository.
- Do not reimplement standard Unix utilities in griTTYkit core. Dispatch to BusyBox or another upstream payload tool instead.
- Keep native griTTYkit code limited to supervisor functionality such as `survey`, `envfix`, `extract`, `clean`, `list`, and `config-info`.
- Prefer upstream tools and Buildroot-compatible packaging for payloads.
- Every native supervisor command must support `--help` and return success for help output.
- Prefer simple C and POSIX/Linux syscalls in the supervisor. Avoid external runtime dependencies in Tier 0 where practical.
- Preserve the static-first policy for griTTYkit and payload tools.
- Bundled shared libraries in `runtime/payload/lib` are acceptable when fully static payload builds are unavailable, but builds must warn clearly.
- Run `make smoke-test` after applet changes. Add or extend smoke checks when adding behavior.
- Keep `survey --json` valid JSON and parse-check it when Python is available.


<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
