"""Exercise destructive decisions, unsupported inputs and the public CLI."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import plan_review

ROOT = Path(__file__).resolve().parents[1]


def plan(*actions):
    """Small synthetic plan envelope; attribute content is irrelevant to policy."""
    return {'format_version': '1.2', 'terraform_version': '1.9.8',
            'planned_values': {}, 'configuration': {},
            'resource_changes': [
                {'address': f'module.team_b.azurerm_subnet.example[{index}]', 'mode': 'managed',
                 'change': {'actions': list(action)}} for index, action in enumerate(actions)]}


def review(value):
    return plan_review.review(json.dumps(value).encode())


class PlanReviewTests(unittest.TestCase):
    def test_create_read_update_and_noop_pass_narrow_policy(self):
        result = review(plan(['create'], ['read'], ['update'], ['no-op']))
        self.assertEqual(result['status'], 'no_destructive_changes')
        self.assertEqual(sum(result['counts'].values()), 4)

    def test_delete_requires_review(self):
        result = review(plan(['delete']))
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['counts']['delete'], 1)

    def test_both_replacement_orders_require_review(self):
        for actions in (['delete', 'create'], ['create', 'delete']):
            with self.subTest(actions=actions):
                result = review(plan(actions))
                self.assertEqual(result['status'], 'review_required')
                self.assertEqual(result['counts']['replace'], 1)
                self.assertEqual(result['counts']['delete'], 0)

    def test_safe_rows_do_not_clear_an_earlier_blocker(self):
        self.assertEqual(review(plan(['delete'], ['create']))['status'], 'review_required')

    def test_empty_and_output_only_plans_pass(self):
        value = plan()
        del value['resource_changes']
        value['output_changes'] = {'example': {'actions': ['delete']}}
        self.assertEqual(review(value)['status'], 'no_destructive_changes')

    def test_unknown_actions_and_malformed_rows_fail_closed(self):
        for actions in ([], ['forget'], ['create', 'forget'], ['update', 'delete'], ['create', 'create'], [None], 'delete'):
            value = plan(['create'])
            value['resource_changes'][0]['change']['actions'] = actions
            with self.subTest(actions=actions), self.assertRaises(plan_review.InvalidPlan):
                review(value)
        for rows in (None, {}, [None], [{}]):
            value = plan()
            value['resource_changes'] = rows
            with self.subTest(rows=rows), self.assertRaises(plan_review.InvalidPlan):
                review(value)

    def test_format_minor_additions_allowed_major_changes_rejected(self):
        value = plan()
        value.update(format_version='1.99', future_field={'opaque': True})
        self.assertEqual(review(value)['status'], 'no_destructive_changes')
        for version in ('2.0', '0.1', None, 1, '1'):
            value['format_version'] = version
            with self.subTest(version=version), self.assertRaises(plan_review.InvalidPlan):
                review(value)

    def test_state_and_partial_documents_are_not_empty_plans(self):
        for value in ({}, [], {'format_version': '1.0', 'terraform_version': '1.9.8', 'values': {}},
                      {'format_version': '1.0', 'terraform_version': '1.9.8', 'planned_values': {}}):
            with self.subTest(value=value), self.assertRaises(plan_review.InvalidPlan):
                review(value)

    def test_errored_and_malformed_status_flags_are_invalid(self):
        for flag, value in (('errored', True), ('complete', 'true'), ('applyable', 1), ('errored', None)):
            document = plan()
            document[flag] = value
            with self.subTest(flag=flag, value=value), self.assertRaises(plan_review.InvalidPlan):
                review(document)

    def test_incomplete_and_deferred_plans_require_review(self):
        for fields in ({'complete': False}, {'deferred_changes': [{'reason': 'unknown'}]}):
            document = plan(['create'])
            document.update(fields)
            self.assertEqual(review(document)['status'], 'review_required')

    def test_duplicate_json_keys_nonstandard_numbers_and_bad_encoding_rejected(self):
        for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b'not-json', b'\xff'):
            with self.subTest(payload=payload), self.assertRaises(plan_review.InvalidPlan):
                plan_review.review(payload)

    def test_sensitive_values_never_enter_report(self):
        value = plan(['delete', 'create'])
        value['variables'] = {'password': {'value': 'SECRET-VARIABLE'}}
        value['output_changes'] = {'password': {'after': 'SECRET-OUTPUT'}}
        value['resource_changes'][0]['change'].update(
            before={'password': 'SECRET-BEFORE'}, after={'password': 'SECRET-AFTER'},
            before_sensitive={'password': True}, after_sensitive={'password': True})
        report = plan_review.markdown(review(value))
        self.assertNotIn('SECRET-', report)
        self.assertIn('REVIEW REQUIRED', report)

    def test_addresses_are_escaped_for_markdown_tables(self):
        value = plan(['delete'])
        value['resource_changes'][0]['address'] = 'module.x["a|b`[link](url)<img>\nrow"]'
        report = plan_review.markdown(review(value))
        self.assertIn('&#124;', report)
        self.assertNotIn('<img>', report)
        self.assertNotIn('[link](url)', report)
        self.assertNotIn('\nrow', report)

    def test_deposed_objects_are_distinct_but_duplicate_identity_is_invalid(self):
        value = plan(['no-op'])
        old = copy.deepcopy(value['resource_changes'][0])
        old.update(deposed='deadbeef', change={'actions': ['delete']})
        value['resource_changes'].append(old)
        self.assertEqual(review(value)['status'], 'review_required')
        value['resource_changes'].append(copy.deepcopy(old))
        with self.assertRaises(plan_review.InvalidPlan): review(value)

    def test_data_source_removal_is_not_described_as_infrastructure_destruction(self):
        value = plan(['delete'])
        value['resource_changes'][0]['mode'] = 'data'
        self.assertIn('Data-source removal', review(value)['resources'][0]['reason'])

    def test_utf8_bom_accepted_and_digest_identifies_exact_input(self):
        payload = b'\xef\xbb\xbf' + json.dumps(plan()).encode()
        self.assertEqual(plan_review.review(payload)['sha256'], hashlib.sha256(payload).hexdigest())

    def test_cli_exit_codes_reports_and_input_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            source, report = Path(folder) / 'plan.json', Path(folder) / 'review.md'
            for payload, code, status in ((json.dumps(plan(['create'])), 0, 'NO DESTRUCTIVE'),
                                          (json.dumps(plan(['create', 'delete'])), 1, 'REVIEW REQUIRED'),
                                          ('invalid', 2, 'INVALID OR UNSUPPORTED')):
                source.write_text(payload)
                result = subprocess.run([sys.executable, str(ROOT / 'plan_review.py'), str(source),
                                         '--output', str(report)], capture_output=True, text=True)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn(status, report.read_text())
                self.assertEqual(source.read_text(), payload)

    def test_cli_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'plan.json'
            source.write_text(json.dumps(plan()))
            before = source.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / 'plan_review.py'), str(source),
                                     '--output', str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_bytes(), before)

    def test_committed_examples_have_expected_results(self):
        for name, expected in (('safe', 'no_destructive_changes'), ('destructive', 'review_required')):
            result = plan_review.review((ROOT / f'examples/plans/{name}.json').read_bytes())
            self.assertEqual(result['status'], expected)


if __name__ == '__main__': unittest.main()
