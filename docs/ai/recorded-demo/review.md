# AI-assisted Terraform review

Provider: deterministic_baseline

Deterministic policy: **review_required**

Advisory only. This report is not approval to apply.

Local input SHA-256: ee1c1d8853276634fc27af9c52aee1a4ec038cc7bf0fc255677829393de355de

**Offline demonstration: no live model was called.**


## R001 azurerm&#95;virtual&#95;network&#95;peering.hub&#95;to&#95;team&#95;b&#91;&quot;team&#95;b&quot;&#93;

Evidence: `/resource_changes/2/change`; mode: managed; actions: create -> delete; unknown values: not_reported.

Replacement includes removal of the old object. Review ordering, dependencies and recovery.

- How will cutover and temporary capacity be verified before the old object is removed?
- What tested recovery procedure and retained data are available if this change fails?
- Which functional and monitoring checks will confirm the intended result?

## R002 module.hub.azurerm&#95;virtual&#95;network.this

Evidence: `/resource_changes/3/change`; mode: managed; actions: no-op; unknown values: not_reported.

No resource action is listed. This does not prove the wider deployment is safe.

- Which functional and monitoring checks will confirm the intended result?

## R003 module.team&#95;b&#91;&quot;team&#95;b&quot;&#93;.azurerm&#95;subnet.workload

Evidence: `/resource_changes/0/change`; mode: managed; actions: delete; unknown values: not_reported.

Removal is planned. Check dependencies, retained data and recovery before proceeding.

- What tested recovery procedure and retained data are available if this change fails?
- Which functional and monitoring checks will confirm the intended result?

## R004 module.team&#95;b&#91;&quot;team&#95;b&quot;&#93;.azurerm&#95;virtual&#95;network.this

Evidence: `/resource_changes/1/change`; mode: managed; actions: delete -> create; unknown values: not_reported.

Replacement includes removal of the old object. Review ordering, dependencies and recovery.

- What interruption window is acceptable when destruction precedes creation?
- What tested recovery procedure and retained data are available if this change fails?
- Which functional and monitoring checks will confirm the intended result?

Limits: no attribute analysis, dependency graph, cost estimate, live outage prediction, deployment execution or signature verification. Input hashes identify bytes but do not authenticate them.
