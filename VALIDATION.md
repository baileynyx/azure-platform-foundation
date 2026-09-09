# Validation

## Optional second-team increment

The implementation adds 12 plan-only mock runs in `tests/two_teams.tftest.hcl`, alongside the five original runs. They exercise default-off behavior, onboarding without changing Team A/hub configuration, separate owner tags, the shared deny baseline, both peerings, an alternate allocation, disabling Team B, and invalid owner/allocation inputs.

Local Terraform formatting passed. Hosted execution for this increment is pending; the original five-test result below applies to the earlier baseline only. No Azure plan/apply or live network test has been performed.

## Original baseline

September 9, 2026: the [first hosted Terraform validation run](https://github.com/baileynyx/azure-platform-foundation/actions/runs/34357895861) passed for source commit `20eb4cf1372a8f27eafb9ebf69f1a1d30e96718e`.

- Terraform 1.9.8 formatting check: passed.
- Initialization with the committed AzureRM 4.81.0 lock file: passed.
- Provider-backed `terraform validate`: passed.
- `terraform test`: **5 passed, 0 failed**.

The five mock runs cover the network/ownership/peering contract, invalid environment, invalid owner, invalid CIDR allocation and the child module's inbound security contract.

Local preparation had been blocked by the runtime's provider socket restriction. The hosted runner resolved that environment limitation without changing the implementation.

These are schema and mocked configuration checks. No Azure subscription was accessed, and no live plan, apply, packet-flow test or teardown was performed.
