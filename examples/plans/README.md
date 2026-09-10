# Synthetic plan review examples

These are hand-authored, reduced Terraform plan JSON fixtures, not exported Azure
plans. They include the envelope and action fields consumed by `plan_review.py`.
Resource addresses reflect this lab's hub, Team A and optional Team B modules.

- `safe.json`: no-op hub, new Team B VNet and an in-place Team A NSG update.
  Expected exit 0 means no destructive action was found; an NSG update still
  requires review of its actual rules and traffic impact.
- `destructive.json`: one Team B subnet deletion and two replacement orders,
  plus an unchanged hub. Expected exit 1 and three resource objects requiring review.

The destructive example is a policy exercise, not a prediction of the exact plan
AzureRM would generate for an allocation change. Before/after values are omitted.
Do not replace these files with real plans or state exports.

`check_plan_contract.py` separately tests actual Terraform-generated JSON for
creation, no-op, replacement and destruction using built-in `terraform_data`.
It creates temporary local state only; no Azure resources or credentials are used.
