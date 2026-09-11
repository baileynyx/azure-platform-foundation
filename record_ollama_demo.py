"""Capture one real Ollama CLI review of the fixed synthetic destructive plan.

This is a portable scripted terminal recording, not a desktop video. Narrative
is labelled separately from captured CLI output; timestamps retain actual waits.
There is no replay, baseline, retry or arbitrary-plan option in this recorder.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import ai_review as ai

ROOT = Path(__file__).resolve().parent
FIXTURE = 'examples/plans/destructive.json'
# Compare parsed JSON so a normal Windows CRLF checkout is accepted. Pinning the
# complete fixture prevents a replacement real plan from entering public output.
FIXTURE_DIGEST = 'cdc4a4116976653578ad9e20639a9483bc141328b1a2f0414af9ed784aad695f'
SOURCE_FILES = ('record_ollama_demo.py', 'ai_review.py', 'plan_review.py', FIXTURE)
REVIEW_TIMEOUT = 240


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def fixture_bytes():
    payload = ai.read_bytes(ROOT / FIXTURE, 64 * 1024)
    canonical = json.dumps(ai.parse_json(payload), sort_keys=True, separators=(',', ':')).encode()
    if sha256(canonical) != FIXTURE_DIGEST:
        raise ai.ReviewError('The synthetic fixture has changed; restore the committed demonstration fixture.')
    return payload


def source_state():
    """Record source identity without collecting remote URLs, usernames or env.

    Git identity is optional for downloaded source archives. File hashes still
    identify the bytes used, but neither hashes nor local Git metadata attest
    execution. Dirty is a boolean only: filenames may contain private strings.
    """
    state = {'commit': None, 'dirty': None,
             'sha256': {name: sha256((ROOT / name).read_bytes()) for name in SOURCE_FILES}}
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                capture_output=True, text=True, timeout=10, check=True)
        status = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=normal'],
                                cwd=ROOT, capture_output=True, timeout=10, check=True)
        state.update(commit=commit.stdout.strip(), dirty=bool(status.stdout))
    except (OSError, subprocess.SubprocessError):
        pass  # Null explicitly means the Git observation was unavailable.
    return state


def checked_report(directory, payload):
    """Recheck saved evidence before describing this attempt as successful."""
    result = ai.parse_json(ai.read_bytes(directory / 'review.json', ai.MAX_RESPONSE))
    projection, local = ai.prepare(payload)
    if (result['version'] != ai.VERSION or result['advisory_only'] is not True or
            result['projection'] != projection or result['gate'] != local['gate'] or
            result['evidence_map'] != local['evidence_map'] or
            result['gate']['status'] != 'review_required' or
            result['provider']['source'] != 'ollama' or
            result['provider']['live_inference'] is not True or
            result['provider']['request_version'] != ai.OLLAMA_REQUEST_VERSION):
        raise ai.ReviewError('Saved review does not match this live demonstration contract.')
    ai.validate_response(result['response'], projection)
    if ai.parse_json((directory / 'outbound.json').read_bytes()) != projection:
        raise ai.ReviewError('Saved outbound evidence does not match the synthetic plan.')
    # Universal-newline reading accepts reports written by Python on Windows.
    if (directory / 'review.md').read_text(encoding='utf-8') != ai.markdown(result):
        raise ai.ReviewError('Saved Markdown does not match the validated review.')
    return result


def record(directory):
    # Reserve the parent before any model call. Even a failed attempt owns its
    # directory permanently, so reruns cannot overwrite earlier observations.
    payload = fixture_bytes()
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'plan.json').write_bytes(payload)
    started = time.monotonic()
    metadata = {'version': 'ollama-demo-v1', 'status': 'failed',
                'started_at': datetime.now(timezone.utc).isoformat(),
                'python_version': platform.python_version(),
                'os': {'system': platform.system(), 'release': platform.release(),
                       'version': platform.version(), 'machine': platform.machine()},
                'source': source_state(), 'review_exit': None,
                'review_wall_seconds': None, 'provider': None}
    # Stream evidence to disk as it is emitted, keeping partial recordings useful
    # if interrupted. No shell transcript, desktop content or environment dump
    # is captured. The child CLI itself buffers until it has completed a review.
    with (directory / 'demo.cast').open('x', encoding='utf-8', newline='\n') as cast, \
            (directory / 'transcript.txt').open('x', encoding='utf-8', newline='\n') as transcript:
        header = {'version': 2, 'width': 120, 'height': 40,
                  'title': 'Local Ollama Terraform review - captured attempt'}
        cast.write(json.dumps(header) + '\n')

        def emit(text):
            text = text.replace('\r\n', '\n')
            cast.write(json.dumps([round(time.monotonic() - started, 3), 'o',
                                   text.replace('\n', '\r\n')]) + '\n')
            transcript.write(text)
            cast.flush()
            transcript.flush()
            print(text, end='', flush=True)

        exit_code = 2
        try:
            emit('WALKTHROUGH: one local Ollama attempt; synthetic Terraform evidence.\n'
                 'The model selects questions; Python owns the review decision.\n\n')
            projection, _ = ai.prepare(payload)
            for item in projection['evidence']:
                emit(f'{item["evidence_id"]}: {" -> ".join(item["actions"])}\n')
            emit('\nCAPTURED CLI: ai_review.py examples/plans/destructive.json '
                 '--provider ollama\nOutput is saved in this recording folder under review/.\n'
                 'Waiting for the actual model response; no retries or substituted answers.\n')
            # Review the already checked snapshot, so a concurrent edit to the
            # checkout fixture cannot change the input after our synthetic check.
            command = [sys.executable, str(ROOT / 'ai_review.py'), str(directory / 'plan.json'),
                       '--provider', 'ollama', '--output-dir', str(directory / 'review')]
            # Explicit UTF-8 keeps child output portable across Windows code pages.
            # Merge stderr into stdout so an error keeps its observed stream order.
            review_started = time.monotonic()
            try:
                process = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, encoding='utf-8', timeout=REVIEW_TIMEOUT,
                                         env=dict(os.environ, PYTHONUTF8='1'))
            finally:
                metadata['review_wall_seconds'] = round(time.monotonic() - review_started, 3)
            metadata['review_exit'] = process.returncode
            emit(process.stdout)
            emit(f'Observed review exit: {process.returncode}\n')
            if process.returncode != 1:
                raise ai.ReviewError('Expected review-required exit 1; this attempt did not pass.')
            result = checked_report(directory / 'review', payload)
            metadata.update(status='passed', provider=result['provider'])
            emit('\nWALKTHROUGH: exit 1 means human review is required. It is not a provider error.\n'
                 f'Observed CLI wall time: {metadata["review_wall_seconds"]:.3f} seconds.\n'
                 f'Reported chat latency: {result["provider"]["latency_ms"]} ms.\n'
                 '\nVALIDATED REPORT:\n\n')
            emit((directory / 'review/review.md').read_text(encoding='utf-8'))
            exit_code = 0
        except subprocess.TimeoutExpired:
            # The subprocess runner kills and waits for the child on timeout.
            # Its exception may contain bytes or private OS detail; do not echo it.
            metadata['status'] = 'timeout'
            emit('\nRECORDING FAILED: review exceeded the 240-second total limit.\n')
        except KeyboardInterrupt:
            metadata['status'] = 'interrupted'
            emit('\nRECORDING INTERRUPTED: no successful run is claimed.\n')
            exit_code = 130
        except (ai.ReviewError, OSError, KeyError, TypeError) as error:
            metadata['status'] = 'failed'
            message = str(error) if isinstance(error, ai.ReviewError) else 'Unable to capture or verify the review files.'
            emit(f'\nRECORDING FAILED: {message}\n')
        finally:
            metadata['recording_seconds'] = round(time.monotonic() - started, 3)
            # Hash retained files, including failure reports when they exist.
            # Keep the original bytes; never rewrite the review into a success.
            retained = ['plan.json', 'demo.cast', 'transcript.txt',
                        'review/review.json', 'review/review.md', 'review/outbound.json']
            metadata['artifact_sha256'] = {
                name: sha256((directory / name).read_bytes())
                for name in retained if (directory / name).is_file()}
            (directory / 'recording.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        code = record(args.output_dir.resolve())
        print(f'Recorder exit: {code}; results: {args.output_dir}')
        return code
    except (ai.ReviewError, OSError) as error:
        message = str(error) if isinstance(error, ai.ReviewError) else 'Choose a fresh writable output directory.'
        print(f'Recording setup failed: {message}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
