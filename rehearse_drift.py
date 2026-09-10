"""Exercise actual Terraform drift detection on a disposable local file only.

No caller-supplied configuration, state, backend or resource path is accepted.
Recovery is opt-in and applies only a saved plan that passes the fixture's narrow
action/content checks. Reports contain selected observations and hashes; full
plans, state and command output stay inside the temporary execution directory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ADDRESS = 'local_file.service_config'
DESIRED = b'environment=synthetic\nlog_level=info\n'
CHANGED = b'environment=synthetic\nlog_level=debug\n'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_plan(document, expected_drift, expected_actions, creating=False):
    """Reject unexpected actions before reporting success or applying recovery.

    Terraform's exit 2 means a nonempty diff, not necessarily observed drift.
    Inspect resource_drift separately from resource_changes, and allow only the
    exact managed resource created by this rehearsal. A no-op is not a change.
    """
    if not isinstance(document, dict) or not str(document.get('format_version', '')).startswith('1.'):
        raise ValueError('Unsupported Terraform plan JSON format.')
    if document.get('errored') or document.get('output_changes'):
        raise ValueError('Unexpected plan error or output changes.')
    observed = {}
    for field, expected in (('resource_drift', expected_drift), ('resource_changes', expected_actions)):
        rows = document.get(field, [])
        if not isinstance(rows, list):
            raise ValueError(f'{field} must be a list.')
        actions = []
        for row in rows:
            if (row.get('address') != ADDRESS or row.get('mode') != 'managed'
                    or row.get('type') != 'local_file'
                    or row.get('provider_name') != 'registry.terraform.io/hashicorp/local'):
                raise ValueError(f'Unexpected resource in {field}.')
            action = row.get('change', {}).get('actions')
            if action != ['no-op']:
                actions.append(action)
        if actions != expected:
            raise ValueError(f'{field}: expected {expected}, observed {actions}.')
        observed[field] = actions
    if creating:
        # There must be exactly one create with concrete, known fixture values.
        # An action-only gate would wrongly accept a file at a different path or
        # with different content. Never apply an arbitrary user's plan here.
        rows = document.get('resource_changes', [])
        if len(rows) != 1:
            raise ValueError('Recovery must contain exactly one resource.')
        change = rows[0]['change']
        after = change.get('after') or {}
        unknown = change.get('after_unknown') or {}
        if (change['actions'] != ['create'] or change.get('before') is not None
                or after.get('filename') != './service.conf'
                or after.get('content') != DESIRED.decode('utf-8')
                or after.get('file_permission') != '0600'
                or any(unknown.get(key) for key in ('filename', 'content', 'file_permission'))):
            raise ValueError('Create plan does not match the approved local fixture.')
    return observed


def run_terraform(executable, folder, environment, arguments, expected=0):
    """Check native exit codes with bounded execution and no shell evaluation."""
    result = subprocess.run([executable, f'-chdir={folder}', *arguments],
                            env=environment, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding='utf-8',
                            timeout=180, check=False)
    if result.returncode != expected:
        # Only this synthetic configuration is executed, and inherited TF_* flags
        # and CLI credentials are excluded before launch. Keep diagnostics bounded.
        detail = (result.stderr or result.stdout)[-2500:]
        raise RuntimeError(f'Terraform {arguments[0]}: expected exit {expected}, '
                           f'got {result.returncode}. {detail}')
    return result.stdout


def rehearse(output, recover):
    executable = shutil.which('terraform')
    if not executable:
        raise RuntimeError('Terraform must be installed and available on PATH.')
    # Refuse reuse rather than mixing old successful evidence with a new failure.
    output.mkdir(parents=True, exist_ok=False)
    fixture = Path(__file__).resolve().parent / 'examples/drift'
    evidence = {'schema_version': 1, 'result': 'running',
                'started_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'disposable local_file; no Azure resources',
                'recovery_requested': recover, 'observations': []}
    with tempfile.TemporaryDirectory(prefix='terraform-drift-') as temporary:
        folder = Path(temporary)
        for name in ('main.tf', '.terraform.lock.hcl'):
            shutil.copyfile(fixture / name, folder / name)
        # Avoid inherited workspaces, injected arguments, remote data directories,
        # CLI credentials and dev overrides affecting an otherwise isolated root.
        environment = {key: value for key, value in os.environ.items()
                       if not key.upper().startswith('TF_')}
        cli_config = folder / 'terraform.rc'
        cli_config.write_text('disable_checkpoint = true\n', encoding='utf-8')
        environment.update(TF_CLI_CONFIG_FILE=str(cli_config), TF_IN_AUTOMATION='1',
                           CHECKPOINT_DISABLE='1')
        call = lambda *args, expected=0: run_terraform(executable, folder, environment, args, expected)
        version = json.loads(call('version', '-json'))
        evidence['terraform_version'] = version['terraform_version']
        evidence['configuration_sha256'] = digest((folder / 'main.tf').read_bytes())
        evidence['provider_lock_sha256'] = digest((folder / '.terraform.lock.hcl').read_bytes())
        call('init', '-backend=false', '-input=false', '-no-color', '-lockfile=readonly')

        def plan(name, code, drift, actions, *flags, creating=False):
            call('plan', '-input=false', '-no-color', '-detailed-exitcode',
                 f'-out={name}.tfplan', *flags, expected=code)
            raw = call('show', '-json', f'{name}.tfplan')
            observed = check_plan(json.loads(raw), drift, actions, creating)
            observed.update(phase=name, terraform_exit=code, plan_json_sha256=digest(raw.encode('utf-8')))
            evidence['observations'].append(observed)
            return digest((folder / f'{name}.tfplan').read_bytes())

        def apply_checked(name, checked_hash):
            # Apply the reviewed bytes rather than silently generating a new plan.
            if digest((folder / f'{name}.tfplan').read_bytes()) != checked_hash:
                raise RuntimeError('Saved plan changed after fixture checks.')
            call('apply', '-input=false', '-no-color', f'{name}.tfplan')

        initial = plan('initial', 2, [], [['create']], creating=True)
        apply_checked('initial', initial)
        target = folder / 'service.conf'
        if target.read_bytes() != DESIRED:
            raise RuntimeError('Initial apply did not write the expected content.')
        plan('baseline', 0, [], [])
        state_before = digest((folder / 'terraform.tfstate').read_bytes())
        target.write_bytes(CHANGED)
        evidence['file_hashes'] = {'before': digest(DESIRED), 'changed': digest(target.read_bytes())}

        # A refresh-only PLAN observes external changes without accepting them
        # into persisted state or repairing the file. Never apply this plan.
        plan('drift', 2, [['delete']], [], '-refresh-only')
        evidence['detection_preserved_state'] = state_before == digest((folder / 'terraform.tfstate').read_bytes())
        evidence['detection_preserved_changed_file'] = target.read_bytes() == CHANGED
        if not evidence['detection_preserved_state'] or not evidence['detection_preserved_changed_file']:
            raise RuntimeError('Detection unexpectedly changed state or the managed file.')
        if recover:
            recovery = plan('recovery', 2, [['delete']], [['create']], creating=True)
            apply_checked('recovery', recovery)
            if target.read_bytes() != DESIRED:
                raise RuntimeError('Recovery did not restore the original bytes.')
            evidence['file_hashes']['restored'] = digest(target.read_bytes())
            plan('clean', 0, [], [])
            teardown = plan('teardown', 2, [], [['delete']], '-destroy')
            apply_checked('teardown', teardown)
            if target.exists() or call('state', 'list').strip():
                raise RuntimeError('Terraform teardown left resources behind.')
            evidence['terraform_teardown_verified'] = True
        evidence['configuration_unchanged'] = evidence['configuration_sha256'] == digest((folder / 'main.tf').read_bytes())
        if not evidence['configuration_unchanged']:
            raise RuntimeError('Fixture configuration changed during the rehearsal.')
    # Publish a passing result only after TemporaryDirectory cleanup succeeds.
    evidence.update(result='passed', temporary_directory_removed=not folder.exists(),
                    finished_at=datetime.now(timezone.utc).isoformat())
    (output / 'drift-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    lines = ['# Local Terraform drift rehearsal', '', '**Result: passed**', '',
             'Scope: disposable local file; no Azure deployment or production recovery.', '',
             '| Phase | Terraform exit | Observed drift actions | Planned resource actions |',
             '| --- | ---: | --- | --- |']
    for row in evidence['observations']:
        drift = ', '.join('/'.join(a) for a in row['resource_drift']) or 'none'
        actions = ', '.join('/'.join(a) for a in row['resource_changes']) or 'none'
        lines.append(f"| {row['phase']} | {row['terraform_exit']} | {drift} | {actions} |")
    lines += ['', 'The file was changed outside Terraform. The local provider reports the content',
              'mismatch as a deleted managed object; the on-disk file still existed.',
              'Detection preserved both persisted state and the changed file.', '']
    if recover:
        lines += ['Recovery passed fixture-specific checks, applied the saved plan, restored the',
                  'original bytes and reached a clean plan. Terraform teardown was verified.']
    else:
        lines.append('Recovery was not requested; the temporary fixture was removed without repair.')
    lines += ['', 'These automated fixture checks are not human approval for production recovery.',
              'All temporary files, plans and state were removed. Full plan/state data is not published.', '']
    (output / 'drift-report.md').write_text('\n'.join(lines), encoding='utf-8')
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('reports/drift-demo'))
    parser.add_argument('--recover-local-fixture', action='store_true',
                        help='Also check and apply recovery of the fixed disposable file, then verify teardown.')
    args = parser.parse_args(argv)
    try:
        evidence = rehearse(args.output_dir, args.recover_local_fixture)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'Drift rehearsal failed: {error}', file=sys.stderr)
        return 2
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
