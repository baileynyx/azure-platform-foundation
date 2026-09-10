# Azure OpenAI service for the Terraform reviewer

An isolated Terraform root that provisions three managed resources: a dedicated
resource group, an Azure OpenAI S0 account and one `terraform-reviewer` model
deployment. It supplies the non-secret environment values consumed by
[`ai_review.py`](../../ai_review.py). It does not modify the networking lab or run
inference during apply.

The starting configuration is `eastus2`, GPT-4.1 mini version `2025-04-14`,
`GlobalStandard`, capacity 10. Model, version, location and capacity are inputs.
These are configuration defaults, not a guarantee of capacity in a particular
subscription. GPT-4.1 mini supports chat completions and structured outputs and
is listed as Legacy in Microsoft's current schedule. Confirm availability and
lifecycle before creating a new deployment; choose another compatible explicit
model/version pair if necessary.

## What this configuration does

- Uses a separate local state in this directory and binds the provider to an explicit subscription UUID.
- Allows only your supplied public IPv4 host through the public endpoint firewall; other clients are denied and trusted-service bypass is disabled.
- Enables API-key authentication for the existing reviewer. It exposes no key outputs.
- Pins the model version with `NoAutoUpgrade` and disables dynamic throttling.
- Uses consumption-based `GlobalStandard`, with no provisioned-throughput SKU, compute VM, private endpoint or monitoring workspace.
- Soft-deletes the account on Terraform destroy; it does not automatically purge the account.

**No Azure apply or live inference has been performed for this change.** Mock
tests exercise the installed provider schema and the configuration. They cannot
prove account permissions, quota, regional availability, firewall reachability,
billing or successful model responses.

## Prerequisites

Use PowerShell, Python 3.12+, Terraform 1.9.x and Azure CLI. An active Azure
subscription with billing enabled is required. Your Azure identity needs rights
to create the resource group, Cognitive Services account and deployment and to
list account keys. The `Microsoft.CognitiveServices` resource provider must be
registered. Terraform deliberately does not register providers automatically.

Start from the repository root. This login and preflight block performs reads
and selects the subscription; it does not provision a model:

```powershell
$ErrorActionPreference = 'Stop'
az login
if ($LASTEXITCODE -ne 0) { throw 'Azure sign-in failed.' }
az account list --query '[].{Name:name,Subscription:id,Default:isDefault}' -o table
if ($LASTEXITCODE -ne 0) { throw 'Unable to list subscriptions.' }
$aiSubscription = Read-Host 'Subscription UUID for this demo'
az account set --subscription $aiSubscription
if ($LASTEXITCODE -ne 0) { throw 'Unable to select that subscription.' }
$aiSubscription = az account show --query id -o tsv
if ($LASTEXITCODE -ne 0 -or -not $aiSubscription) { throw 'Unable to verify subscription.' }
$aiSubscription = $aiSubscription.Trim()
$registration = az provider show --namespace Microsoft.CognitiveServices --query registrationState -o tsv
if ($LASTEXITCODE -ne 0 -or $registration.Trim() -ne 'Registered') {
    throw 'An administrator must register Microsoft.CognitiveServices before continuing.'
}
$aiRegion = Read-Host 'Region identifier (press Enter for eastus2)'
if (-not $aiRegion) { $aiRegion = 'eastus2' }
az cognitiveservices model list --location $aiRegion --output json
if ($LASTEXITCODE -ne 0) { throw 'Model catalogue lookup failed.' }
az cognitiveservices usage list --location $aiRegion --output table
if ($LASTEXITCODE -ne 0) { throw 'Quota lookup failed.' }
```

If registration is required, an authorized subscription administrator can run
`az provider register --namespace Microsoft.CognitiveServices --wait`, then rerun
the registration check. This is a subscription-level change, separate from this
Terraform root.

Inspect the catalogue for the selected model/version and a `GlobalStandard` SKU.
Check its lifecycle and available quota as well. A catalogue entry is not proof
of allocatable capacity. If the default is unavailable, change the inputs before
plan. GlobalStandard can process requests outside the account's region.

