# Validation

September 9, 2026:

- Terraform 1.9.8 formatting check passed for all configuration and test files.
- `terraform init -backend=false -input=false` installed AzureRM 4.81.0 and generated the committed dependency lock file. Terraform reported the provider signed by HashiCorp.
- `terraform validate` could not load the provider schema because this runtime denied the provider's local Unix socket creation. This is an environment limitation, not a successful validation result.
- Five mock test runs are supplied: network/ownership/peering contract, invalid environment, invalid owner, invalid CIDR allocation and child-module inbound security contract. They have **not been executed** because the provider cannot start in this runtime.

The workflow is configured to initialize, validate and run the tests in GitHub Actions. Its first successful hosted run is still required. No Azure subscription was accessed, and no live plan, apply, network test or teardown was performed.
