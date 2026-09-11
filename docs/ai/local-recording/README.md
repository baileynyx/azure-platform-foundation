# Local Ollama review: captured run

[Read the original transcript](evidence/transcript.txt) ·
[Open the rendered review](evidence/review/review.md) ·
[Inspect the timed recording](evidence/demo.cast) ·
[Run it yourself](../../ollama-recording.md)

On September 11, 2026, one local `qwen2.5:3b` review of the synthetic destructive
Terraform fixture passed the response contract. The model supplied questions for
all four resources, including the unchanged resource. The deterministic policy
returned **`review_required`**, and the recorder retained the original output.

This page describes one submitted live attempt. The separate
[12-case local evaluation](../local-evaluation/README.md) measures a different run;
its totals must not be combined with this recording into a success-rate claim.

## What the review demonstrates

The two replacement orders need different questions. The saved response includes
cutover for create-before-delete and interruption for delete-before-create, with
recovery for both. Local code checked resource coverage, echoed facts and question
constraints before rendering the report. Model-selected question IDs are below;
the [original report](evidence/review/review.md) supplies their full wording.

| Evidence | Synthetic action | Questions, in recorded order |
| --- | --- | --- |
| R001 | `create -> delete` | cutover, dependencies, recovery, verification |
| R002 | `no-op` | dependencies, verification |
| R003 | `delete` | dependencies, recovery, verification |
| R004 | `delete -> create` | dependencies, interruption, recovery, verification |

Review exit **1** means human review is required for this destructive fixture.
Recorder exit **0**, reported in the submitted console output, means capture and
saved-report checks succeeded. The retained metadata independently records
`status: passed` and `review_exit: 1`; it does not store the recorder's exit code.
Neither exit code authorizes an apply.

## Recorded measurements

| Observation | Recorded value |
| --- | --- |
| Started (UTC) | 2026-09-11 07:50:11.663741 |
| Complete child CLI wall time | **60.203 seconds** |
| Chat request latency | **60.047 seconds** |
| Recording duration | **60.375 seconds** |
| Prompt tokens | 1,432 |
| Completion tokens | 256 |
| Total tokens | **1,688** |
| Model | `qwen2.5:3b` |
| Request version | `ollama-review-v3` |
| Options | temperature 0; seed 42; context 8,192; output limit 2,048 |

The [recording metadata](evidence/recording.json) and
[structured review](evidence/review/review.json) contain the same provider
observations, including server-reported timings and manifest digest. CLI wall time
includes work outside the chat request. This is one four-resource plan; its
latency is not directly comparable to the earlier evaluation's per-case average.

The asciicast keeps the actual wait before the CLI output appears. It contains
labelled walkthrough text and buffered subprocess output, not token streaming or
a desktop video. No timing compression or edits were applied. GitHub can display
the transcript and render the Markdown report; the `.cast` file needs a compatible
player for timed playback. Pause playback to read the report.

## Environment and source identity

| Observation | Value and scope |
| --- | --- |
| Python | **3.11.9**, as recorded on the laptop. Repository documentation and CI target **3.12+**; this successful attempt does not establish general 3.11 support. |
| OS fields | `system: Windows`, `release: 10`, `version: 10.0.26200`, `machine: AMD64`; quoted as reported by Python. |
| Laptop | User-reported Intel Core i7-1185G7 at 3.00 GHz and 16 GB RAM; not measured by the recorder. |
| Git commit | [`978b277a7655f3c15775c894d5a7761614b6215b`](https://github.com/baileynyx/azure-platform-foundation/commit/978b277a7655f3c15775c894d5a7761614b6215b) |
| Working tree | Recorder reported `dirty: false`. |
| Ollama application version | Not collected in this capture. Earlier setup reported 0.34.0; it is not re-established by these files. |

GPU utilization and peak memory were not recorded, so the run is not labelled
CPU-only. Use Python 3.12+ for the documented reproduction path. The preflight
manifest digest was
`357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.
That is a local daemon observation, not cryptographic proof of the executing
weights. Source hashes likewise identify file bytes, not execution provenance.

## Evidence validation

The seven files under [evidence/](evidence/) were extracted from the submitted
ZIP and retained byte for byte, including their original line endings. The
directory's Git attributes disable newline conversion for these files so their
recorded hashes survive a checkout.

Before publication, the following checks passed without calling a model:

- All **six artifact hashes** listed in `recording.json` matched the retained
  files. The metadata itself is the seventh file and has no self-hash.
- All **four source hashes** matched the stated Git commit when its source files
  were represented with Windows CRLF line endings. The plan's original byte hash
  also matched the source fixture hash.
- The fixed synthetic plan matched the recorder's pinned fixture. The saved
  candidate passed the source revision's unchanged validator for all four IDs.
- Recomputed policy, evidence mapping and outbound projection matched the saved
  report. The original Markdown matched the validated report renderer after
  newline normalization for comparison only.
- Concatenated cast output matched the transcript; event times were ordered and
  within the recorded duration. Token totals and provider metadata agreed across
  the recording and review.

The uploaded ZIP was named
`ollama-demo-ceec841c5bb74f67b61bacc763baf379.zip`; its SHA-256 was
`0e54704ed927567e3dab09bfc7b4ae8c47d72a5c5f8f080cb86f9fdbc4ab8246`.
The retained `recording.json` SHA-256 is
`38bc1156f7a995f7e489c92e9c038cbcb257ff08007c6ee936c26911820ad709`.
The ZIP container is not duplicated here; the original seven extracted files are.

These checks establish internal consistency and agreement with the stated source.
The evidence is unsigned and user-supplied, so they do not independently attest
that inference occurred. The synthetic fixture contains no real infrastructure
attributes or credentials. No Azure deployment, review time savings, broad model
accuracy or production readiness is established by this capture.
