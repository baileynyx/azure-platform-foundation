# Review Terraform changes before deployment

The plan review gate reads saved-plan JSON, identifies deletions and replacements,
and produces a Markdown report with resource addresses, action order and concrete
review prompts. [Open the generated destructive example](plan-review-example.md)
or inspect [the implementation](../plan_review.py).

This is a narrow action policy. It does not certify a plan as safe, authorize an
apply or provide a deployment approval system. The existing Azure workflow still
has no deployment identity or automatic apply step.

## Try the examples

From the repository root with Python 3.11 or later; no Python packages or Azure
credentials are required:

```shell
python -m unittest discover -s tests -p 'test_*.py' -v
python plan_review.py examples/plans/safe.json --output reports/plan-review/safe.md
python plan_review.py examples/plans/destructive.json --output reports/plan-review/destructive.md
```

The final command deliberately exits 1. Its report lists one deletion and two
replacements requiring review. Both replacement orders are flagged, including
create-before-destroy. The [fixtures](../examples/plans/README.md) are synthetic
action examples, not live Azure plans or a promise of provider behavior.

| Exit | Result | How automation should treat it |
| --- | --- | --- |
| 0 | No destructive changes found | This particular policy passed; other checks and approvals still apply. |
| 1 | Review required | Stop automatic progression and inspect the identified changes. |
| 2 | Invalid or unsupported plan, input/output error | Stop; resolve the error before treating any report as valid. |

These codes belong to the reviewer and are different from Terraform's
`plan -detailed-exitcode` convention. The reviewer never invokes Terraform itself.

## Use an existing saved plan

Generate the JSON from the exact saved plan intended for review. For an already
created `lab.tfplan`, the following PowerShell commands keep the output UTF-8:

```powershell
$planJson = terraform show -json lab.tfplan
if ($LASTEXITCODE -ne 0) { throw 'Terraform could not export the saved plan.' }
$jsonPath = Join-Path (Get-Location) 'runtime/plan-review-input.json'
New-Item -ItemType Directory -Force runtime | Out-Null
[System.IO.File]::WriteAllText($jsonPath, ($planJson -join "`n"), [System.Text.UTF8Encoding]::new($false))
python plan_review.py $jsonPath --output reports/plan-review/current.md
$reviewExit = $LASTEXITCODE
if ($reviewExit -eq 1) { throw 'Review required. Inspect reports/plan-review/current.md.' }
if ($reviewExit -ne 0) { throw 'Plan review could not complete.' }
```

This stops after review. The report includes a SHA-256 of the exact JSON bytes for
traceability; it does not bind a later apply to the binary plan. A deployment
workflow must preserve the reviewed plan, verify its provenance and identity, and
enforce its own approval controls. Do not re-plan silently between review and apply.

Real plan JSON can contain sensitive values. The report intentionally omits
before/after attributes, variables, outputs and free-form provider reasons, but
resource addresses can still reveal infrastructure names. Keep real inputs in
ignored local storage; the public CI artifacts use synthetic inputs only.

## Decisions covered by the policy

Deletion prompts review of dependents, retained data and recovery. A replacement
also identifies action order: destroy-first may interrupt service, while
create-first still requires cutover and capacity review. Data-source removals are
flagged conservatively without claiming they destroy managed infrastructure.

The gate accepts known create, read, update and no-op actions. It rejects unknown
action combinations, malformed consumed fields, duplicate JSON keys, duplicate
resource identities and unsupported format major versions. State exports are
rejected. A current and a deposed object may legitimately share an address and are
reported separately. Explicitly incomplete plans or nonempty deferred changes
require review; errored plans are invalid.

Missing `resource_changes` is allowed for empty or output-only plans when the
required plan envelope is present. New minor-version properties are ignored.
This is consumed-field validation, not a complete schema validator or protection
against a forged or deliberately truncated JSON document.

The interface follows [HashiCorp's saved-plan JSON format](https://developer.hashicorp.com/terraform/internals/json-format).
This version supports its documented basic action combinations; newer actions
such as state-forgetting are rejected until explicitly reviewed and supported.

## CI evidence

The `plan-review` job runs 19 Python tests, checks that synthetic safe/destructive
fixtures return exactly 0/1, and publishes their reports in the run summary. It
then runs `python check_plan_contract.py` against Terraform 1.9.8.

That integration script creates a built-in `terraform_data` fixture in a temporary
directory, saves a real create plan and applies it to local state. It then saves
no-op, replacement and destroy plans, checking the public review CLI and expected
action counts for all four scenarios. Replacement and destroy are planned only.
It never loads this lab's Azure configuration or executes provisioners. The
temporary configuration, plans and state are removed afterward.

The `terraform-plan-review-…` artifact contains Markdown reports and a JSON
integration summary, retained 14 days. A report upload alone does not mean the
checks passed: inspect job conclusions and the exact source commit. The separate
`validate` job retains the existing 17 Terraform mock tests.

The first hosted result for this increment is recorded in the PR checks; consult
[VALIDATION.md](../VALIDATION.md) for the distinction between local and hosted work.

## Practical limits

An in-place change can still break routing, permissions or availability. This gate
does not inspect attribute-level changes, costs, resource drift, output changes,
Terraform check results, unknown values or Azure connectivity. It is not a
replacement for reviewing the full plan. No Azure plan/apply or live network test
was performed for this feature. Input is limited to 10 MiB; report writes are
atomic, and the input path cannot be used as the output path. Always check the
current process exit code rather than trusting a report left by an earlier run.
