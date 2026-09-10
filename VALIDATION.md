# Validation

## Local drift rehearsal

September 10, 2026: all **27 Python tests** passed locally (19 plan-review tests
and 8 drift-rehearsal boundary tests). The new tests reject configuration-only
changes masquerading as drift, Terraform error exit 1, unexpected recovery
actions/resources/paths/content, unknown values, unsupported or errored plans,
and reuse of an existing evidence directory.

The local full rehearsal attempt stopped when the runtime could not start the
local provider process; it did not produce a passing rehearsal report. The
hosted `drift-rehearsal` job is configured to execute actual Terraform detection
and recovery with Terraform 1.9.8 and the locked local provider 2.5.3. Its two
modes must be checked on the PR's exact commit before claiming hosted success.

Expected assertions include observed drift separate from planned actions,
unchanged persisted state/file during detection, fixture-specific recovery
checks, restored bytes, a clean plan and verified Terraform teardown. Reports
contain selected evidence and hashes, while full plans/state remain temporary.
See the [walkthrough, expected results and scope](docs/drift-rehearsal.md).

## Terraform plan review increment

Local Python validation passed **19 tests** for the new action reviewer. They
cover deletion, both replacement orders, safe actions, invalid/unsupported input,
incomplete and deferred plans, deposed objects, omission of sensitive attribute
values, Markdown escaping and public CLI exit codes/report behavior.

The synthetic examples return 0 for no destructive actions and 1 for one deletion
plus two replacements. The committed sample report is generated from that fixture.
Terraform is unavailable in the local preparation environment, so no local
Terraform execution is claimed for this increment.

CI runs the existing 17 Terraform mock tests and a separate plan-review job. Its
real Terraform contract check uses built-in `terraform_data` in temporary local
state for create/no-op/replace/destroy plans. Inspect the exact PR run before
claiming that hosted check passed. It does not access Azure or run a live network
test. [Walkthrough and limits](docs/plan-review.md).

## Optional second-team increment

The implementation adds 12 plan-only mock runs in `tests/two_teams.tftest.hcl`, alongside the five original runs. They exercise default-off behavior, onboarding without changing Team A/hub configuration, separate owner tags, the shared deny baseline, both peerings, an alternate allocation, disabling Team B, and invalid owner/allocation inputs.

September 9, 2026: [hosted validation of the second-team implementation](https://github.com/baileynyx/azure-platform-foundation/actions/runs/34382938050) passed for source commit `15d30520adfc3f73e1893536cee9baefaae4f0a9`. Formatting, locked provider initialization and `terraform validate` passed; `terraform test` reported **17 passed, 0 failed**. The original five-test result below applies to the earlier baseline. No Azure plan/apply or live network test has been performed.

## Original baseline

September 9, 2026: the [first hosted Terraform validation run](https://github.com/baileynyx/azure-platform-foundation/actions/runs/34357895861) passed for source commit `20eb4cf1372a8f27eafb9ebf69f1a1d30e96718e`.

- Terraform 1.9.8 formatting check: passed.
- Initialization with the committed AzureRM 4.81.0 lock file: passed.
- Provider-backed `terraform validate`: passed.
- `terraform test`: **5 passed, 0 failed**.

The five mock runs cover the network/ownership/peering contract, invalid environment, invalid owner, invalid CIDR allocation and the child module's inbound security contract.

Local preparation had been blocked by the runtime's provider socket restriction. The hosted runner resolved that environment limitation without changing the implementation.

These are schema and mocked configuration checks. No Azure subscription was accessed, and no live plan, apply, packet-flow test or teardown was performed.
