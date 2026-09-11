# Run the Terraform reviewer locally with Ollama

This path runs a small language model on your own computer. No Azure subscription,
API key or Terraform deployment is needed. It exercises the same evidence checks,
question catalogue and deterministic action policy as the Azure adapter.

An Intel i7-1185G7 with 16 GB RAM is a reasonable machine to try the 3-billion-
parameter model below. CPU inference may be slow; actual memory use, latency and
contract success must be measured on the machine. Close memory-heavy applications
first. Do not install Kubernetes or a container stack for this demo.

**Evidence status:** automated tests intercept HTTP and use synthetic responses.
They do not run Ollama or establish model quality. The committed recording remains
an offline baseline. A user-run review of the destructive fixture on Ollama 0.34.0
with `qwen2.5:3b` returned JSON but failed the question contract: it added
`interruption` to the create-before-delete resource and used `cutover` instead of
`interruption` for the delete-before-create resource. The validator rejected both
errors. A subsequent attempt failed with `Response omits resource evidence.`
The exact omitted IDs were not captured. A later v3 run passed all 12 synthetic
cases; the [results case study](ai/local-evaluation/README.md) preserves the original
evaluation JSON, measurements and limitations.

## 1. Install and start Ollama on Windows

Download and run the installer from [Ollama for Windows](https://ollama.com/download/windows).
The [Windows documentation](https://docs.ollama.com/windows) lists supported Windows
versions and installation requirements. Allow several GB of free space for the
application and model. No separate GPU is required to attempt CPU inference.

Open a new PowerShell window. Copy only the command inside each block, one block
at a time. Do not paste the `PS C:\...>` prompt or error output as commands.

```powershell
ollama --version
```

Disable cloud features persistently for your Windows user:

```powershell
[Environment]::SetEnvironmentVariable('OLLAMA_NO_CLOUD', '1', 'User')
```

Quit Ollama from its system-tray menu and reopen it from the Start menu so the
server reads that setting. See the [official cloud-disable instructions](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).
The reviewer connects only to `127.0.0.1:11434`, but that alone cannot prevent a
separately configured daemon from forwarding requests. Use the standard local
installation and leave its default loopback binding in place.

Download the starting model explicitly:

```powershell
ollama pull qwen2.5:3b
```

The [published model](https://ollama.com/library/qwen2.5:3b) is approximately 1.9 GB
with Q4_K_M quantization at the time of writing. Pulling requires internet access;
the reviewer never downloads models. Tags can change, so each successful review
records the installed manifest digest reported by Ollama.

```powershell
ollama list
```

Confirm `qwen2.5:3b` appears before continuing.

## 2. Run one synthetic plan

Open PowerShell in your updated `azure-platform-foundation` checkout, in the
folder containing `ai_review.py`. Use Python 3.12 or later:

```powershell
python --version
```

Confirm the checkout includes the current schema revision before running a model:

```powershell
python -c "import ai_review; print(ai_review.OLLAMA_REQUEST_VERSION)"
```

Expected: `ollama-review-v3`. If it differs, update the checkout first.

Select the model for this PowerShell session:

```powershell
$env:OLLAMA_MODEL = 'qwen2.5:3b'
```

Choose a fresh output directory:

```powershell
$reviewRun = 'reports/ai-ollama-' + [Guid]::NewGuid().ToString('N')
```

```powershell
python ai_review.py examples/plans/destructive.json --provider ollama --output-dir $reviewRun
```

The first call loads model weights and may take longer. The adapter permits a
180-second socket timeout for chat. Wait for the command to finish. Then check
its exit code before running another external command:

```powershell
$LASTEXITCODE
```

For this destructive fixture, **1 is the expected result**: the original action
policy still requires human review. Exit 2 means the provider, response contract
or file operation failed; it is not a successful review. Exit 0 would be unexpected
for this fixture. For other plans, 0 only means this narrow policy found no
destructive actions, never permission to apply.

If the command produced the expected result:

```powershell
Get-Content (Join-Path $reviewRun 'review.md')
```

```powershell
Get-Content (Join-Path $reviewRun 'review.json')
```

The JSON includes the local input hash, checked candidate, model name, installed
manifest digest, generation options, measured chat latency, and server-reported
token counts and nanosecond timings. The digest is a preflight observation from
the local server, not cryptographic proof of which weights produced a response.
Do not replace or pull the model during a run. Temperature 0 and a fixed seed help
comparison but do not guarantee identical results across versions or hardware.

`outbound.json` is the plan-derived projection: aliases, action enums, mode and
unknown-value status. The request adds the fixed instructions, question catalogue, response schema,
request version and per-resource allowed/required question IDs derived from the
existing deterministic rules. These constraints add no raw plan strings. Full plans, values and resource names are never
sent to the model. Local review files do contain resource addresses; use only
synthetic plans for public portfolio evidence.

## 3. Evaluate all 12 synthetic cases

After the single review works, reserve a new output name:

```powershell
$evaluationRun = 'reports/ai-ollama-eval-' + [Guid]::NewGuid().ToString('N')
```

```powershell
python evaluate_ai_review.py --provider ollama --output-dir $evaluationRun
```

This attempts one local chat per case, plus an installed-model preflight for each
case. It does not retry failures. On a CPU, the full run can take several minutes;
if every chat times out, the socket waits alone can approach 36 minutes. Stop with
Ctrl+C if necessary; interrupted runs do not produce a completed evaluation report.

```powershell
$LASTEXITCODE
```

Evaluation exit 0 means all 12 corpus contracts and 13 separately constructed
adversarial validator probes passed. Exit 1 means at least one failed; exit 2 means
an evaluation setup error. These evaluation codes differ from the single-plan
review-required code above.

```powershell
Get-Content (Join-Path $evaluationRun 'evaluation.md')
```

`evaluation.json` retains candidates, model metadata and measurements for accepted
responses. Failures stay in the denominator. Token totals cover accepted responses
only; failed or rejected responses may also have consumed compute. The 13 probes
are deliberately corrupted test responses, not model-generated attack results.
The corpus is small and public; passing does not prove operational benefit.

For portfolio evidence, retain the full synthetic evaluation JSON, including any
failures, alongside your CPU/RAM, Windows version, `ollama --version`, repository
commit (`git rev-parse HEAD`) and a short explanation of what was measured. Reports
are ignored by Git; review them before choosing to publish any results.

## Troubleshooting and cleanup

To capture a portfolio walkthrough after the single review works, follow
[Record a local AI review walkthrough](ollama-recording.md). The separate recorder
retains a transcript, timed terminal recording, original reports and attempt
metadata. It preserves failures and uses a new output directory for every attempt.

- **Command not found:** reopen PowerShell after installing Ollama; verify it is
  available before copying the next command.
- **Local inference failed:** open Ollama, check `ollama list`, close memory-heavy
  applications and try one synthetic review again with a new output directory.
  The socket timeout is not a performance target or guaranteed total deadline.
- **Selected model is not installed:** run the matching pull command explicitly.
- **Response rejected:** preserve the failure. A small model can produce valid
  JSON that violates the evidence or required-question rules. The adapter does
  not relax checks or silently substitute a baseline answer.
- **Output directory already exists:** generate a new run name. Existing reports
  are never overwritten and an existing directory prevents inference.

If memory or latency is a problem, the only alternate model supported in this
increment is the smaller `qwen2.5:1.5b`. Its contract success may differ. Run these
commands separately, then repeat the single review with a new output directory:

```powershell
ollama stop qwen2.5:3b
```

```powershell
ollama pull qwen2.5:1.5b
```

```powershell
$env:OLLAMA_MODEL = 'qwen2.5:1.5b'
```

To release memory after either model:

```powershell
ollama stop $env:OLLAMA_MODEL
```

The request uses an 8,192-token context, a 2,048-token output limit, temperature 0,
seed 42 and a five-minute keep-alive. Large plans may exhaust these limits or the
timeout even within the existing 20-resource input cap. Truncation is rejected.
No weights or installer are redistributed in this repository.

## Revised request after the first local failure

The local request now includes a separate `question_constraints` entry for each
evidence ID. It lists exactly which questions are allowed and which are mandatory.
The instructions tell the model to follow the matching entry and never transfer
replacement questions between resources. Unknown-value and data-source rules come
from the same validator policy. No candidate is automatically repaired, no failure
is retried, and no validation rule is relaxed.

That instruction change was version `ollama-review-v2`. After the subsequent
coverage failure, version `ollama-review-v3` changes the native response schema:
`findings` is now an object with a required property for every input evidence ID,
including unchanged resources. Each value still contains the model-echoed
`evidence_id`, `category`, `unknown_values` and `questions`. The schema restricts
echoed facts to their expected enums and question IDs to that resource's allowed
list. Mandatory question membership and uniqueness remain application checks.

The adapter checks the exact set of keys and each echoed identity before
converting values into the existing report array in evidence order. It never
fills missing entries, removes extra entries or repairs questions or facts.
Duplicate JSON keys are rejected before conversion. Zero-resource plans require
an empty findings object. Public reports, replay format and the Azure response
format remain arrays.

Successful local reports record `ollama-review-v3` in provider metadata.
Regression tests reject both earlier question mistakes and each possible omitted
resource in the destructive fixture. Round-trip tests cover all 12 synthetic
cases, including empty evidence, without changing model question order. These
intercepted tests establish adapter behavior. A subsequent single-plan run
returned the expected exit 1, followed by the successful 12-case run linked above.
For a new installation, start with the single synthetic plan before the full
corpus; a successful review of this destructive fixture returns exit 1.

## Adapter contract

The implementation uses the documented [installed-model list](https://docs.ollama.com/api/tags)
and [native chat API](https://docs.ollama.com/api/chat), with a JSON schema supplied
through `format` and streaming disabled. The per-plan schema follows Ollama's
[structured-output guidance](https://docs.ollama.com/capabilities/structured-outputs)
and is also included in the prompt. Only `qwen2.5:3b` and `qwen2.5:1.5b` are
accepted. Remote endpoint overrides, proxies, redirects and automatic pulls are
not supported; Azure credentials are never attached. The model must be installed
and report a valid manifest digest. Explicit remote-model metadata is rejected.
The local daemon remains a trusted component; this is not a sandbox for an
untrusted Ollama installation.

Malformed or oversized responses, refusals, tool calls, wrong model names,
incomplete generation, missing usage/timings and evidence-contract violations
all fail closed. Response bodies and network exception details are not printed.
CI tests this transport on Windows and Linux without loading a model.
