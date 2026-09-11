# Local AI review: turning rejected responses into checked evidence

One local Qwen 2.5 3B evaluation passed all **12 synthetic cases** with the
`ollama-review-v3` request. The run recorded **8,946 tokens** and **160.656 seconds
of combined chat latency**. Before this result, real attempts exposed incorrect
replacement questions and omitted resources. Those failures drove changes to the
request and generation schema while the deterministic policy stayed authoritative.

[Inspect the original evaluation JSON](evaluation.json) or
[run the Windows walkthrough](../../ollama-review.md).

## Problem and engineering decisions

The project adds a bounded AI question selector to a Terraform action reviewer.
A local adapter made the experiment possible without an Azure subscription. The
model receives generated evidence IDs, action metadata and a fixed catalogue;
resource names, attribute values and full plans stay outside the model request.
Local code writes factual explanations and decides whether review is required.

| Observed behavior | Change | Boundary retained |
| --- | --- | --- |
| The initial local response mixed up replacement order: R001 included interruption for create-before-delete; R004 chose cutover and omitted interruption for delete-before-create. | [PR #11](https://github.com/baileynyx/azure-platform-foundation/pull/11) supplied explicit allowed and mandatory question IDs for each resource, revision v2. | Irrelevant and missing mandatory questions still cause exit 2. |
| A subsequent attempt failed with omitted resource evidence. The omitted IDs were not captured. | [PR #12](https://github.com/baileynyx/azure-platform-foundation/pull/12) changed native findings to an object with a required property for every evidence ID, revision v3. Fact enums and allowed question IDs are specific to each resource. | Exact coverage and identity are checked before conversion to the public report array; no entries or facts are repaired. |
| A later destructive-plan review returned `review_required; exit=1`, followed by this passing evaluation. | Preserve the submitted JSON and independently validate its candidates and totals. | A successful AI response cannot authorize Terraform apply. |

The earlier failures and single-plan success were observed in submitted console
output. Their full reports and timings are not included here. This is an iteration
history, not a controlled comparison of model accuracy between revisions.

## Measured results

| Measure | Recorded result |
| --- | ---: |
| Live responses accepted against the corpus contract | 12 / 12 |
| Cases containing resource evidence | 9 |
| Cases with no resource evidence | 3 |
| Separate adversarial validator probes rejected | 13 / 13 |
| Prompt / completion tokens | 8,292 / 654 |
| Total tokens | 8,946 |
| Sum of per-request chat latency | 160.656 s |
| Median chat latency, all 12 cases | 15.891 s |
| Mean chat latency, 9 resource-bearing cases | 17.026 s |
| Latency range, 9 resource-bearing cases | 14.360–22.375 s |

The three empty-evidence cases are incomplete, deferred and output-only plans.
They legitimately return empty findings; separate deterministic policy warnings
still apply. Their shorter responses lower the all-case average to 13.388 seconds.
The latency sum excludes model-list preflights and other program overhead; it is
not a measurement of total evaluation wall time or human review time.

| Case | Contract | Chat latency (s) |
| --- | --- | ---: |
| create | Passed | 22.375 |
| update | Passed | 17.140 |
| delete | Passed | 14.360 |
| replace_unknown | Passed | 16.188 |
| create_before_destroy | Passed | 17.265 |
| data_read | Passed | 15.656 |
| data_removal | Passed | 15.282 |
| no_op | Passed | 16.125 |
| incomplete | Passed; empty evidence | 5.703 |
| deferred | Passed; empty evidence | 0.860 |
| output_only | Passed; empty evidence | 0.859 |
| injection_and_secrets | Passed | 18.843 |

Both replacement orders include their mandatory questions in this run. The
injection fixture tests that raw secret/instruction strings are excluded from
the projection; it does not demonstrate resistance to arbitrary prompt injection.
The 13 adversarial probes use deliberately corrupted responses to exercise the
validator. They are not 13 attacks generated or resisted by Qwen.

## Environment and provenance

| Item | Evidence |
| --- | --- |
| Host | User-reported Intel Core i7-1185G7 at 3.00 GHz, 16 GB RAM |
| Operating environment | Windows PowerShell; exact Windows build and Python version were not captured |
| Ollama | Version 0.34.0 from the setup console output |
| Model | `qwen2.5:3b`; the setup model listing reported a 1.9 GB download |
| Request revision | `ollama-review-v3` in every observation |
| Generation settings | Temperature 0; seed 42; context 8,192; output limit 2,048 tokens |
| Execution device and peak memory | Not captured; these measurements must not be labelled CPU-only benchmarks |

Ollama reported the same installed manifest digest for every case:

```text
357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b
```

The uploaded file is preserved byte for byte, including its Windows line endings.
Its SHA-256 is:

```text
762339c53437f06ffd1b7e757387c45d7128e81cbff3be3255446977137986a7
```

All saved candidates were independently checked against the repository's
[labelled corpus](../../../examples/ai/evaluation-cases.json) and evidence rules.
Case names, policy/unknown-value expectations, question constraints, probe results
and token totals agree. This checks the report's content and internal consistency;
it does not independently attest execution on the host. The model digest is also
a server-reported preflight observation, not a signature over generated output.

The reference implementation is [PR #12's source commit](https://github.com/baileynyx/azure-platform-foundation/commit/006eb05bf572a514a37591bc927e9275ae2c4fbb).
The evaluation file does not capture a local Git commit, run timestamp, or software
inventory, so exact host revision and timing provenance cannot be reconstructed
from it. Request v3 is recorded explicitly.

## Reproduce the exercise

Follow the [Windows setup and evaluation steps](../../ollama-review.md). Use a
fresh output directory and retain the complete result, including failures. A new
run should record its Git commit, Python/Ollama versions, device allocation and
peak memory as well as the existing model metadata. Keep real plan reports private.

To verify this committed evidence file from the repository root:

```powershell
# Hash the original JSON bytes without reformatting or rewriting the file.
Get-FileHash -Algorithm SHA256 -LiteralPath 'docs/ai/local-evaluation/evaluation.json'
```

This small, public corpus has been used during development. One successful run
supports contract compliance under the recorded settings, not a general accuracy
score. Constrained generation supplies exact facts and limits the model's choices;
it does not establish independent infrastructure reasoning. Repeated runs, unseen
cases and a blinded comparison with the deterministic question baseline would be
needed to assess reliability and reviewer benefit. No Azure deployment, production
readiness, cost saving or time-saving claim follows from these results.
