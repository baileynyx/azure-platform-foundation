# Terraform change review

**Result: REVIEW REQUIRED**

Policy: destructive-actions-v1

Input JSON SHA-256: ee1c1d8853276634fc27af9c52aee1a4ec038cc7bf0fc255677829393de355de

This action review is not approval to apply. Resource values, variables and outputs are omitted.

## Summary

| Action | Resource objects |
| --- | ---: |
| unchanged | 1 |
| create | 0 |
| read | 0 |
| update | 0 |
| delete | 1 |
| replace | 2 |

## Resource review

| Address | Mode | Actions | Decision and reason |
| --- | --- | --- | --- |
| azurerm&#95;virtual&#95;network&#95;peering.hub&#95;to&#95;team&#95;b&#91;&quot;team&#95;b&quot;&#93; | managed | create -&gt; delete | REVIEW: Create before destroy still removes the old object: review cutover, capacity and recovery. |
| module.hub.azurerm&#95;virtual&#95;network.this | managed | no-op | No destructive action identified. |
| module.team&#95;b&#91;&quot;team&#95;b&quot;&#93;.azurerm&#95;subnet.workload | managed | delete | REVIEW: Object removal: review dependents, retained data and recovery before proceeding. |
| module.team&#95;b&#91;&quot;team&#95;b&quot;&#93;.azurerm&#95;virtual&#95;network.this | managed | delete -&gt; create | REVIEW: Destroy before create: review interruption, dependent resources and recovery. |

Limits: updates can still disrupt service. This policy does not evaluate attribute values, cost,
network reachability, drift, output changes or Terraform check results. It does not authenticate
the JSON or prove that a later apply uses the same saved plan.
