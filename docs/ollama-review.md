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
an offline baseline. No live local evaluation result is claimed yet.

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
unknown-value status. The request adds only the fixed instructions, question
catalogue and response schema. Full plans, values and resource names are never
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

## Adapter contract

The implementation uses the documented [installed-model list](https://docs.ollama.com/api/tags)
and [native chat API](https://docs.ollama.com/api/chat), with a JSON schema supplied
through `format` and streaming disabled. Only `qwen2.5:3b` and `qwen2.5:1.5b` are
accepted. Remote endpoint overrides, proxies, redirects and automatic pulls are
not supported; Azure credentials are never attached. The model must be installed
and report a valid manifest digest. Explicit remote-model metadata is rejected.
The local daemon remains a trusted component; this is not a sandbox for an
untrusted Ollama installation.

Malformed or oversized responses, refusals, tool calls, wrong model names,
incomplete generation, missing usage/timings and evidence-contract violations
all fail closed. Response bodies and network exception details are not printed.
CI tests this transport on Windows and Linux without loading a model.
