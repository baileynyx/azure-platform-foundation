"""Synthetic intercepted Ollama transport tests, not local model benchmarks."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import ai_review as ai
import evaluate_ai_review as evaluation

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(evaluation.CORPUS.read_text(encoding='utf-8'))
MODEL = 'qwen2.5:3b'
DIGEST = 'a' * 64  # Synthetic manifest identity; no weights are loaded.


def payload(name='replace_unknown'):
    return json.dumps(next(c['plan'] for c in CASES if c['name'] == name)).encode()


def tags():
    return {'models': [{'name': MODEL, 'digest': DIGEST}]}


def envelope(candidate):
    # Simulate the provider's named entries without using production conversion.
    # Preserve extra top-level fields and invalid entries for adversarial tests.
    wire = dict(candidate, findings={f'R{index:03d}': finding
                                   for index, finding in enumerate(candidate['findings'], 1)})
    return {'model': MODEL, 'done': True, 'done_reason': 'stop',
            'message': {'role': 'assistant', 'content': json.dumps(wire)},
            'prompt_eval_count': 100, 'eval_count': 50,
            'total_duration': 1000000, 'load_duration': 100000,
            'prompt_eval_duration': 200000, 'eval_duration': 700000}


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.projection, _ = ai.prepare(payload())
        self.candidate = ai.baseline(self.projection)

    def test_loopback_request_privacy_schema_and_measured_metadata(self):
        requests = []
        def intercepted(request, timeout):
            requests.append((request, timeout))
            if request.full_url.endswith('/api/tags'):
                return response(tags())
            body = json.loads(request.data)
            projection = json.loads(body['messages'][1]['content'])['input']
            return response(envelope(ai.baseline(projection)))
        with patch.dict(os.environ, {'AZURE_OPENAI_API_KEY': 'SECRET-KEY',
                                    'OLLAMA_HOST': 'https://remote.invalid',
                                    'HTTPS_PROXY': 'https://proxy.invalid'}), \
                patch('urllib.request.OpenerDirector.open', side_effect=intercepted), \
                patch('urllib.request.build_opener', wraps=ai.urllib.request.build_opener) as builder:
            result = ai.run_review(payload('injection_and_secrets'), 'ollama')
        self.assertEqual(builder.call_args.args[0].proxies, {})
        self.assertIsInstance(builder.call_args.args[1], ai.NoRedirect)
        self.assertEqual([(r.full_url, t) for r, t in requests],
                         [('http://127.0.0.1:11434/api/tags', 10),
                          ('http://127.0.0.1:11434/api/chat', 180)])
        request = requests[1][0]
        body = json.loads(request.data)
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(dict(request.header_items()), {'Content-type': 'application/json'})
        self.assertIs(body['stream'], False)
        self.assertEqual(body['format'], json.loads(body['messages'][1]['content'])['response_schema'])
        self.assertEqual(body['format']['properties']['findings']['type'], 'object')
        self.assertEqual(body['options'], {'temperature': 0, 'seed': 42, 'num_ctx': 8192, 'num_predict': 2048})
        for marker in (b'SECRET', b'IGNORE', b'password', b'azurerm', b'module.'):
            self.assertNotIn(marker, request.data)
        metadata = result['provider']
        self.assertEqual(metadata['request_version'], 'ollama-review-v3')
        self.assertEqual(metadata['installed_manifest_digest'], DIGEST)
        self.assertEqual(metadata['usage']['total_tokens'], 150)
        self.assertEqual(metadata['durations_ns']['eval_duration'], 700000)
        self.assertGreaterEqual(metadata['latency_ms'], 0)
        self.assertTrue(metadata['live_inference'])
        self.assertNotIn('no live model was called', ai.markdown(result))

    def test_request_distinguishes_both_replacement_orders(self):
        # Inspect bytes sent through the real adapter, rather than testing only
        # the helper rules. Expected lists are authored for the reported fixture.
        raw = (ROOT / 'examples/plans/destructive.json').read_bytes()
        projection, _ = ai.prepare(raw)
        with patch('urllib.request.OpenerDirector.open', side_effect=[
                response(tags()), response(envelope(ai.baseline(projection)))]) as network:
            ai.run_review(raw, 'ollama')
        body = json.loads(network.call_args.args[0].data)
        submitted = json.loads(body['messages'][1]['content'])
        self.assertEqual(submitted['input'], projection)
        self.assertEqual(submitted['request_version'], 'ollama-review-v3')
        # Coverage and exact facts are now expressed in the generation schema,
        # including the unchanged resource that still needs a finding.
        schema = body['format']['properties']['findings']
        self.assertEqual(schema['required'], ['R001', 'R002', 'R003', 'R004'])
        self.assertEqual(set(schema['properties']), set(schema['required']))
        self.assertIs(schema['additionalProperties'], False)
        for record in projection['evidence']:
            fields = schema['properties'][record['evidence_id']]['properties']
            for name in ('evidence_id', 'category', 'unknown_values'):
                self.assertEqual(fields[name]['enum'], [record[name]])
        self.assertEqual(schema['properties']['R001']['properties']['questions']['items']['enum'],
                         ['cutover', 'dependencies', 'recovery', 'verification'])
        self.assertEqual(schema['properties']['R004']['properties']['questions']['items']['enum'],
                         ['dependencies', 'interruption', 'recovery', 'verification'])
        self.assertEqual(submitted['question_constraints'], [
            {'evidence_id': 'R001',
             'allowed_questions': ['cutover', 'dependencies', 'recovery', 'verification'],
             'required_questions': ['cutover', 'recovery']},
            {'evidence_id': 'R002', 'allowed_questions': ['dependencies', 'verification'],
             'required_questions': []},
            {'evidence_id': 'R003', 'allowed_questions': ['dependencies', 'recovery', 'verification'],
             'required_questions': ['recovery']},
            {'evidence_id': 'R004',
             'allowed_questions': ['dependencies', 'interruption', 'recovery', 'verification'],
             'required_questions': ['interruption', 'recovery']},
        ])

    def test_reported_replacement_confusion_remains_rejected(self):
        # Reproduce the user-reported Qwen response. Also isolate each faulty
        # finding so rejection of R001 cannot mask a regression in R004 checks.
        raw = (ROOT / 'examples/plans/destructive.json').read_bytes()
        valid = {'findings': [
            {'evidence_id': 'R001', 'category': 'replace', 'unknown_values': 'not_reported',
             'questions': ['recovery', 'cutover']},
            {'evidence_id': 'R002', 'category': 'unchanged', 'unknown_values': 'not_reported',
             'questions': ['verification']},
            {'evidence_id': 'R003', 'category': 'delete', 'unknown_values': 'not_reported',
             'questions': ['recovery']},
            {'evidence_id': 'R004', 'category': 'replace', 'unknown_values': 'not_reported',
             'questions': ['recovery', 'interruption']},
        ]}
        for faulty_indices in ([0], [3], [0, 3]):
            candidate = json.loads(json.dumps(valid))
            for index in faulty_indices:
                candidate['findings'][index]['questions'] = (
                    ['recovery', 'cutover', 'interruption'] if index == 0 else ['recovery', 'cutover'])
            with self.subTest(faulty_indices=faulty_indices), patch(
                    'urllib.request.OpenerDirector.open', side_effect=[response(tags()), response(envelope(candidate))]):
                with self.assertRaises(ai.ReviewError):
                    ai.run_review(raw, 'ollama')
        # Accept a manually authored valid candidate as a validator control.
        # This is synthetic evidence, not a claim that the model was corrected.
        with patch('urllib.request.OpenerDirector.open', side_effect=[response(tags()), response(envelope(valid))]):
            self.assertEqual(ai.run_review(raw, 'ollama')['gate']['status'], 'review_required')

    def test_named_response_rejects_each_missing_resource_without_repair(self):
        raw = (ROOT / 'examples/plans/destructive.json').read_bytes()
        projection, _ = ai.prepare(raw)
        valid_envelope = envelope(ai.baseline(projection))
        valid_wire = json.loads(valid_envelope['message']['content'])
        invalid = []
        # Omission of any one resource, including unchanged R002, must fail.
        for identity in ('R001', 'R002', 'R003', 'R004'):
            wire = json.loads(json.dumps(valid_wire))
            del wire['findings'][identity]
            invalid.append(wire)
        wire = json.loads(json.dumps(valid_wire))
        wire['findings']['R999'] = wire['findings']['R001']
        invalid.append(wire)
        wire = json.loads(json.dumps(valid_wire))
        wire['findings']['R001'], wire['findings']['R004'] = wire['findings']['R004'], wire['findings']['R001']
        invalid.append(wire)
        invalid.extend([{'findings': {}}, ai.baseline(projection), {'findings': {'R001': None}},
                        dict(valid_wire, approved=True)])
        for wire in invalid:
            completed = dict(valid_envelope, message={'role': 'assistant', 'content': json.dumps(wire)})
            with self.subTest(wire=wire), patch('urllib.request.OpenerDirector.open',
                                              side_effect=[response(tags()), response(completed)]):
                with self.assertRaises(ai.ReviewError):
                    ai.run_review(raw, 'ollama')

    def test_duplicate_wire_keys_are_rejected_before_normalization(self):
        completed = envelope(self.candidate)
        finding = json.dumps(self.candidate['findings'][0])
        completed['message']['content'] = '{"findings":{"R001":' + finding + ',"R001":' + finding + '}}'
        with patch('urllib.request.OpenerDirector.open', side_effect=[response(tags()), response(completed)]):
            with self.assertRaises(ai.ReviewError):
                ai.run_review(payload(), 'ollama')

    def test_named_response_preserves_candidates_and_handles_empty_evidence(self):
        # Round-trip every labelled case through intercepted native wire JSON.
        # Reverse object key order to prove mapping uses identity, not position.
        for case in CASES:
            raw = json.dumps(case['plan']).encode()
            projection, _ = ai.prepare(raw)
            valid = ai.baseline(projection)
            for finding in valid['findings']:
                finding['questions'].reverse()
            completed = envelope(valid)
            wire = json.loads(completed['message']['content'])
            wire['findings'] = dict(reversed(list(wire['findings'].items())))
            completed['message']['content'] = json.dumps(wire)
            with self.subTest(case=case['name']), patch('urllib.request.OpenerDirector.open',
                                                       side_effect=[response(tags()), response(completed)]):
                result = ai.run_review(raw, 'ollama')
            self.assertEqual(result['response'], valid)
            self.assertEqual(result['gate']['status'], case['expected_policy'])
            self.assertEqual(result['provider']['request_version'], 'ollama-review-v3')
        empty, _ = ai.prepare(payload('output_only'))
        self.assertEqual(ai.ollama_schema(empty)['properties']['findings']['required'], [])

    def test_invalid_or_cloud_model_names_never_connect(self):
        for model in ('qwen2.5:3b-cloud', 'https://evil.invalid', '../qwen', '', 'other:latest'):
            with self.subTest(model=model), patch('urllib.request.OpenerDirector.open') as network:
                with self.assertRaises(ai.ReviewError):
                    ai.ollama_request(self.projection, {'OLLAMA_MODEL': model})
                network.assert_not_called()

    def test_smaller_model_is_explicitly_supported(self):
        installed = tags()
        installed['models'][0]['name'] = 'qwen2.5:1.5b'
        completed = envelope(self.candidate)
        completed['model'] = 'qwen2.5:1.5b'
        with patch('urllib.request.OpenerDirector.open', side_effect=[response(installed), response(completed)]):
            _, metadata = ai.ollama_request(self.projection, {'OLLAMA_MODEL': 'qwen2.5:1.5b'})
        self.assertEqual(metadata['model'], 'qwen2.5:1.5b')

    def test_absent_ambiguous_remote_or_invalid_manifest_prevents_chat(self):
        invalid = [{'models': []}, {'models': [tags()['models'][0]] * 2},
                   {'models': None}, {'models': [None]}]
        for field, value in [('digest', 'invalid'), ('digest', None),
                             ('remote_host', 'https://example.invalid'), ('remote_model', 'cloud-model')]:
            item = tags()
            item['models'][0][field] = value
            invalid.append(item)
        for item in invalid:
            with self.subTest(item=item), patch('urllib.request.OpenerDirector.open', return_value=response(item)) as network:
                with self.assertRaises(ai.ReviewError):
                    ai.ollama_request(self.projection)
                self.assertEqual(network.call_count, 1)

    def test_incomplete_or_unexpected_envelopes_fail_closed(self):
        invalid = []
        for field, value in [('done', False), ('done', 1), ('done_reason', 'length'),
                             ('model', 'different:tag'), ('error', 'PRIVATE-BODY'),
                             ('prompt_eval_count', True), ('eval_count', -1),
                             ('eval_duration', None), ('load_duration', '1')]:
            item = envelope(self.candidate)
            item[field] = value
            invalid.append(item)
        for field, value in [('content', {}), ('role', 'user'), ('refusal', 'PRIVATE-BODY'),
                             ('tool_calls', [{'function': {'name': 'execute'}}])]:
            item = envelope(self.candidate)
            item['message'][field] = value
            invalid.append(item)
        invalid.extend([{}, [], None])
        for item in invalid:
            with self.subTest(item=item), patch('urllib.request.OpenerDirector.open',
                                               side_effect=[response(tags()), response(item)]):
                with self.assertRaises(ai.ReviewError) as caught:
                    ai.ollama_request(self.projection)
                self.assertNotIn('PRIVATE-BODY', str(caught.exception))

    def test_malformed_and_oversized_bytes_are_rejected_at_both_endpoints(self):
        for bad in (b'{', b'null', b'{"models":[],"models":[]}', b'x' * (ai.MAX_RESPONSE + 1)):
            for at_chat in (False, True):
                replies = ([response(tags())] if at_chat else []) + [io.BytesIO(bad)]
                with self.subTest(at_chat=at_chat, size=len(bad)), \
                        patch('urllib.request.OpenerDirector.open', side_effect=replies):
                    with self.assertRaises(ai.ReviewError):
                        ai.ollama_request(self.projection)

    def test_network_errors_are_sanitized_without_retry(self):
        errors = [TimeoutError('PRIVATE-BODY'), urllib.error.URLError('PRIVATE-BODY'),
                  urllib.error.HTTPError('http://127.0.0.1:11434', 500, 'PRIVATE-BODY', {}, io.BytesIO(b'PRIVATE-BODY'))]
        for error in errors:
            with self.subTest(error=type(error)), patch('urllib.request.OpenerDirector.open', side_effect=error) as network:
                with self.assertRaises(ai.ReviewError) as caught:
                    ai.ollama_request(self.projection)
                self.assertNotIn('PRIVATE-BODY', str(caught.exception))
                self.assertEqual(network.call_count, 1)
        with self.assertRaises(ai.ReviewError):
            ai.NoRedirect().redirect_request(None, None, 307, 'redirect', {}, 'https://evil.invalid')

    def test_all_adversarial_candidates_still_fail_in_ollama_mode(self):
        for name, candidate in evaluation.mutations(self.candidate):
            with self.subTest(name=name), patch('urllib.request.OpenerDirector.open',
                                              side_effect=[response(tags()), response(envelope(candidate))]):
                with self.assertRaises(ai.ReviewError):
                    ai.run_review(payload(), 'ollama')

    def test_evaluation_counts_successes_failures_and_tokens_honestly(self):
        calls = 0
        def intercepted(request, timeout):
            nonlocal calls
            if request.full_url.endswith('/api/tags'):
                return response(tags())
            calls += 1
            if calls == 2:
                raise TimeoutError('PRIVATE-BODY')
            projection = json.loads(json.loads(request.data)['messages'][1]['content'])['input']
            return response(envelope(ai.baseline(projection)))
        with patch('urllib.request.OpenerDirector.open', side_effect=intercepted):
            result = evaluation.evaluate('ollama')
        self.assertEqual(calls, 12)
        self.assertTrue(result['live_inference_requested'])
        self.assertEqual(result['successful_live_responses'], 11)
        self.assertEqual(result['cases_passed'], 11)
        self.assertEqual(result['total_tokens'], 1650)
        self.assertEqual(result['adversarial_probes_rejected'], 13)
        self.assertNotIn('PRIVATE-BODY', json.dumps(result))

    def test_cli_preserves_policy_exit_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            output = str(Path(folder) / 'review')
            args = [str(ROOT / 'examples/plans/destructive.json'), '--provider', 'ollama', '--output-dir', output]
            def intercepted(request, timeout):
                if request.full_url.endswith('/api/tags'):
                    return response(tags())
                projection = json.loads(json.loads(request.data)['messages'][1]['content'])['input']
                return response(envelope(ai.baseline(projection)))
            with patch('urllib.request.OpenerDirector.open', side_effect=intercepted):
                self.assertEqual(ai.main(args), 1)
            saved = json.loads((Path(output) / 'review.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['provider']['source'], 'ollama')
            with patch('urllib.request.OpenerDirector.open') as network:
                self.assertEqual(ai.main(args), 2)
                network.assert_not_called()
            args[-1] = str(Path(folder) / 'failed')
            with patch('urllib.request.OpenerDirector.open', side_effect=TimeoutError('PRIVATE-BODY')):
                self.assertEqual(ai.main(args), 2)
            self.assertFalse(Path(args[-1]).exists())

    def test_invalid_plan_does_not_connect(self):
        with patch('urllib.request.OpenerDirector.open') as network:
            with self.assertRaises(ai.ReviewError):
                ai.run_review(b'{', 'ollama')
            network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
