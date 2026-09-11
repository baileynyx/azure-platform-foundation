"""Recorder contract tests with intercepted subprocesses; no model is loaded."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import ai_review as ai
import record_ollama_demo as demo


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.target = Path(self.scratch.name) / 'recording'
        self.payload = demo.fixture_bytes()
        # This baseline is only test data for a mocked child process. It must
        # never be committed or advertised as an actual Ollama recording.
        self.result = ai.run_review(self.payload)
        self.result['provider'] = {
            'source': 'ollama', 'live_inference': True, 'model': 'qwen2.5:3b',
            'request_version': ai.OLLAMA_REQUEST_VERSION, 'latency_ms': 1234,
            'installed_manifest_digest': 'a' * 64,
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150},
        }

    def child(self, command, **kwargs):
        self.assertEqual(command[1], str(demo.ROOT / 'ai_review.py'))
        self.assertEqual(command[3:5], ['--provider', 'ollama'])
        self.assertEqual(Path(command[2]).read_bytes(), self.payload)
        self.assertEqual(Path(command[2]), self.target / 'plan.json')
        self.assertEqual(kwargs['timeout'], 240)
        self.assertEqual(kwargs['env']['PYTHONUTF8'], '1')
        ai.save_new(Path(command[-1]), self.result)
        return subprocess.CompletedProcess(command, 1, 'AI review: ollama; policy=review_required; exit=1\n')

    def capture(self, effect):
        # Suppress terminal output and Git subprocesses, and intercept the only
        # model-running subprocess. Tests cannot accidentally invoke Ollama.
        with patch.object(demo, 'source_state', return_value={'commit': None, 'dirty': None}), \
                patch.object(demo.subprocess, 'run', side_effect=effect) as child, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = demo.main(['--output-dir', str(self.target)])
        return code, child

    def metadata(self):
        return json.loads((self.target / 'recording.json').read_bytes())

    def test_success_retains_original_reports_and_actual_output(self):
        code, child = self.capture(self.child)
        self.assertEqual(code, 0)
        child.assert_called_once()
        metadata = self.metadata()
        self.assertEqual(metadata['status'], 'passed')
        self.assertEqual(metadata['review_exit'], 1)
        self.assertEqual(metadata['provider'], self.result['provider'])
        self.assertGreaterEqual(metadata['review_wall_seconds'], 0)
        for name, digest in metadata['artifact_sha256'].items():
            self.assertEqual(hashlib.sha256((self.target / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(len(metadata['artifact_sha256']), 6)
        self.assertEqual(json.loads((self.target / 'review/review.json').read_bytes()), self.result)
        transcript = (self.target / 'transcript.txt').read_text(encoding='utf-8')
        self.assertIn('AI review: ollama; policy=review_required; exit=1', transcript)
        self.assertIn('human review is required', transcript)
        self.assertIn(ai.markdown(self.result), transcript)
        frames = [json.loads(line) for line in (self.target / 'demo.cast').read_text().splitlines()]
        self.assertEqual(frames[0]['version'], 2)
        self.assertNotIn('env', frames[0])
        self.assertNotIn('idle_time_limit', frames[0])
        self.assertEqual([f[0] for f in frames[1:]], sorted(f[0] for f in frames[1:]))
        self.assertTrue(all(f[1] == 'o' for f in frames[1:]))
        self.assertEqual(''.join(f[2] for f in frames[1:]).replace('\r\n', '\n'), transcript)

    def test_unexpected_exit_preserves_failure_without_success_report(self):
        for exit_code in (0, 2):
            with self.subTest(exit_code=exit_code):
                self.target = Path(self.scratch.name) / str(exit_code)
                code, child = self.capture(lambda *a, **kw: subprocess.CompletedProcess(a[0], exit_code, 'diagnostic\n'))
                self.assertEqual(code, 2)
                child.assert_called_once()
                self.assertEqual(self.metadata()['status'], 'failed')
                self.assertEqual(self.metadata()['review_exit'], exit_code)
                self.assertIsNone(self.metadata()['provider'])
                self.assertFalse((self.target / 'review').exists())
                self.assertIn('diagnostic', (self.target / 'transcript.txt').read_text())

    def test_exit_one_requires_complete_live_evidence(self):
        valid = copy.deepcopy(self.result)
        mutations = [lambda r: r['response']['findings'].pop(),
                     lambda r: r['provider'].update(source='deterministic_baseline', live_inference=False),
                     lambda r: r['gate'].update(status='safe'),
                     lambda r: r['gate'].update(sha256='0' * 64)]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.target = Path(self.scratch.name) / str(index)
                self.result = copy.deepcopy(valid)
                mutate(self.result)
                code, _ = self.capture(self.child)
                self.assertEqual(code, 2)
                self.assertEqual(self.metadata()['status'], 'failed')
                # Retain the rejected report exactly, rather than fixing it.
                self.assertEqual(json.loads((self.target / 'review/review.json').read_bytes()), self.result)

    def test_exit_one_without_reports_fails(self):
        code, _ = self.capture(lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, ''))
        self.assertEqual(code, 2)
        self.assertEqual(self.metadata()['status'], 'failed')

    def test_existing_output_blocks_inference_and_preserves_bytes(self):
        self.target.mkdir()
        marker = self.target / 'transcript.txt'
        marker.write_bytes(b'earlier failure\r\n')
        code, child = self.capture(self.child)
        self.assertEqual(code, 2)
        child.assert_not_called()
        self.assertEqual(marker.read_bytes(), b'earlier failure\r\n')

    def test_real_cli_from_another_directory_preserves_provider_failure(self):
        # An unsupported model is rejected before HTTP setup. This exercises the
        # real nested CLI, stderr capture and paths with spaces without inference.
        self.target = Path(self.scratch.name) / 'recording with spaces'
        process = subprocess.run(
            [sys.executable, str(demo.ROOT / 'record_ollama_demo.py'),
             '--output-dir', str(self.target)], cwd=self.scratch.name,
            capture_output=True, text=True, encoding='utf-8', timeout=30,
            env=dict(os.environ, OLLAMA_MODEL='unsupported-test-model', PYTHONUTF8='1'))
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertEqual(self.metadata()['review_exit'], 2)
        self.assertEqual(self.metadata()['status'], 'failed')
        self.assertIn('OLLAMA_MODEL must be', (self.target / 'transcript.txt').read_text())
        self.assertEqual(self.metadata()['source']['sha256']['ai_review.py'],
                         hashlib.sha256((demo.ROOT / 'ai_review.py').read_bytes()).hexdigest())

    def test_modified_fixture_blocks_inference_before_recording(self):
        changed = json.loads(self.payload)
        changed['resource_changes'][0]['address'] = 'PRIVATE-RESOURCE'
        with patch.object(demo.ai, 'read_bytes', return_value=json.dumps(changed).encode()):
            code, child = self.capture(self.child)
        self.assertEqual(code, 2)
        child.assert_not_called()
        self.assertFalse(self.target.exists())

    def test_windows_fixture_line_endings_are_accepted(self):
        windows = self.payload.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        with patch.object(demo.ai, 'read_bytes', return_value=windows):
            self.assertEqual(demo.fixture_bytes(), windows)

    def test_timeout_retains_incomplete_attempt_and_no_raw_exception(self):
        code, child = self.capture(subprocess.TimeoutExpired('PRIVATE-COMMAND', 240, output=b'PRIVATE-BODY'))
        self.assertEqual(code, 2)
        child.assert_called_once()
        self.assertEqual(self.metadata()['status'], 'timeout')
        self.assertIsNone(self.metadata()['review_exit'])
        transcript = (self.target / 'transcript.txt').read_text()
        self.assertIn('240-second', transcript)
        self.assertNotIn('PRIVATE', transcript)

    def test_interruption_is_preserved_and_not_retried(self):
        code, child = self.capture(KeyboardInterrupt())
        self.assertEqual(code, 130)
        child.assert_called_once()
        self.assertEqual(self.metadata()['status'], 'interrupted')
        self.assertIsNone(self.metadata()['provider'])

    def test_report_markdown_and_outbound_tampering_fail(self):
        for name in ('review.md', 'outbound.json'):
            with self.subTest(name=name):
                self.target = Path(self.scratch.name) / name
                def changed_child(command, **kwargs):
                    process = self.child(command, **kwargs)
                    (self.target / 'review' / name).write_text('{}', encoding='utf-8')
                    return process
                code, _ = self.capture(changed_child)
                self.assertEqual(code, 2)
                self.assertEqual(self.metadata()['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
