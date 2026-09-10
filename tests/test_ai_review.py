"""Exercise privacy, evidence, real CLI and intercepted Azure HTTP boundaries.

All HTTP responses in this suite are synthetic. A passing transport test proves
request/response handling, not Azure authentication or model quality.
"""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import ai_review as ai
import evaluate_ai_review as evaluation

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'examples/ai/evaluation-cases.json').read_text(encoding='utf-8'))
ENV = {'AZURE_OPENAI_ENDPOINT': 'https://synthetic-test.openai.azure.com',
       'AZURE_OPENAI_DEPLOYMENT': 'synthetic-deployment', 'AZURE_OPENAI_API_KEY': 'synthetic-key-not-real'}


def payload(name='replace_unknown'):
    return json.dumps(next(c['plan'] for c in CASES if c['name'] == name)).encode()


def envelope(candidate):
    return {'model': 'synthetic-model', 'choices': [{'finish_reason': 'stop',
            'message': {'content': json.dumps(candidate), 'refusal': None}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}


class ProjectionTests(unittest.TestCase):
    def test_no_raw_strings_leave_projection(self):
        projection, local = ai.prepare(payload('injection_and_secrets'))
        encoded = json.dumps(projection)
        for marker in ['SECRET', 'IGNORE', 'password', 'azurerm', 'module.', 'deploy', 'sha256']:
            self.assertNotIn(marker, encoded)
        self.assertIn('IGNORE', json.dumps(local))
        self.assertEqual(projection['evidence'][0]['unknown_values'], 'present')

    def test_deposed_objects_have_distinct_pointers(self):
        plan = json.loads(payload())
        other = copy.deepcopy(plan['resource_changes'][0])
        other['deposed'] = 'old-instance'
        plan['resource_changes'].append(other)
        projection, local = ai.prepare(json.dumps(plan).encode())
        self.assertEqual(len(projection['evidence']), 2)
        self.assertEqual({r['json_pointer'] for r in local['evidence_map'].values()},
                         {'/resource_changes/0/change', '/resource_changes/1/change'})

    def test_unknown_metadata_is_not_silently_known(self):
        for bad in [None, 1, 'true', {'nested': 'secret'}, [False, 0]]:
            with self.subTest(bad=bad), self.assertRaises(ai.ReviewError):
                ai.unknown_status({'after_unknown': bad})
        self.assertEqual(ai.unknown_status({}), 'not_reported')
        self.assertEqual(ai.unknown_status({'after_unknown': {'x': [False, {}]}}), 'none_marked')
        self.assertEqual(ai.unknown_status({'after_unknown': {'x': [False, True]}}), 'present')

    def test_oversized_inputs_are_rejected(self):
        with self.assertRaises(ai.ReviewError):
            ai.unknown_status({'after_unknown': [False] * 10001})
        plan = json.loads(payload())
        resource = plan['resource_changes'][0]
        plan['resource_changes'] = [dict(resource, address=f'demo.r{i}') for i in range(21)]
        with self.assertRaises(ai.ReviewError):
            ai.prepare(json.dumps(plan).encode())
        with self.assertRaises(ai.ReviewError):
            ai.prepare(b' ' * (ai.plan_review.MAX_BYTES + 1))

    def test_invalid_plan_prevents_provider_calls(self):
        with patch.object(ai, 'azure_request') as live:
            for raw in [b'{', b'{"format_version":"1.2","format_version":"1.2"}', b'null', b'NaN']:
                with self.subTest(raw=raw), self.assertRaises(ai.ReviewError):
                    ai.run_review(raw, 'azure')
            live.assert_not_called()

    def test_local_addresses_are_escaped(self):
        plan = json.loads(payload())
        plan['resource_changes'][0]['address'] = '<script>alert(1)</script>[click](https://evil.invalid)'
        text = ai.markdown(ai.run_review(json.dumps(plan).encode()))
        self.assertNotIn('<script>', text)
        self.assertNotIn('[click]', text)


class ContractTests(unittest.TestCase):
    def test_case_oracles_and_adversarial_probes(self):
        report = evaluation.evaluate()
        self.assertEqual(report['cases_passed'], 12)
        self.assertEqual(report['adversarial_probes_rejected'], 13)
        self.assertEqual(report['successful_live_responses'], 0)
        self.assertIsNone(report['total_tokens'])

    def test_arbitrary_shapes_are_rejected(self):
        projection, _ = ai.prepare(payload())
        for value in [None, [], {'findings': None}, {'findings': [None]}, {'findings': [{}]}]:
            with self.subTest(value=value), self.assertRaises(ai.ReviewError):
                ai.validate_response(value, projection)

    def test_data_removal_explanation(self):
        result = ai.run_review(payload('data_removal'))
        self.assertIn('not evidence of managed infrastructure destruction', ai.markdown(result))
        self.assertEqual(result['response']['findings'][0]['questions'], ['state', 'verification'])

    def test_question_variation_is_allowed(self):
        projection, _ = ai.prepare(payload('create'))
        candidate = ai.baseline(projection)
        candidate['findings'][0]['questions'] = ['dependencies', 'verification']
        self.assertEqual(ai.validate_response(candidate, projection), candidate)

    def test_replay_is_explicitly_offline(self):
        projection, _ = ai.prepare(payload())
        result = ai.run_review(payload(), 'replay', json.dumps(ai.baseline(projection)).encode())
        self.assertEqual(result['provider']['source'], 'replay')
        self.assertIn('no live model was called', ai.markdown(result))


class TransportTests(unittest.TestCase):
    def call_with(self, data, projection=None):
        projection = projection or ai.prepare(payload())[0]
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(json.dumps(data).encode())) as opened:
            result = ai.azure_request(projection, ENV)
            return result, opened.call_args

    def test_request_projection_schema_and_usage(self):
        projection, _ = ai.prepare(payload('injection_and_secrets'))
        (candidate, metadata), call = self.call_with(envelope(ai.baseline(projection)), projection)
        request = call.args[0]
        self.assertEqual(request.full_url, 'https://synthetic-test.openai.azure.com/openai/v1/chat/completions')
        self.assertEqual(request.get_header('Api-key'), ENV['AZURE_OPENAI_API_KEY'])
        self.assertEqual(call.kwargs['timeout'], 30)
        body = json.loads(request.data)
        self.assertNotIn('SYNTHETIC_SECRET', request.data.decode())
        self.assertNotIn('IGNORE POLICY', request.data.decode())
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertEqual(body['max_completion_tokens'], 4096)
        self.assertEqual(metadata['usage']['total_tokens'], 150)
        ai.validate_response(candidate, projection)

    def test_endpoint_restrictions(self):
        for endpoint in ['http://synthetic-test.openai.azure.com', 'https://evil.invalid',
                         'https://synthetic-test.openai.azure.com.evil.invalid',
                         'https://synthetic-test.openai.azure.com/path',
                         'https://user@synthetic-test.openai.azure.com',
                         'https://synthetic-test.openai.azure.com?token=secret']:
            with self.subTest(endpoint=endpoint), patch('urllib.request.OpenerDirector.open') as opened:
                with self.assertRaises(ai.ReviewError):
                    ai.azure_request(ai.prepare(payload())[0], ENV | {'AZURE_OPENAI_ENDPOINT': endpoint})
                opened.assert_not_called()

    def test_refusals_truncation_tool_calls_and_bad_envelopes(self):
        projection, _ = ai.prepare(payload())
        base = envelope(ai.baseline(projection))
        variants = [None, [], {'choices': []}]
        for reason in ['length', 'content_filter']:
            data = copy.deepcopy(base)
            data['choices'][0]['finish_reason'] = reason
            variants.append(data)
        for field, value in [('refusal', 'sensitive-text'), ('tool_calls', [{'name': 'apply'}]), ('content', '{')]:
            data = copy.deepcopy(base)
            data['choices'][0]['message'][field] = value
            variants.append(data)
        for usage in [{}, {'prompt_tokens': True, 'completion_tokens': 50, 'total_tokens': 51},
                      {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 160}]:
            data = copy.deepcopy(base)
            data['usage'] = usage
            variants.append(data)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ai.ReviewError):
                self.call_with(data, projection)

    def test_http_errors_are_sanitized_without_retry(self):
        error = urllib.error.HTTPError('https://secret.invalid', 429, 'SECRET_HTTP_BODY', {}, io.BytesIO(b'secret'))
        with patch('urllib.request.OpenerDirector.open', side_effect=error) as opened:
            with self.assertRaises(ai.ReviewError) as captured:
                ai.azure_request(ai.prepare(payload())[0], ENV)
            self.assertNotIn('SECRET', str(captured.exception))
            self.assertEqual(opened.call_count, 1)

    def test_redirects_and_oversized_responses(self):
        with self.assertRaises(ai.ReviewError):
            ai.NoRedirect().redirect_request(None, None, 307, '', {}, 'https://evil.invalid')
        with patch('urllib.request.OpenerDirector.open', return_value=io.BytesIO(b' ' * (ai.MAX_RESPONSE + 1))):
            with self.assertRaises(ai.ReviewError):
                ai.azure_request(ai.prepare(payload())[0], ENV)

    def test_contradictory_provider_response_is_rejected(self):
        projection, _ = ai.prepare(payload())
        candidate = ai.baseline(projection)
        candidate['findings'][0]['category'] = 'unchanged'
        with patch.object(ai, 'azure_request', return_value=(candidate, {'source': 'azure'})):
            with self.assertRaises(ai.ReviewError):
                ai.run_review(payload(), 'azure')


class CLITests(unittest.TestCase):
    def test_native_exit_codes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, expected in [('create', 0), ('delete', 1)]:
                plan = root / f'{name}.json'
                plan.write_bytes(payload(name))
                output = root / name
                command = [sys.executable, str(ROOT / 'ai_review.py'), str(plan), '--output-dir', str(output)]
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                saved = (output / 'review.json').read_bytes()
                self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
                self.assertEqual((output / 'review.json').read_bytes(), saved)
                self.assertEqual(plan.read_bytes(), payload(name))

    def test_rejected_replay_writes_no_success_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan, response, output = root / 'plan.json', root / 'response.json', root / 'output'
            plan.write_bytes(payload())
            response.write_text('{"findings":[]}', encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'ai_review.py'), str(plan),
                                     '--provider', 'replay', '--response', str(response),
                                     '--output-dir', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())

    def test_existing_output_blocks_network(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ai, 'azure_request') as live:
            self.assertEqual(ai.main(['missing-plan', '--provider', 'azure', '--output-dir', temp]), 2)
            live.assert_not_called()


if __name__ == '__main__':
    unittest.main()
