# Onboarding a second application team to an Azure foundation

**Engineering case study · Azure · Terraform · Platform engineering**  
**Reading time:** about six minutes.

## Decision in brief

Keep shared connectivity under platform ownership. Give each application team a defined network allocation and its own change boundary. Approve connectivity from an explicit traffic requirement, and validate both permitted and denied paths before handing over the environment.

This is a design exercise grounded in the working [Azure platform foundation](../README.md). Team A and Team B are fictional. The repository now implements one hub, Team A and an optional Team B spoke with separate owner tags. Separate state, deployment identities and the operating model below remain **proposed extensions**, not completed customer work.

**Evidence:** the original baseline passed provider validation and [five Terraform mock tests](https://github.com/baileynyx/azure-platform-foundation/actions/runs/34357895861). The second-team increment adds regression and invalid-input tests; see the [current validation record](../VALIDATION.md) for its execution status. No Azure deployment or packet-flow verification has been performed.

## The scenario and requirements

Assume Team A uses the first spoke and Team B needs a separate application environment. Both teams need predictable onboarding, but neither should be able to replace shared networking through an ordinary application change.

For this exercise, Team B needs a private workload subnet and a narrowly scoped connection to a future shared service in the hub. Direct application traffic between the two teams is not required. The service and its port are intentionally not implemented; agreeing that contract is a prerequisite to an allow rule.

A successful onboarding would require:

- An allocation checked against the organization's network inventory, with an accountable owner.
- A deployment boundary that keeps routine team changes away from shared resources.
- Explicit approval of required connections, with unrelated inbound traffic denied.
- Tests for allowed and denied paths, a handover record, and a recovery procedure.

No measured onboarding time or production reliability outcome is claimed.

## What the repository proves today

The [root configuration](../main.tf) derives a hub and Team A spoke from one IPv4 /16, with Team B enabled by an optional input object. All use the same [network module](../modules/network/main.tf): VNet, workload subnet, NSG, inbound deny rule and subnet-to-NSG association. Each enabled spoke has both peering directions to the hub, without forwarded traffic or gateway transit.

| Capability | Current implementation | Remaining operational work |
| --- | --- | --- |
| Address allocation | Hub slot 0; Team A slot 1; optional Team B slot 2 by default (`10.42.32.0/20`) | Check and reserve the allocation in the real network inventory |
| Workload subnet | One /24 per VNet, including Team B when enabled | Deploy workloads and verify connectivity |
| Ownership | Platform owner on hub/resource group; optional Team A owner; required enabled Team B owner | Enforce authority with identity scopes, not tags |
| State | One root and one resource group using local state by default | Independently controlled remote states and resource scopes |
| Connectivity | Both peering directions per spoke and explicit inbound deny | Approval process and narrow application allow rules |
| Delivery | Credential-free validation workflow | Separate protected deployment workflow with OIDC |

The Team B allocation follows the existing arithmetic; it is not a reservation in a real IP address management system. Its index must be an integer from 2 to 15, preventing reuse of the hub and Team A slots. The code does not inspect networks elsewhere in Azure or on premises.

## Decision 1: separate state by ownership and lifecycle

One state is reasonable for this small lab: relationships are visible in one plan and there are few moving parts. Once independent teams own workloads, the same boundary would couple unrelated changes and give an application deployment more reach than it needs.

The proposed division is:

| Boundary | Owns | Change authority |
| --- | --- | --- |
| Platform connectivity | Hub, both directions of each peering, shared routing decisions | Platform review and platform deployment identity |
| Team A foundation | Team A resource group, VNet, subnet and NSG | Team-scoped deployment identity and reviewed network contract |
| Team B foundation | Team B resource group, VNet, subnet and NSG | Team-scoped deployment identity and reviewed network contract |

Both ends of each peering belong to one platform-controlled configuration, avoiding competing management of the same resource. Teams provide VNet identifiers through a validated onboarding record. This introduces sequencing: create the spoke before creating its peerings, and remove its peerings before deleting the spoke.

Use separately controlled Azure Blob state storage with Entra authentication and access aligned to these boundaries. Different state keys alone are not an authorization boundary; permissions must enforce the intended separation. The AzureRM backend provides native locking and consistency checking. Locking prevents conflicting state writers; it does not decide who should have access. [Terraform AzureRM backend](https://developer.hashicorp.com/terraform/language/backend/azurerm)

For an already deployed environment, splitting state would need an explicit resource-address migration plan, backups and a controlled change window. Each Azure object must have one active Terraform owner. Verify a migration plan shows no unintended replacements before applying. That migration is not part of this lab.

## Decision 2: reuse the module, not the entire foundation

Team B can reuse the network module, but copying the root would create another hub-and-spoke foundation rather than extend the shared one.

The implemented increment adds `team_b` and `team_a_owner` inputs while retaining `module.spoke` and both original peering addresses. Team B uses the stable key `team_b` in its own module and peerings. Platform metadata still uses `owner`; Team A inherits that value unless overridden, and enabled Team B requires an owner. These tags identify responsibility but do not grant or restrict access. Validate every requested allocation against the authoritative network inventory.

The tradeoff is additional configuration and orchestration. It is justified when owners and release schedules differ; it would be unnecessary complexity for a disposable single-operator lab.

## Decision 3: treat peering and permission as separate decisions

The module's deny rule uses priority 4096, ahead of Azure's default rules. A future required connection needs a narrower allow rule with a lower priority number. Azure processes lower numbers first. [Azure NSG rule evaluation](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview)

For the fictional shared-service request, record the source subnet, destination, protocol, port, service owner and review date. Approve that specific contract rather than opening the entire peered address space.

The baseline has no application allow rules, no central inspection service and no custom outbound controls. It therefore does not demonstrate working application connectivity, controlled egress or transit through a hub appliance. The proposed handover must test those requirements explicitly wherever they are introduced.

## Decision 4: separate validation from deployment authority

Keep pull-request formatting, schema validation and mock tests credential-free. A proposed deployment workflow would use a reviewed commit, a protected environment and a narrowly scoped Azure identity. OIDC avoids storing long-lived Azure credentials in GitHub; trust and environment rules still need deliberate configuration. [GitHub OIDC for Azure](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure)

The platform identity would manage shared connectivity; team identities would manage only their assigned foundation scope. Platform review should be required for connectivity changes. Application owners should approve their service requirements.

Approval should identify the exact commit and deployment plan. Treat saved plans as sensitive, limit access and retention, and produce a new reviewed plan when the source or relevant state changes. The current repository contains none of this privileged deployment automation.

## Failure handling and recovery

| Failure | Detection | Response |
| --- | --- | --- |
| Team B allocation overlaps another network | Network inventory check before deployment | Reject the request and allocate an approved range; mock tests cannot discover estate-wide overlap |
| An allow rule exposes more than the agreed service | Rule review and negative connectivity tests | Stop handover, narrow the rule and retest required and forbidden paths |
| Apply succeeds only partially | Terraform failure output, state inspection and Azure inspection | Retain state, stop concurrent writers, diagnose the failure, then review a fresh plan before retrying |
| One direction of peering is absent | Inspect both peering resources and effective connectivity | Reconcile the missing side through its platform owner; do not widen NSGs as a guess |
| Team teardown would affect shared resources | Review a destroy plan against the ownership contract | Stop the change; remove platform-owned peerings in order and limit teardown to the team's resources |
| A rollback introduces replacements | Review the plan generated from the proposed source revision | Choose a controlled forward fix or approved recovery plan; reverting Git alone does not reverse infrastructure |

If a state lock remains after a failure, first establish that no writer is active. A force unlock is an exceptional recovery action, not a routine retry step.

These are proposed operating procedures. No incident, outage or recovery timing is represented as observed.

## Evidence and remaining acceptance gates

The original five-test baseline in the [recorded validation](../VALIDATION.md) covers source commit [20eb4cf](https://github.com/baileynyx/azure-platform-foundation/commit/20eb4cf1372a8f27eafb9ebf69f1a1d30e96718e):

| Passing mock run | What it checks |
| --- | --- |
| `network_contract` | Expected hub/spoke allocations, the resource-group owner tag and disabled forwarded traffic |
| `invalid_environment` | Rejection of `prod` by the lab's environment input |
| `invalid_owner` | Rejection of a blank owner |
| `invalid_cidr` | Rejection of a /24 where the root requires a /16 |
| `subnet_security_contract` | The child module's inbound deny direction, access, priority and wildcard address fields |

These assertions do not establish Azure authorization, deployed NSG association, packet flow, DNS behavior or recovery. A green mock suite is evidence about the specified configuration, not an operational acceptance test.

The new [two-team test suite](../tests/two_teams.tftest.hcl) compares Team A and hub configuration before and after Team B is enabled, verifies owner tags and peerings, exercises custom allocation and disabling, and rejects invalid owners and reserved or invalid allocation slots. This is configuration regression evidence, not a live state transition or network isolation test.

Before claiming Team B is operationally onboarded, the extension would need:

1. Successful review and execution of the second-spoke implementation and regression tests; current status is linked in `VALIDATION.md`.
2. Remote state and identity checks showing that team deployments cannot modify platform-owned resources.
3. A disposable Azure rehearsal verifying NSG associations, both peerings and required DNS behavior.
4. Positive tests for approved connections and negative tests for prohibited inter-team traffic.
5. A reviewed teardown demonstrating that Team B can be removed while shared and Team A resources remain.
6. A handover record linking actual plans, test results, owners, cost review and recovery instructions.

## Engineering takeaway

Adding a second spoke is a small configuration change. Giving a second team reliable ownership requires explicit decisions about state, authority, dependencies and recovery.

The first implementation increment now supplies the optional second spoke, per-team owner tags, a runnable variable example and configuration tests. Remote state and protected deployment remain separately reviewable future changes. Each stage should publish the evidence it actually produces.

[Back to the project](../README.md) · [Bailey's profile](https://github.com/baileynyx)
