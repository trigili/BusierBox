# Flaky Network Harness

`tests/integration/flaky-network-harness.py` is a deterministic, non-QEMU
intermittent-connectivity harness for the operator control plane. It exercises
the same contracts that a networked QEMU lab should later validate across
virtual network boundaries:

- queued target mailbox work survives while targets are offline
- anonymous polls do not drain target-scoped mailboxes
- a short phone-home window delivers only the reconnecting target's work
- duplicate polls do not redeliver already delivered commands
- target result upload updates `last_seen`, mailbox, and latest-result state
- survey bootstrap script/result flows refresh target survey state
- interrupted file uploads are recorded as truncated target file activity
- bridge relay activity is attributed back to the selected target

Run it directly when debugging:

```sh
tests/integration/flaky-network-harness.py --artifact-dir local/flaky-network/latest
```

The artifact directory contains HTTP transcripts, per-phase operator status
JSON, bridge response data, and `summary.json`. The smoke wrapper
`tests/smoke/flaky-network-harness.sh` runs the same scenario from
`make smoke-test` with a temporary artifact directory.

The harness intentionally uses only Python stdlib and loopback sockets so it can
run in CI without QEMU, tap devices, root privileges, or network downloads. A
future QEMU lab should reuse the same phase names and expected artifacts while
adding operator/target VM topology, link-state transitions, image/kernel
metadata, tap/bridge setup, and target-side poll logs.

For the networked-QEMU path, `tests/qemu-system/run-flaky-network-lab` creates
that lab plan without requiring QEMU by default:

```sh
tests/qemu-system/run-flaky-network-lab --artifact-root local/qemu-flaky/latest
```

The plan artifacts include `topology.json`, `link-transitions.json`,
`operator-commands.sh`, `target-commands.sh`, `plan.json`, and `summary.json`.
They record the operator node, target nodes, controllable links, phase names,
expected per-phase artifacts, QEMU command template, and the exact operator and
target commands to run once a real image/kernel/tap setup is available.

To ask for the opt-in QEMU path, use:

```sh
make test-qemu-flaky-network
```

Like the existing QEMU matrix runner, this remains skip-friendly when the
example environments are disabled or the local host lacks the requested QEMU
inputs.
