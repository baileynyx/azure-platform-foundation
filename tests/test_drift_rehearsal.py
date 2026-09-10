"""Check failure boundaries; real provider behavior is exercised by the CI demo."""
import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rehearse_drift as drift


def resource(actions, after=None):
    return {'address': drift.ADDRESS, 'mode': 'managed', 'type': 'local_file',
            'provider_name': 'registry.terraform.io/hashicorp/local',
            'change': {'actions': actions, 'before': None, 'after': after,
                       'after_unknown': {}}}


def recovery():
    return {'format_version': '1.2', 'resource_drift': [resource(['delete'])],
            'resource_changes': [resource(['create'], {
                'filename': './service.conf', 'content': drift.DESIRED.decode(),
                'file_permission': '0600'})]}


class DriftBoundaryTests(unittest.TestCase):
    def test_observed_drift_and_proposed_actions_are_separate(self):
        plan = recovery()
        plan.pop('resource_changes')
        observed = drift.check_plan(plan, [['delete']], [])
        self.assertEqual(observed['resource_drift'], [['delete']])
        self.assertEqual(observed['resource_changes'], [])

    def test_configuration_only_change_does_not_count_as_drift(self):
        plan = recovery()
        plan.pop('resource_drift')
        with self.assertRaises(ValueError):
            drift.check_plan(plan, [['delete']], [['create']], creating=True)

    def test_native_error_is_not_accepted_as_expected_drift(self):
        # Exit 1 is a Terraform error; it must never be treated like exit 2.
        failed = subprocess.CompletedProcess([], 1, '', 'provider unavailable')
        with patch('rehearse_drift.subprocess.run', return_value=failed):
            with self.assertRaisesRegex(RuntimeError, 'expected exit 2, got 1'):
                drift.run_terraform('terraform', Path('.'), {}, ['plan'], expected=2)

    def test_recovery_rejects_changed_destination_content_or_extra_resource(self):
        for key, value in (('filename', '../outside.conf'), ('content', 'unexpected'),
                           ('file_permission', '0777')):
            with self.subTest(key=key):
                plan = recovery()
                plan['resource_changes'][0]['change']['after'][key] = value
                with self.assertRaises(ValueError):
                    drift.check_plan(plan, [['delete']], [['create']], creating=True)
        plan = recovery()
        extra = copy.deepcopy(plan['resource_changes'][0])
        extra['address'] = 'local_file.other'
        plan['resource_changes'].append(extra)
        with self.assertRaises(ValueError):
            drift.check_plan(plan, [['delete']], [['create']], creating=True)

    def test_recovery_rejects_destructive_or_update_actions(self):
        for actions in (['delete'], ['delete', 'create'], ['update']):
            with self.subTest(actions=actions):
                plan = recovery()
                plan['resource_changes'][0]['change']['actions'] = actions
                with self.assertRaises(ValueError):
                    drift.check_plan(plan, [['delete']], [['create']], creating=True)

    def test_recovery_requires_known_values(self):
        plan = recovery()
        plan['resource_changes'][0]['change']['after_unknown']['content'] = True
        with self.assertRaises(ValueError):
            drift.check_plan(plan, [['delete']], [['create']], creating=True)
        drift.check_plan(recovery(), [['delete']], [['create']], creating=True)

    def test_errored_or_unsupported_plan_is_not_evidence(self):
        for key, value in (('format_version', '2.0'), ('errored', True)):
            plan = recovery()
            plan[key] = value
            with self.assertRaises(ValueError):
                drift.check_plan(plan, [['delete']], [['create']], creating=True)

    def test_existing_output_is_preserved_before_any_terraform_call(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'drift-evidence.json'
            marker.write_text('previous evidence', encoding='utf-8')
            with patch('rehearse_drift.shutil.which', return_value='terraform'), \
                    patch('rehearse_drift.subprocess.run') as execute:
                with self.assertRaises(FileExistsError):
                    drift.rehearse(Path(folder), True)
                execute.assert_not_called()
            self.assertEqual(marker.read_text(encoding='utf-8'), 'previous evidence')


if __name__ == '__main__':
    unittest.main()
