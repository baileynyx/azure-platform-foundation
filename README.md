# Azure platform foundation

A small subscription-level Terraform networking foundation: one resource group, a hub and Team A spoke, plus an optional Team B spoke. Each VNet has a workload subnet and associated NSG with an explicit inbound deny rule. Each spoke peers with the hub in both directions.

**This is an independent networking lab, not a complete enterprise landing zone.** It contains no compute, managed firewall, gateway, public IP, or Azure deployment automation. CI validates without cloud credentials.

## Start here: five-minute interview demo

[Follow the demo walkthrough](DEMO.md) for the architecture, copyable validation commands, expected results, regression assertions and engineering tradeoffs. No Azure credentials are needed; the walkthrough links the merged implementation and its 17 passing mock tests.

## Featured engineering case study

[Onboarding a second application team](docs/second-team-case-study.md): the implemented second-spoke increment, its regression evidence, and the state ownership, connectivity approval and recovery work still required for a team-operated platform.

## Five-minute review

Install Terraform 1.9 or later (less than 2.0). Provider installation requires internet access.

```shell
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

Mock tests use the real provider schema and synthetic computed values. They verify configuration contracts, not Azure permissions, service availability or packet flow. See `VALIDATION.md` for checks actually executed.

## Enable the second team

The default remains one hub and one spoke. `team_b = null` creates no Team B resources. The [two-team example](examples/two-teams.example.tfvars) assigns owners and enables Team B:

```hcl
owner        = "platform-engineering"
team_a_owner = "application-team-a"
team_b = {
  owner            = "application-team-b"
  allocation_index = 2
}
```

| Input | Default | Behavior |
| --- | --- | --- |
| `owner` | `platform-engineering` | Owner tag for the resource group and hub |
| `team_a_owner` | `null` | Team A inherits `owner`; a nonblank override changes its VNet and NSG owner tags |
| `team_b` | `null` | Non-null object enables the optional spoke and requires a nonblank owner |
| `team_b.allocation_index` | `2` when enabled | Integer 2–15 selects a /20; slots 0 and 1 remain reserved for hub and Team A |

No new state boundary or Azure permission is created by an owner tag. All resources still share one root state and resource group. Existing `module.spoke` and peering addresses, Azure resource names, and `hub`/`spoke` output keys are retained. Changing only `team_b` leaves Team A and hub inputs unchanged. Setting `team_a_owner` intentionally changes Team A's owner tags.

`network_allocations` and `subnet_ids` gain a `team_b` key only when enabled. `network_configuration` exposes configured names, allocations, owner tags and inbound-deny rule fields for review. It does not report live connectivity.

Run the dedicated cloud-free regression suite with `terraform test -filter=tests/two_teams.tftest.hcl`. For an optional real Azure rehearsal, use the prerequisites below and pass `-var-file=examples/two-teams.example.tfvars` to `terraform plan`; review the saved plan before apply.

After deployment, changing the Team B allocation can disrupt or replace its network resources. Setting `team_b = null` plans removal of its network and peerings. Review that plan, remove dependent workloads first and verify Team A/shared resources are unaffected. Configuration tests do not prove a live teardown is safe.

## Architecture

```mermaid
flowchart TD
  HUB["Hub: 10.42.0.0/20"] <-->|"Peering"| A["Team A: 10.42.16.0/20"]
  HUB <-->|"Optional peering"| B["Team B: 10.42.32.0/20"]
  HUB --> HN["10.42.0.0/24; NSG inbound deny"]
  A --> AN["10.42.16.0/24; NSG inbound deny"]
  B --> BN["10.42.32.0/24; NSG inbound deny"]
```

Peering creates routes; it does not override the NSGs. There are no allow rules or workloads. Default Azure outbound rules remain, so this is not a design for controlled egress. The network module keeps subnets separate from VNet inline configuration to avoid competing resource ownership.

## Decisions

| Decision | Rationale and tradeoff |
| --- | --- |
| Derive /20 VNets from one /16 with reserved slots | Prevent overlap within this deployment; check the /16 against the real estate before using it. |
| Optional Team B with a stable instance key | Preserve existing Team A resource addresses and avoid an unnecessary state migration. |
| Per-team owner tags with a compatible fallback | Identify spoke ownership while preserving the original owner by default; tags are not RBAC boundaries. |
| One reusable network module | Makes the hub/spoke resource contract consistent without hiding a large framework. |
| Override the default VNet inbound allow | Make traffic intent explicit. Adding a workload requires reviewed narrow allow rules. |
| Tag validation | Provides ownership metadata, not policy enforcement across a subscription. |
| Local state for an isolated lab | Makes the demo small; unsuitable for team deployment. Remote state is a separate bootstrap responsibility. |
| AzureRM 4.x compatibility line | A deliberate baseline tested by CI; evaluate major upgrades in a separate change. |

For an enterprise landing zone, evaluate [Azure Verified Modules and Microsoft's implementation options](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/implementation-options), management groups, policy, identity, logging, DNS, routing and remote state. A custom networking module is not a substitute for that work.

## Optional real Azure rehearsal

Real deployment is manual and was not performed as part of this package. It requires Azure CLI, a selected disposable subscription, and permissions to manage resource groups and networking. The provider deliberately disables automatic resource-provider registration; an administrator must register `Microsoft.Network` in advance.

In PowerShell:

```powershell
az login
$subscription = az account show --query id -o tsv
if ($LASTEXITCODE -ne 0 -or -not $subscription) { throw 'Select an Azure subscription first.' }
$env:ARM_SUBSCRIPTION_ID = $subscription.Trim()
az account show --query '{subscription:name,id:id}' -o table
terraform init
terraform plan -out=lab.tfplan
terraform show lab.tfplan
terraform apply lab.tfplan
```

Before apply, confirm the subscription and allocation, review the plan and current Azure pricing. Peering traffic can incur charges; lack of compute is not a promise of zero cost. Treat state and plan files as sensitive and keep them out of Git.

For a team workflow, bootstrap an Azure Storage backend independently, give the deployment identity only required access, use OIDC with environment-bound trust and protected deployment approval, and keep untrusted PR validation credential-free. That workflow is a documented extension, not an included deployment.

## Teardown

From the same checkout, state and selected subscription, run `terraform plan -destroy -out=destroy.tfplan`, inspect it with `terraform show destroy.tfplan`, then `terraform apply destroy.tfplan`. Confirm the resource group is gone. Preserve state until deletion is verified; then remove local plan/state copies according to your retention policy. Do not delete a shared state backend as part of workload teardown.
