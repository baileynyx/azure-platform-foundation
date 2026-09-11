# Record a local AI review walkthrough

Capture one real Ollama review of the committed synthetic destructive plan.
The recorder creates a timed terminal recording, a readable transcript and the
original review files. No screen-recording software or extra Python packages are
required. It runs on Windows or Linux with Python 3.12+ and the existing local
Ollama installation described in [the setup guide](ollama-review.md).

**Evidence status:** this page supplies the recording procedure. A live recording
has not yet been published. CI intercepts subprocesses to test the recorder;
those synthetic test responses are not live inference evidence. The earlier
[12-case local evaluation](ai/local-evaluation/README.md) and
[offline baseline recording](ai/recorded-demo/transcript.txt) remain separate.

## Capture the actual run

Open PowerShell in your updated `azure-platform-foundation` checkout, with
`record_ollama_demo.py` present. Keep Ollama running with cloud features disabled
and `qwen2.5:3b` already installed. Do not pull or replace weights or edit the
source files during the recording. Copy only the contents of each code block.

Run this block once. The output folder is unique, so earlier attempts survive:

```powershell
# Select the installed local model; this does not download or start a model.
$env:OLLAMA_MODEL = 'qwen2.5:3b'
$recordingRun = 'reports/ollama-demo-' + [Guid]::NewGuid().ToString('N')

# Capture the recorder's status immediately, before another native command runs.
python record_ollama_demo.py --output-dir $recordingRun
$recordingExit = $LASTEXITCODE
Write-Output "Recorder exit code: $recordingExit"
Write-Output "Results folder: $recordingRun"
```

The script presents the four resource action sequences, waits for the real model
and shows the validated questions. It uses a checked copy of the fixed synthetic
fixture and cannot select another plan. It does not retry, substitute a baseline,
deploy infrastructure or contact Azure. The reviewer continues to enforce its
local Ollama endpoint and response checks.

| Observed status | Meaning |
| --- | --- |
| Review exit `1`, recorder exit `0`, recording status `passed` | The model response passed validation, and the destructive plan still requires human review. |
| Recorder exit `2` | Setup, provider, report verification or capture failed. An existing folder is never overwritten. |
| Recording status `timeout` | The child review exceeded the recorder's 240-second total limit. It was terminated; this is a failed attempt. |
| Recorder exit `130`, status `interrupted` | Ctrl+C interrupted capture. Retain the partial attempt. |

The recorder's success code differs from the reviewer's expected exit `1`.
The review still requires a person to evaluate the change; neither code approves
a Terraform apply. Once the output folder has been created, ordinary review
failures, timeouts and interrupts retain capture files. Disk failure or forcibly
terminating Python can leave only partial files; check `recording.json` exists.

Inspect the saved status and transcript:

```powershell
Get-Content (Join-Path $recordingRun 'recording.json')
Get-Content (Join-Path $recordingRun 'transcript.txt')
```

## What the evidence contains

| File | Purpose |
| --- | --- |
| `plan.json` | Original bytes of the checked synthetic fixture passed to the child CLI. |
| `demo.cast` | Timed terminal output, including labelled walkthrough text and captured CLI output. |
| `transcript.txt` | The same output as readable text. |
| `recording.json` | Attempt status, observed child exit, timing, Python/OS versions, Git commit/dirty flag, source hashes, accepted provider metadata and artifact hashes. |
| `review/review.json` | Original structured review, candidate and provider observations, when produced. |
| `review/outbound.json` | The plan-derived projection, when produced. |
| `review/review.md` | Original human-readable review, when produced. |

Failed attempts may lack the `review/` files. The adapter does not retain rejected
HTTP bodies; the recording preserves its sanitized diagnostic instead. No raw
environment, Git remote URL, shell history, desktop or credentials are collected.
Git commit and dirty status are null when Git metadata is unavailable. File hashes
identify bytes; this recording is not signed or an attestation of model execution.
The local daemon and source checkout remain trusted components.

`review_wall_seconds` measures the complete child CLI call. Provider `latency_ms`
measures the chat request only; these are different measurements. The recording
uses [asciicast v2](https://docs.asciinema.org/manual/asciicast/v2/) with actual
elapsed timestamps and no configured idle-time compression. The child output is
buffered until it exits, then emitted as a block; this is not token streaming or
a recording of typed keystrokes. Pause playback to read the report. It is a
scripted terminal capture, not an MP4 or GIF, and GitHub can display the text
transcript without requiring a player.

CPU/RAM, GPU utilization, peak memory and Ollama application version are not
automatically collected. Retain your hardware description and the output of
`ollama --version` separately if publishing the environment. The report includes
the model tag, preflight manifest digest and generation options.

## Explain it in an interview

Use these three beats while showing the transcript or recording:

1. **The input:** “This synthetic plan removes a subnet and replaces two network
   resources. One replacement creates before deleting; the other deletes first.”
2. **The boundary:** “The local model receives aliases and action metadata, then
   selects questions from a fixed catalogue. Python rejects missing resources,
   incorrect facts and irrelevant or missing required questions.”
3. **The result:** “The validated report distinguishes cutover from interruption
   and asks about recovery. The deterministic policy still requires human review.
   This demonstrates a constrained integration; it does not establish time savings
   or production readiness.”

Use the result beat only for a passed attempt. If the model fails, show the
diagnostic and explain that validation stopped the review. Aim for roughly a
minute of explanation, but allow the model's actual runtime to determine the
capture length. Keep any later edited excerpt clearly labelled and preserve the
full original recording beside it.

## Bundle the attempt for review

After inspecting the files, create a ZIP beside the output folder. This command
also works for a failed attempt and does not overwrite an existing ZIP:

```powershell
# Include the complete attempt so timing, status and source evidence stay together.
$recordingZip = $recordingRun + '.zip'
Compress-Archive -Path $recordingRun -DestinationPath $recordingZip -ErrorAction Stop
Write-Output "Recording ZIP: $recordingZip"
```

Share that ZIP for validation before selecting a recording to publish. Both the
folder and ZIP remain under Git-ignored `reports/`; the script uploads nothing.
Preserve unsuccessful attempts when reporting how many runs passed. A successful
single-plan recording is separate from the 12-case evaluation and does not
replace it. After capture, `ollama stop qwen2.5:3b` can release the model's memory.
