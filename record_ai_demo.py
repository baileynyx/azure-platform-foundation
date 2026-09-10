"""Record real local CLI output as asciicast v2 and a readable transcript.

The recording shows the deterministic baseline and adversarial contract tests;
its metadata explicitly disclaims live AI inference. No simulated model output
or staged success messages are substituted for subprocess output.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parent
    events, transcript = [], []
    start = time.monotonic()

    def emit(value):
        events.append([round(time.monotonic() - start, 3), 'o', value.replace('\n', '\r\n')])
        transcript.append(value)

    emit('Terraform review demonstration — OFFLINE BASELINE; NO LIVE AI\n\n')
    with tempfile.TemporaryDirectory(prefix='ai-review-demo-') as scratch:
        target = Path(scratch)
        commands = [
            ('python ai_review.py examples/plans/destructive.json --output-dir DEMO_OUTPUT',
             [sys.executable, 'ai_review.py', 'examples/plans/destructive.json', '--output-dir', str(target / 'review')], 1),
            ('python evaluate_ai_review.py --output-dir DEMO_EVALUATION',
             [sys.executable, 'evaluate_ai_review.py', '--output-dir', str(target / 'evaluation')], 0),
        ]
        for display, command, expected in commands:
            emit('$ ' + display + '\n')
            process = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=60)
            emit(process.stdout + process.stderr)
            emit(f'Observed exit: {process.returncode}\n\n')
            if process.returncode != expected:
                raise RuntimeError('Demonstration command failed its expected exit contract.')
        emit('Recorded review report:\n\n')
        emit((target / 'review/review.md').read_text(encoding='utf-8'))
        evaluation = json.loads((target / 'evaluation/evaluation.json').read_text(encoding='utf-8'))
        (args.output_dir / 'evaluation.json').write_text(json.dumps(evaluation, indent=2) + '\n', encoding='utf-8')
        (args.output_dir / 'review.md').write_text((target / 'review/review.md').read_text(encoding='utf-8'), encoding='utf-8')
    header = {'version': 2, 'width': 120, 'height': 40, 'title': 'Terraform AI review — offline contract demonstration',
              'env': {'TERM': 'xterm-256color', 'SHELL': 'portable Python subprocess'}}
    (args.output_dir / 'demo.cast').write_text('\n'.join(json.dumps(x) for x in [header] + events) + '\n', encoding='utf-8')
    (args.output_dir / 'transcript.txt').write_text(''.join(transcript), encoding='utf-8')
    print('Recorded actual CLI output; temporary reports cleaned up.')


if __name__ == '__main__':
    main()
