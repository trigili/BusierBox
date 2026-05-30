# Flaky Network Harness

`tests/integration/flaky-network-harness.py` is a deterministic, non-QEMU
intermittent-connectivity harness for the operator control plane. It exercises
the same contracts that a networked QEMU lab should later validate across
virtual network boundaries:

- queued target mailbox work survives while targets are offline
- queued target mailbox work survives operator-daemon stop/start boundaries
- queued survey bootstrap and staged-file fetch work can be prepared before any
  target reconnect
- anonymous polls do not drain target-scoped mailboxes
- anonymous polls are recorded as phone-home attempts with an explicit pending
  reason when queued work requires target identity
- bad-token polls are rejected, recorded as failed phone-home attempts, and do
  not drain queued mailbox work
- a short phone-home window delivers only the reconnecting target's work
- duplicate polls do not redeliver already delivered commands
- target-mismatched result uploads are rejected, recorded with the mismatch
  reason, and do not mutate the delivered command
- dropped/truncated result uploads are rejected without mutating delivered work
- rejected result uploads are exposed as failed phone-home attempts with the
  rejection reason
- failed command results and expired queued work remain visible in mailbox state
- target result upload updates `last_seen`, mailbox, and latest-result state
- survey bootstrap script/result flows refresh target survey state
- interrupted file uploads are recorded as truncated target file activity
- interrupted file uploads are exposed through upload status indexes, target
  latest-file-transfer indexes, retained forensic payload metadata, event
  records, and headless target status text
- bridge relay activity is attributed back to the selected target

Run it directly when debugging:

```sh
tests/integration/flaky-network-harness.py --artifact-dir local/flaky-network/latest
```

The artifact directory contains HTTP transcripts, per-phase operator status
JSON, dropped-result evidence, bridge response data, and `summary.json`. It also
writes focused debug artifacts that mirror the QEMU lab contract:
`target-mailbox.json`, `offline-workflow-mailbox.json`, `command-result.json`,
`phone-home-attempts.json`, `mailbox-lifecycle.json`,
`restart-persistence.json`, `bad-token-phone-home.json`,
`target-mismatch-phone-home.json`, `transfer.log`, `bridge-events.jsonl`, and
`artifact-manifest.json`. The smoke wrapper
`tests/smoke/flaky-network-harness.sh` runs the same scenario from
`make smoke-test` with a temporary artifact directory and validates those
focused artifacts.

The harness intentionally uses only Python stdlib and loopback sockets so it can
run in CI without QEMU, tap devices, root privileges, or network downloads. A
future QEMU lab should reuse the same phase names and expected artifacts while
adding operator/target VM topology, link-state transitions, image/kernel
metadata, tap/bridge setup, target-side poll logs, and proof that queued survey
and staged-file fetch mailbox work drains during a short reconnect window while
failed and expired mailbox records stay inspectable.

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
