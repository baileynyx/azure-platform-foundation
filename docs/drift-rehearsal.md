# Detect drift and rehearse recovery

This lab demonstrates a change made outside Terraform, detection without repair,
and an explicitly requested recovery of a disposable local file. It complements
the [plan reviewer](plan-review.md): a planned configuration change and an observed
external change are different evidence.

## Run the full rehearsal

Requires Terraform 1.9 or later (less than 2.0), Python 3.11+, and network access
to install the locked `hashicorp/local` 2.5.3 provider. CI uses Terraform 1.9.8,
Python 3.12 and Ubuntu. No Azure credentials, cloud resources or Python packages
are needed. From the repository root:

```shell
python rehearse_drift.py --recover-local-fixture --output-dir reports/drift-demo
```

The command creates a fresh temporary root from the committed local fixture and
lock file. It never runs the Azure root module. It accepts no configuration,
state, backend or managed-file path from the caller. Use a new report directory
for each run; existing directories are refused.

The shorter command observes drift without recovering it:

```shell
python rehearse_drift.py --output-dir reports/drift-observe
```

Both modes remove their temporary files and state. Detection-only mode leaves
the changed bytes in place until temporary-directory cleanup, so it does not
demonstrate Terraform recovery or Terraform destroy.

## Expected evidence

| Phase | Detailed plan exit | Observation | Planned resource action |
| --- | ---: | --- | --- |
| Initial | 2 | No prior resource | Create the local file |
| Baseline | 0 | File agrees with state/configuration | None |
| Drift | 2 | Provider reports a deleted managed object | None in refresh-only mode |
| Recovery, when requested | 2 | Same observed drift | Create the expected file |
| Clean, after recovery | 0 | Original file bytes restored | None |
| Teardown, after recovery | 2 | No drift | Delete the local file |

The script changes `log_level=info` to `log_level=debug` directly on disk while
leaving the Terraform configuration untouched. The local provider treats a
content hash mismatch as an absent managed object. Thus the `delete` drift action
describes the provider's model; the file still exists on disk. Before/changed/
restored SHA-256 values establish the byte changes independently.

Terraform's detailed plan codes are **0: no changes, 1: error, 2: changes**.
An exit 2 alone does not prove drift. The rehearsal inspects `resource_drift`
separately from `resource_changes` and rejects unexpected results. Its own CLI
returns **0** when every requested assertion passes, or **2** on failure. An
expected Terraform drift exit 2 therefore becomes a successful demonstration.

## Recovery boundary

Detection uses a refresh-only **plan** and verifies that persisted state and the
changed file remain untouched. It does not apply the refresh-only plan.

With `--recover-local-fixture`, a normal saved plan must contain exactly one
create for `local_file.service_config`, at `./service.conf`, with the original
content and `0600` file permissions. Unknown values, extra resources, updates,
deletions and replacements are rejected as recovery proposals. The script checks
the saved plan's hash again before applying those same bytes. It then verifies
the restored contents and a clean plan, followed by a checked destroy plan,
absence of the file and an empty Terraform resource list.

These are automated checks for a fixed synthetic fixture, **not human approval
for production recovery**. Real drift requires an owner to determine whether
the external change was intentional, assess impact and choose either restoration
of the approved configuration or a reviewed configuration/state update. A
refresh-only apply accepts observations into state; it does not restore a resource.

## Reports, CI and limits

Inspect `drift-report.md` and `drift-evidence.json` in the chosen output folder.
Evidence includes the actual Terraform version, per-phase actions and exit codes,
configuration/provider-lock hashes, plan-JSON hashes, file hashes and cleanup
assertions. Hashes identify inputs; they are not signed attestations. Full saved
plans, state and provider command output are not published. A failed run cannot
reuse a previous passing report directory.

The CI job executes both modes, publishes the recovery Markdown in its summary
and retains the two report sets for 14 days. Check the exact commit in the
[workflow history](https://github.com/baileynyx/azure-platform-foundation/actions/workflows/validate.yml).

This is a local provider rehearsal. It does not establish Azure drift detection,
remote state locking, scheduled monitoring, alert delivery, production approval
or safe automated remediation. Run both observation and recovery on the same
machine: a local file absent on a different runner can also appear as drift.

References: [Terraform plan modes and exit codes](https://developer.hashicorp.com/terraform/cli/commands/plan),
[local file provider behavior](https://github.com/hashicorp/terraform-provider-local/blob/v2.5.3/docs/resources/file.md).
