"""Evidence-bound AI review questions for Terraform plans (Python 3.12+).

The existing action policy remains authoritative. The optional model selects
questions from a fixed catalogue; local code supplies factual explanations and
checks every model-echoed fact. No arbitrary model prose or commands are rendered.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

import plan_review

VERSION = 'ai-review-v1'
# Version the local request separately: the evidence and response contracts are
# unchanged, but measurements must distinguish the revised model instructions.
OLLAMA_REQUEST_VERSION = 'ollama-review-v3'
MAX_RESOURCES = 20
MAX_RESPONSE = 128 * 1024
QUESTIONS = {
    'dependencies': 'Which dependent services need verification before and after this change?',
    'recovery': 'What tested recovery procedure and retained data are available if this change fails?',
    'cutover': 'How will cutover and temporary capacity be verified before the old object is removed?',
    'interruption': 'What interruption window is acceptable when destruction precedes creation?',
    'verification': 'Which functional and monitoring checks will confirm the intended result?',
    'unknowns': 'Which values remain unresolved, and how will they be checked before proceeding?',
    'state': 'What are the state and refresh implications of this data-source action?',
}
EXPLANATIONS = {
    'unchanged': 'No resource action is listed. This does not prove the wider deployment is safe.',
    'create': 'An object is planned for creation. Dependencies and the resulting behavior require verification.',
    'read': 'A data read is planned. Check when values become available and how they are consumed.',
    'update': 'An in-place update is planned. Action metadata alone cannot establish whether service will be interrupted.',
    'delete': 'Removal is planned. Check dependencies, retained data and recovery before proceeding.',
    'replace': 'Replacement includes removal of the old object. Review ordering, dependencies and recovery.',
}
PROMPT = '''You select review questions for a human Terraform reviewer.
Return one finding per evidence record, including unchanged resources. Copy its
evidence_id, category and unknown_values exactly. Select one to four distinct
question IDs from the supplied catalogue that suit the action and mode. You may
prioritize their order. Use unknowns when unknown_values is present. Use recovery
for managed delete/replace, interruption for managed delete-before-create, and
cutover for managed create-before-delete. Data sources use state rather than
infrastructure recovery. No tools, commands, deployment approvals or free text.
The evidence contains only aliases, enums and boolean-derived status. You have no
resource attributes, dependency graph, costs or live service observations.'''
SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['findings'],
    'properties': {'findings': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False,
        'required': ['evidence_id', 'category', 'unknown_values', 'questions'],
        'properties': {
            'evidence_id': {'type': 'string'},
            'category': {'type': 'string', 'enum': list(EXPLANATIONS)},
            'unknown_values': {'type': 'string', 'enum': ['present', 'none_marked', 'not_reported']},
            'questions': {'type': 'array', 'items': {'type': 'string', 'enum': list(QUESTIONS)}},
        },
    }}},
}


class ReviewError(ValueError):
    """A safe fixed diagnostic; raw inputs and HTTP error bodies are never echoed."""


def parse_json(payload):
    """Reject duplicate keys, nonstandard constants, invalid UTF-8 and deep JSON."""
    try:
        return json.loads(payload, object_pairs_hook=plan_review.unique_object,
                          parse_constant=plan_review.reject_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ReviewError('Invalid or ambiguous JSON.') from error


def read_bytes(path, limit):
    with Path(path).open('rb') as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ReviewError('Input exceeds the supported size limit.')
    return value


def unknown_status(change):
    """Inspect boolean shape only, never names or attribute values.

    Missing metadata is distinct from an explicit tree containing no true flags.
    Traverse iteratively with a node cap; malformed metadata fails closed instead
    of silently implying known values. Terraform permits nested objects/lists.
    """
    if 'after_unknown' not in change:
        return 'not_reported'
    stack, found, count = [change['after_unknown']], False, 0
    while stack:
        item = stack.pop()
        count += 1
        if count > 10000:
            raise ReviewError('Unknown-value metadata exceeds the node limit.')
        if type(item) is bool:
            found |= item
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        else:
            raise ReviewError('Unknown-value metadata must contain booleans, objects or arrays.')
    return 'present' if found else 'none_marked'


def prepare(payload):
    """Return a provider-safe projection and a local-only evidence map.

    Reuse the existing destructive-action gate verbatim. Addresses, deposed keys,
    plan hashes, types, variables, outputs, before/after values and arbitrary
    strings never enter the outbound object. Aliases are local to this request.
    """
    if len(payload) > plan_review.MAX_BYTES:
        raise ReviewError('Plan exceeds the 10 MiB limit.')
    try:
        gate = plan_review.review(payload)
    except plan_review.InvalidPlan as error:
        raise ReviewError('Plan failed the existing action-policy input contract.') from error
    plan = parse_json(payload)
    if len(gate['resources']) > MAX_RESOURCES:
        raise ReviewError('This release supports at most 20 resource objects; no truncation is performed.')
    changes = {(r['address'], r.get('deposed', '')): (i, r['change'])
               for i, r in enumerate(plan.get('resource_changes', []))}
    evidence, local = [], {}
    for index, resource in enumerate(gate['resources'], start=1):
        evidence_id = f'R{index:03d}'
        source_index, change = changes[(resource['address'], resource['deposed'])]
        record = {'evidence_id': evidence_id, 'mode': resource['mode'],
                  'actions': resource['actions'], 'category': resource['category'],
                  'unknown_values': unknown_status(change)}
        evidence.append(record)
        local[evidence_id] = {'address': resource['address'], 'deposed': resource['deposed'],
                              'json_pointer': f'/resource_changes/{source_index}/change'}
    return {'version': VERSION, 'evidence': evidence}, {'gate': gate, 'evidence_map': local}


def question_rules(record):
    """Define conservative relevance and required coverage independently of AI."""
    allowed = {'dependencies', 'verification'}
    required = set()
    if record['unknown_values'] == 'present':
        allowed.add('unknowns')
        required.add('unknowns')
    if record['mode'] == 'data':
        allowed.add('state')
        required.add('state')
    elif record['category'] in ('delete', 'replace'):
        allowed.add('recovery')
        required.add('recovery')
        if record['actions'] == ['delete', 'create']:
            allowed.add('interruption')
            required.add('interruption')
        elif record['actions'] == ['create', 'delete']:
            allowed.add('cutover')
            required.add('cutover')
    return allowed, required


def baseline(projection):
    """Deterministic baseline, explicitly not a model response or AI evaluation."""
    findings = []
    for record in projection['evidence']:
        _, required = question_rules(record)
        questions = sorted(required) + ['verification']
        findings.append({k: record[k] for k in ('evidence_id', 'category', 'unknown_values')} |
                        {'questions': questions})
    return {'findings': findings}


def validate_response(value, projection):
    """Check complete evidence coverage, exact facts and catalogue constraints.

    Schema-constrained generation is not trusted on its own. Application checks
    reject omitted resources, mismatched unknown flags, fabricated citations,
    irrelevant questions and additional prose/approval fields before rendering.
    """
    if not isinstance(value, dict) or set(value) != {'findings'} or not isinstance(value['findings'], list):
        raise ReviewError('Response must contain only a findings array.')
    evidence = {r['evidence_id']: r for r in projection['evidence']}
    seen = set()
    for finding in value['findings']:
        if not isinstance(finding, dict) or set(finding) != {'evidence_id', 'category', 'unknown_values', 'questions'}:
            raise ReviewError('Finding contains missing or unsupported fields.')
        identity = finding['evidence_id']
        if not isinstance(identity, str) or identity not in evidence or identity in seen:
            raise ReviewError('Finding has an invented or duplicate evidence reference.')
        record = evidence[identity]
        if finding['category'] != record['category'] or finding['unknown_values'] != record['unknown_values']:
            raise ReviewError('Finding contradicts deterministic evidence.')
        questions = finding['questions']
        if (not isinstance(questions, list) or not 1 <= len(questions) <= 4 or
                not all(isinstance(q, str) for q in questions) or len(set(questions)) != len(questions)):
            raise ReviewError('Finding needs one to four distinct catalogue questions.')
        allowed, required = question_rules(record)
        if not set(questions) <= allowed or not required <= set(questions):
            raise ReviewError('Finding has irrelevant questions or omits required review questions.')
        seen.add(identity)
    if seen != set(evidence):
        raise ReviewError('Response omits resource evidence.')
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward credential-bearing inference requests to another URL."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReviewError('Provider redirects are not accepted.')


def azure_request(projection, environment=None):
    """Use documented Azure v1 REST without a client SDK or implicit retries.

    Credentials are read only when live mode is selected. Support the public
    Azure OpenAI host shape exclusively, normal TLS verification, no proxy env
    inheritance and a 30-second socket timeout. Each invocation sends one request.
    """
    env = os.environ if environment is None else environment
    endpoint = env.get('AZURE_OPENAI_ENDPOINT', '')
    deployment = env.get('AZURE_OPENAI_DEPLOYMENT', '')
    key = env.get('AZURE_OPENAI_API_KEY', '')
    if not re.fullmatch(r'https://[a-z0-9][a-z0-9-]{0,62}\.openai\.azure\.com/?', endpoint):
        raise ReviewError('Set AZURE_OPENAI_ENDPOINT to your HTTPS Azure OpenAI resource origin.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', deployment) or not key or not key.isascii() or not key.isprintable():
        raise ReviewError('Set valid AZURE_OPENAI_DEPLOYMENT and AZURE_OPENAI_API_KEY values in the environment.')
    request_body = {
        'model': deployment, 'max_completion_tokens': 4096,
        'messages': [{'role': 'system', 'content': PROMPT},
                     {'role': 'user', 'content': json.dumps({'input': projection, 'catalogue': QUESTIONS})}],
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'terraform_review_questions', 'strict': True, 'schema': SCHEMA}},
    }
    encoded = json.dumps(request_body).encode('utf-8')
    request = urllib.request.Request(endpoint.rstrip('/') + '/openai/v1/chat/completions',
                                     data=encoded, headers={'Content-Type': 'application/json', 'api-key': key}, method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    started = time.monotonic()
    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ReviewError('Provider response exceeds 128 KiB.')
        envelope = parse_json(raw)
        choices = envelope['choices']
        if not isinstance(choices, list) or len(choices) != 1:
            raise ReviewError('Provider must return exactly one completion.')
        choice = choices[0]
        message = choice['message']
        if choice['finish_reason'] != 'stop' or message.get('refusal') or message.get('tool_calls'):
            raise ReviewError('Provider returned a refusal, tool call or incomplete completion.')
        content = message['content']
        if not isinstance(content, str):
            raise ReviewError('Provider completion must contain JSON text.')
        result = parse_json(content)
        usage = envelope.get('usage', {})
        tokens = {k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
        if any(type(v) is not int or v < 0 for v in tokens.values()):
            raise ReviewError('Provider did not return valid token usage.')
        if tokens['total_tokens'] != tokens['prompt_tokens'] + tokens['completion_tokens']:
            raise ReviewError('Provider token usage is inconsistent.')
        model = envelope.get('model')
        if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', model):
            raise ReviewError('Provider returned invalid model metadata.')
        return result, {'source': 'azure', 'model': model, 'deployment': deployment,
                        'latency_ms': round((time.monotonic() - started) * 1000),
                        'request_bytes': len(encoded), 'usage': tokens}
    except ReviewError:
        raise
    except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        raise ReviewError('Azure inference failed; check endpoint, credentials, deployment support and connectivity.') from error


def ollama_schema(projection):
    """Require every generated evidence ID in the local wire response.

    An unconstrained findings array allowed the model to stop after a subset of
    resources. Named required properties express coverage to the grammar itself.
    Only aliases and validated enums enter this schema; raw plan strings do not.
    Mandatory question membership and uniqueness remain application checks.
    """
    properties = {}
    for record in projection['evidence']:
        allowed, required = question_rules(record)
        fields = {name: {'type': 'string', 'enum': [record[name]]}
                  for name in ('evidence_id', 'category', 'unknown_values')}
        fields['questions'] = {
            'type': 'array', 'minItems': max(1, len(required)), 'maxItems': 4,
            'items': {'type': 'string', 'enum': sorted(allowed)},
        }
        properties[record['evidence_id']] = {
            'type': 'object', 'additionalProperties': False,
            'required': list(fields), 'properties': fields,
        }
    return {
        'type': 'object', 'additionalProperties': False, 'required': ['findings'],
        'properties': {'findings': {
            'type': 'object', 'additionalProperties': False,
            'required': list(properties), 'properties': properties,
        }},
    }


def normalize_ollama_response(value, projection):
    """Validate wire coverage before losslessly restoring the public list shape.

    Never fill omitted entries, discard extra entries or repair model facts.
    The usual response validator still checks every finding after conversion.
    JSON parsing has already rejected duplicate object keys at every depth.
    """
    if (not isinstance(value, dict) or set(value) != {'findings'} or
            not isinstance(value['findings'], dict)):
        raise ReviewError('Ollama response must contain an evidence-keyed findings object.')
    identities = [record['evidence_id'] for record in projection['evidence']]
    findings = value['findings']
    if set(findings) != set(identities):
        raise ReviewError('Ollama response has missing or unexpected resource evidence.')
    for identity in identities:
        if not isinstance(findings[identity], dict) or findings[identity].get('evidence_id') != identity:
            raise ReviewError('Ollama finding does not match its resource evidence key.')
    return {'findings': [findings[identity] for identity in identities]}


def ollama_request(projection, environment=None):
    """Call an installed small model through a trusted loopback Ollama daemon.

    No pulls, credentials, proxies, redirects or remote endpoint overrides.
    The installed manifest digest is server-reported provenance, not attestation.
    Disable cloud in the daemon too; a loopback address alone cannot enforce it.
    """
    env = os.environ if environment is None else environment
    model = env.get('OLLAMA_MODEL', 'qwen2.5:3b')
    if model not in ('qwen2.5:3b', 'qwen2.5:1.5b'):
        raise ReviewError('OLLAMA_MODEL must be qwen2.5:3b or qwen2.5:1.5b, installed locally.')
    origin = 'http://127.0.0.1:11434'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def receive(request, timeout):
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ReviewError('Provider response exceeds 128 KiB.')
        return parse_json(raw)

    try:
        tags = receive(urllib.request.Request(origin + '/api/tags'), 10)
        models = tags['models']
        if not isinstance(models, list) or not all(isinstance(item, dict) for item in models):
            raise ReviewError('Ollama returned an invalid installed-model list.')
        matches = [item for item in models if item.get('name') == model]
        if len(matches) != 1:
            raise ReviewError('Selected model is not installed; use the documented ollama pull command.')
        installed = matches[0]
        digest = installed.get('digest')
        if (installed.get('remote_model') or installed.get('remote_host') or
                not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise ReviewError('Ollama must report a local model with a valid manifest digest.')
        # Derive per-resource guidance from the same deterministic rules used
        # after inference. A small model previously confused the two replacement
        # orders when given only the general prose instructions. These lists
        # contain generated aliases and catalogue IDs, never raw plan strings.
        constraints = []
        for record in projection['evidence']:
            allowed, required = question_rules(record)
            constraints.append({'evidence_id': record['evidence_id'],
                                'allowed_questions': sorted(allowed),
                                'required_questions': sorted(required)})
        instructions = PROMPT + '''
For each evidence_id, use its matching question_constraints entry. Include EVERY
required_questions ID and select ONLY from that entry's allowed_questions IDs.
An empty required_questions list still requires at least one allowed question.
The lists apply separately to each resource: do not transfer a question from one
replacement to another. cutover and interruption are not interchangeable. Return
only findings using the response schema; do not echo the constraint fields.
findings MUST be an object keyed by EVERY input evidence_id, not an array.
Include unchanged resources too. Each value must contain its matching evidence_id,
category, unknown_values and questions. For zero evidence records, return an empty
findings object. Do not stop after a subset of resources.'''
        schema = ollama_schema(projection)
        options = {'temperature': 0, 'seed': 42, 'num_ctx': 8192, 'num_predict': 2048}
        body = {
            'model': model, 'stream': False, 'format': schema, 'options': options, 'keep_alive': '5m',
            'messages': [{'role': 'system', 'content': instructions},
                         {'role': 'user', 'content': json.dumps({
                             'request_version': OLLAMA_REQUEST_VERSION,
                             'input': projection, 'catalogue': QUESTIONS,
                             'question_constraints': constraints, 'response_schema': schema})}],
        }
        encoded = json.dumps(body).encode('utf-8')
        request = urllib.request.Request(origin + '/api/chat', data=encoded,
                                         headers={'Content-Type': 'application/json'}, method='POST')
        started = time.monotonic()
        envelope = receive(request, 180)
        elapsed = round((time.monotonic() - started) * 1000)
        message = envelope['message']
        if (envelope.get('error') or envelope.get('done') is not True or
                envelope.get('done_reason') != 'stop' or envelope.get('model') != model or
                message.get('role') != 'assistant' or message.get('tool_calls') or
                message.get('refusal')):
            raise ReviewError('Ollama returned an incomplete, unexpected or unsupported completion.')
        content = message['content']
        if not isinstance(content, str):
            raise ReviewError('Provider completion must contain JSON text.')
        counts = [envelope.get(k) for k in ('prompt_eval_count', 'eval_count')]
        durations = {k: envelope.get(k) for k in
                     ('total_duration', 'load_duration', 'prompt_eval_duration', 'eval_duration')}
        if any(type(v) is not int or v < 0 for v in counts + list(durations.values())):
            raise ReviewError('Ollama did not return valid token counts and timings.')
        return normalize_ollama_response(parse_json(content), projection), {
            'source': 'ollama', 'live_inference': True, 'model': model,
            'request_version': OLLAMA_REQUEST_VERSION,
            'installed_manifest_digest': digest, 'options': options,
            'latency_ms': elapsed, 'request_bytes': len(encoded), 'durations_ns': durations,
            'usage': {'prompt_tokens': counts[0], 'completion_tokens': counts[1],
                      'total_tokens': sum(counts)},
        }
    except ReviewError:
        raise
    except (OSError, urllib.error.URLError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        raise ReviewError('Local inference failed; check Ollama is running, the model is installed and memory is available.') from error


def run_review(payload, provider='baseline', response_payload=None):
    projection, local = prepare(payload)
    if provider == 'azure':
        value, metadata = azure_request(projection)
    elif provider == 'ollama':
        value, metadata = ollama_request(projection)
    elif provider == 'replay':
        value = parse_json(response_payload)
        metadata = {'source': 'replay', 'live_inference': False, 'usage': None, 'latency_ms': None}
    elif provider == 'baseline':
        value = baseline(projection)
        metadata = {'source': 'deterministic_baseline', 'live_inference': False, 'usage': None, 'latency_ms': None}
    else:
        raise ReviewError('Unsupported provider.')
    validate_response(value, projection)
    return {'version': VERSION, 'advisory_only': True, 'projection': projection,
            'gate': local['gate'], 'evidence_map': local['evidence_map'],
            'provider': metadata, 'response': value}


def markdown(result):
    """Render trusted explanations and escaped local addresses, never model prose."""
    gate = result['gate']
    lines = ['# AI-assisted Terraform review', '', f'Provider: {result["provider"]["source"]}', '',
             f'Deterministic policy: **{gate["status"]}**', '',
             'Advisory only. This report is not approval to apply.', '',
             f'Local input SHA-256: {gate["sha256"]}', '']
    if result['provider']['source'] not in ('azure', 'ollama'):
        lines += ['**Offline demonstration: no live model was called.**', '']
    for warning in gate['findings']:
        lines += [f'- {warning}']
    by_id = {r['evidence_id']: r for r in result['projection']['evidence']}
    for finding in result['response']['findings']:
        identity = finding['evidence_id']
        evidence = by_id[identity]
        local = result['evidence_map'][identity]
        lines += ['', f'## {identity} {plan_review.cell(local["address"])}', '',
                  f'Evidence: `{local["json_pointer"]}`; mode: {evidence["mode"]}; '
                  f'actions: {" -> ".join(evidence["actions"])}; unknown values: {evidence["unknown_values"]}.', '']
        if local['deposed']:
            lines += [f'Deposed object: {plan_review.cell(local["deposed"])}', '']
        explanation = ('This is a data-source action, not evidence of managed infrastructure destruction.'
                       if evidence['mode'] == 'data' else EXPLANATIONS[evidence['category']])
        lines += [explanation, '']
        lines += [f'- {QUESTIONS[q]}' for q in finding['questions']]
    lines += ['', 'Limits: no attribute analysis, dependency graph, cost estimate, live outage prediction, '
              'deployment execution or signature verification. Input hashes identify bytes but do not authenticate them.', '']
    return '\n'.join(lines)


def save_new(directory, result):
    """Require a fresh output directory; never overwrite input or prior evidence.

    JSON and Markdown contain local resource addresses. Keep these reports local
    for real plans. Only the separately written projection is sent to a model.
    """
    directory.mkdir(parents=True, exist_ok=False)
    outputs = {'review.json': result, 'outbound.json': result['projection']}
    for name, value in outputs.items():
        (directory / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    (directory / 'review.md').write_text(markdown(result), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--provider', choices=['baseline', 'replay', 'azure', 'ollama'], default='baseline')
    parser.add_argument('--response', type=Path, help='Reviewed JSON response for offline replay only')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output_dir.exists():
            raise ReviewError('Output directory already exists; choose a new directory.')
        if (args.provider == 'replay') != (args.response is not None):
            raise ReviewError('--response is required only for replay mode.')
        payload = read_bytes(args.plan, plan_review.MAX_BYTES)
        response = read_bytes(args.response, MAX_RESPONSE) if args.response else None
        result = run_review(payload, args.provider, response)
        save_new(args.output_dir, result)
        code = 1 if result['gate']['status'] == 'review_required' else 0
        print(f'AI review: {result["provider"]["source"]}; policy={result["gate"]["status"]}; exit={code}')
        return code
    except (ReviewError, OSError) as error:
        message = str(error) if isinstance(error, ReviewError) else 'Unable to read input or create a fresh output directory.'
        print(f'AI review failed: {message}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
