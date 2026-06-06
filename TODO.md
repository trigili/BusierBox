# Future Cleanup

These are follow-up ideas parked after the `grit-console` post-closure
architecture refactor. They are not active goal work.

## `grit-console` polish

* Revisit bridge-route public callback naming to reduce aliasing such as
  `bridge_profile_headless_command` being imported under collision-avoidance
  aliases in composition modules.
* Consider splitting `run_probe_workflow_action` and
  `handle_workflow_action_args` if workflow command families grow again or
  their dispatch branches need isolated tests.
* Consider retiring or narrowing `dispatch_legacy_target_detail_number` when
  legacy numeric target-detail dispatch is no longer needed for compatibility.
