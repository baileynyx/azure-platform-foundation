"""Evaluate the bounded review contract; offline results are not model scores.

The corpus contains explicit human-authored expected policy and unknown-value
labels. Each case is compared with those labels, then the candidate is checked
for evidence coverage and grounded facts. Adversarial response probes exercise
the validator separately and are never reported as model-generated failures.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

import ai_review as ai

CORPUS = Path(__file__).parent / 'examples/ai/evaluation-cases.json'


def mutations(valid):
    """Deliberately corrupt a valid candidate to test distinct trust boundaries."""
    cases = []
    for name, field, value in [
        ('invented_evidence', 'evidence_id', 'R999'),
        ('contradictory_action', 'category', 'unchanged'),
        ('hidden_unknowns', 'unknown_values', 'none_marked'),
        ('unsupported_question', 'questions', ['terraform apply -auto-approve']),
        ('missing_recovery', 'questions', ['verification', 'unknowns']),
        ('irrelevant_state_question', 'questions', ['recovery', 'unknowns', 'state']),
        ('wrong_replacement_order', 'questions', ['recovery', 'unknowns', 'cutover']),
        ('duplicate_questions', 'questions', ['recovery', 'recovery']),
        ('wrong_question_type', 'questions', [False]),
    ]:
        candidate = copy.deepcopy(valid)
        candidate['findings'][0][field] = value
        cases.append((name, candidate))
    candidate = copy.deepcopy(valid)
    candidate['approved'] = True
    cases.append(('approval_field', candidate))
    candidate = copy.deepcopy(valid)
    candidate['findings'][0]['explanation'] = 'There will be no downtime.'
    cases.append(('unverifiable_prose', candidate))
    candidate = copy.deepcopy(valid)
    candidate['findings'].append(copy.deepcopy(candidate['findings'][0]))
    cases.append(('duplicate_resource', candidate))
    cases.append(('omitted_resource', {'findings': []}))
    return cases


def evaluate(provider='baseline'):
    cases = json.loads(CORPUS.read_text(encoding='utf-8'))
    observations = []
    for case in cases:
        payload = json.dumps(case['plan']).encode('utf-8')
        try:
            result = ai.run_review(payload, provider)
            policy_match = result['gate']['status'] == case['expected_policy']
            unknown_match = [r['unknown_values'] for r in result['projection']['evidence']] == case['expected_unknowns']
            observations.append({'case': case['name'], 'passed': policy_match and unknown_match,
                                 'policy_matches_oracle': policy_match, 'unknowns_match_oracle': unknown_match,
                                 'candidate_contract_passed': True, 'provider': result['provider'],
                                 'candidate': result['response']})
        except ai.ReviewError:
            # Preserve failure counts, but not HTTP bodies, credentials or input
            # fragments. Other cases still run so one error cannot hide failures.
            observations.append({'case': case['name'], 'passed': False,
                                 'candidate_contract_passed': False})
    probe_case = next(c for c in cases if c['name'] == 'replace_unknown')
    projection, _ = ai.prepare(json.dumps(probe_case['plan']).encode())
    valid = ai.baseline(projection)
    probes = []
    for name, candidate in mutations(valid):
        try:
            ai.validate_response(candidate, projection)
            rejected = False
        except ai.ReviewError:
            rejected = True
        probes.append({'probe': name, 'rejected': rejected})
    token_samples = [o['provider']['usage'] for o in observations if o.get('provider', {}).get('usage')]
    return {
        'version': ai.VERSION, 'provider_mode': provider,
        'live_inference_requested': provider == 'azure',
        'successful_live_responses': sum(o.get('provider', {}).get('source') == 'azure' for o in observations),
        'interpretation': 'Contract checks on a small synthetic corpus; not evidence of operational benefit or general model quality.',
        'cases_passed': sum(o['passed'] for o in observations), 'case_count': len(observations),
        'adversarial_probes_rejected': sum(p['rejected'] for p in probes), 'adversarial_probe_count': len(probes),
        'total_tokens': sum(t['total_tokens'] for t in token_samples) if token_samples else None,
        'observations': observations, 'adversarial_probes': probes,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['baseline', 'azure'], default='baseline')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # Reserve the output first: an existing directory must not trigger paid
        # inference before the command discovers it cannot save the evidence.
        args.output_dir.mkdir(parents=True, exist_ok=False)
        report = evaluate(args.provider)
        (args.output_dir / 'evaluation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        passed = report['cases_passed'] == report['case_count'] and report['adversarial_probes_rejected'] == report['adversarial_probe_count']
        text = (f'# Terraform AI review evaluation\n\nMode: {args.provider}\n\n'
                f'Cases passed: {report["cases_passed"]}/{report["case_count"]}\n\n'
                f'Adversarial response probes rejected: {report["adversarial_probes_rejected"]}/{report["adversarial_probe_count"]}\n\n'
                f'Successful live responses: {report["successful_live_responses"]}\n\n'
                f'Total measured tokens: {report["total_tokens"]}\n\n{report["interpretation"]}\n')
        (args.output_dir / 'evaluation.md').write_text(text, encoding='utf-8')
        print(text)
        return 0 if passed else 1
    except (OSError, ValueError) as error:
        print('Evaluation failed: unable to read corpus or create fresh outputs.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