## Prepare local configuration and review the plan

Continue in the same PowerShell session. This writes an ignored local variable
file containing your subscription and IP, never an API key. It prompts for all
operator-specific values; there are no template tokens to replace:

```powershell
$aiRoot = Join-Path (Get-Location) 'examples/ai-service'
$aiVarsPath = Join-Path $aiRoot 'demo.auto.tfvars.json'
if (Test-Path $aiVarsPath) { throw 'A demo variable file already exists; inspect and edit it instead of overwriting it.' }
$aiPublicIp = Read-Host 'Your public egress IPv4 host (no /32 suffix)'
$aiModel = Read-Host 'Compatible model name (press Enter for gpt-4.1-mini)'
if (-not $aiModel) { $aiModel = 'gpt-4.1-mini' }
$aiVersion = Read-Host 'Explicit model version (press Enter for 2025-04-14)'
if (-not $aiVersion) { $aiVersion = '2025-04-14' }
$aiVars = @{
    subscription_id = $aiSubscription
    operator_ipv4 = $aiPublicIp
    location = $aiRegion
    model = @{ name = $aiModel; version = $aiVersion }
    capacity = 10
}
$aiJson = $aiVars | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText($aiVarsPath, $aiJson, [Text.UTF8Encoding]::new($false))
terraform -chdir=examples/ai-service init -input=false -lockfile=readonly
if ($LASTEXITCODE -ne 0) { throw 'Terraform initialization failed.' }
terraform -chdir=examples/ai-service validate
if ($LASTEXITCODE -ne 0) { throw 'Terraform validation failed.' }
terraform -chdir=examples/ai-service plan -out=demo.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Terraform plan failed.' }
terraform -chdir=examples/ai-service show demo.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the saved plan.' }
```

For a new demo, expect exactly **3 additions**, no changes and no deletions.
Review the subscription, region, model/version, GlobalStandard routing, host
allowlist and capacity. A name conflict can be resolved by setting `name_prefix`
in the local variable file and generating a new plan. Model/version, name or
location changes can cause replacement; inspect later plans as carefully as the
first one.

Terraform plans and state can contain the account's computed API keys even
though outputs do not expose them. Keep this directory's state, backups and plans
private. The repository ignores them. Never upload real plan JSON to CI artifacts
or include it in a public issue. For shared operation, configure a protected
remote backend separately before deploying; this demo intentionally uses local
state for one operator.

## Apply only after reviewing the saved plan

This command creates billable Azure resources. A saved-plan apply does not show
another interactive approval prompt, so run it only after reviewing the plan:

```powershell
terraform -chdir=examples/ai-service apply demo.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Azure deployment failed; inspect Terraform output and retained state.' }
terraform -chdir=examples/ai-service output reviewer_environment
if ($LASTEXITCODE -ne 0) { throw 'Unable to read deployment outputs.' }
```

Capacity is a quota allocation, **not a dollar budget or monthly spending cap**.
Review the current [Azure OpenAI pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/)
for your model before applying or running requests. You can add a cost alert in
Azure, but an alert does not stop spending automatically. The initial test below
makes one inference request. The full corpus evaluation makes twelve and may hit
rate limits at this small capacity; the reviewer does not retry automatically.

## Run one live synthetic review

From the repository root in the same session, use the non-secret Terraform
outputs and fetch a key directly into a process environment variable. The key is
not printed or written to a file. The script restores any previous reviewer
variables when it finishes:

```powershell
$aiConnectionJson = terraform -chdir=examples/ai-service output -json reviewer_environment
if ($LASTEXITCODE -ne 0) { throw 'Unable to read connection outputs.' }
$aiConnection = $aiConnectionJson | ConvertFrom-Json
$aiGroup = terraform -chdir=examples/ai-service output -raw resource_group_name
if ($LASTEXITCODE -ne 0) { throw 'Unable to read resource group output.' }
$aiAccount = terraform -chdir=examples/ai-service output -raw account_name
if ($LASTEXITCODE -ne 0) { throw 'Unable to read account output.' }
# Read the subscription binding from the local config, rather than trusting a
# later change to the Azure CLI default subscription.
$aiConfig = Get-Content 'examples/ai-service/demo.auto.tfvars.json' -Raw | ConvertFrom-Json
$aiPrevious = @{}
foreach ($aiName in @('AZURE_OPENAI_ENDPOINT','AZURE_OPENAI_DEPLOYMENT','AZURE_OPENAI_API_KEY')) {
    $aiPrevious[$aiName] = [Environment]::GetEnvironmentVariable($aiName, 'Process')
}
try {
    $env:AZURE_OPENAI_ENDPOINT = $aiConnection.AZURE_OPENAI_ENDPOINT
    $env:AZURE_OPENAI_DEPLOYMENT = $aiConnection.AZURE_OPENAI_DEPLOYMENT
    $aiKey = az cognitiveservices account keys list --subscription $aiConfig.subscription_id --resource-group $aiGroup --name $aiAccount --query key1 --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or -not $aiKey) { throw 'Unable to retrieve account key.' }
    $env:AZURE_OPENAI_API_KEY = $aiKey.Trim()
    $aiRun = 'reports/ai-live-' + [Guid]::NewGuid().ToString('N')
    python ai_review.py examples/plans/destructive.json --provider azure --output-dir $aiRun
    if ($LASTEXITCODE -ne 1) { throw 'Expected a valid review-required result with exit 1; inspect the diagnostic.' }
    Get-Content (Join-Path $aiRun 'review.md')
} finally {
    $aiKey = $null
    foreach ($aiName in $aiPrevious.Keys) {
        [Environment]::SetEnvironmentVariable($aiName, $aiPrevious[$aiName], 'Process')
    }
}
```

Successful provisioning does not prove inference works. Confirm the resulting
report says `azure`, includes the returned model identifier and measured usage,
and retains the destructive-policy result. Share only the synthetic review
report if you want help validating it, never the key or Terraform state.
If a request fails, check IP/firewall propagation, current public IP, quota,
model/API compatibility and local network access. A public IP change requires a
new reviewed Terraform plan. The firewall does not allow GitHub-hosted runners.

## Tear down the isolated demo

Keep the same state and variable file. From the repository root:

```powershell
terraform -chdir=examples/ai-service plan -destroy -out=destroy.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Destroy planning failed.' }
terraform -chdir=examples/ai-service show destroy.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the destroy plan.' }
```

After confirming that the three demo resources are the only deletion targets:

```powershell
terraform -chdir=examples/ai-service apply destroy.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Teardown failed; keep state and inspect Azure.' }
```

Account soft deletion can reserve the name after destroy. Recreating the same
name may require recovery, a different prefix or an explicit separately reviewed
purge. This root deliberately does not purge automatically. Confirm the live
deployment and resource group are gone before cleaning up local sensitive files.
Never delete state to force Terraform to forget a failed deployment.

## Validation and references

Credential-free configuration checks:

```shell
terraform -chdir=examples/ai-service init -backend=false -input=false -lockfile=readonly
terraform -chdir=examples/ai-service validate
terraform -chdir=examples/ai-service test
```

The 12 Terraform mock runs cover account wiring, firewall/auth, version/capacity,
non-secret outputs, configurable inputs and rejection of unsafe/malformed values.
CI runs these separately from the existing networking and AI application tests.

- [AzureRM account schema](https://registry.terraform.io/providers/hashicorp/azurerm/4.81.0/docs/resources/cognitive_account)
- [AzureRM deployment schema](https://registry.terraform.io/providers/hashicorp/azurerm/4.81.0/docs/resources/cognitive_deployment)
- [Model capabilities](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure)
- [Model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule)
- [Azure CLI model catalogue](https://learn.microsoft.com/en-us/cli/azure/cognitiveservices/model)
- [Azure CLI quota usage](https://learn.microsoft.com/en-us/cli/azure/cognitiveservices/usage)
