"""Review saved Terraform plan JSON for destructive resource actions.

Exit 0 means this narrow policy found no destructive actions, never approval to
apply. Exit 1 requires review; exit 2 means the input could not be evaluated.
Resource attribute values are deliberately excluded from the Markdown report.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile

MAX_BYTES = 10 * 1024 * 1024
POLICY = 'destructive-actions-v1'
# Replacement order is significant: create-before-destroy still destroys an
# existing object. Never infer safety from the first element alone.
ACTIONS = {
    ('no-op',): ('unchanged', None),
    ('create',): ('create', None),
    ('read',): ('read', None),
    ('update',): ('update', None),
    ('delete',): ('delete', 'Object removal: review dependents, retained data and recovery before proceeding.'),
    ('delete', 'create'): ('replace', 'Destroy before create: review interruption, dependent resources and recovery.'),
    ('create', 'delete'): ('replace', 'Create before destroy still removes the old object: review cutover, capacity and recovery.'),
}


class InvalidPlan(ValueError):
    """The supported plan contract was not satisfied; block the gate."""


def unique_object(pairs):
    """Reject ambiguous duplicate JSON keys rather than accepting the last one."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidPlan('Duplicate JSON object keys are not supported.')
        result[key] = value
    return result


def reject_constant(value):
    raise InvalidPlan('Nonstandard JSON constants are not supported.')


def review(payload):
    """Validate the consumed schema and classify actions without reading values.

    Minor JSON-format additions are ignored. Unknown action combinations and
    major versions fail closed so new Terraform semantics cannot silently pass.
    A missing resource_changes array is valid for an empty/output-only plan.
    """
    try:
        plan = json.loads(payload.decode('utf-8-sig'), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except InvalidPlan:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InvalidPlan('Input must be a valid UTF-8 Terraform plan JSON document.') from error
    if not isinstance(plan, dict):
        raise InvalidPlan('Plan must be a JSON object.')
    version = plan.get('format_version')
    if not isinstance(version, str) or not re.fullmatch(r'1\.[0-9]+', version):
        raise InvalidPlan('Only Terraform plan JSON format major version 1 is supported.')
    if not isinstance(plan.get('terraform_version'), str) or not plan['terraform_version']:
        raise InvalidPlan('Missing Terraform version metadata.')
    # State exports use values, not planned_values plus configuration. Requiring
    # these plan markers catches accidentally supplied state and partial JSON.
    if not isinstance(plan.get('planned_values'), dict) or not isinstance(plan.get('configuration'), dict):
        raise InvalidPlan('Expected saved-plan JSON with planned_values and configuration.')
    for flag in ('complete', 'errored', 'applyable'):
        if flag in plan and type(plan[flag]) is not bool:
            raise InvalidPlan('Plan status fields must be booleans when present.')
    if plan.get('errored', False):
        raise InvalidPlan('Terraform reported an errored plan.')
    deferred = plan.get('deferred_changes', [])
    if not isinstance(deferred, list):
        raise InvalidPlan('deferred_changes must be an array when present.')
    changes = plan.get('resource_changes', [])
    if not isinstance(changes, list):
        raise InvalidPlan('resource_changes must be an array when present.')
    findings = []
    if plan.get('complete') is False:
        findings.append('Terraform marked this plan incomplete; review the remaining plan/apply work.')
    if deferred:
        findings.append('Deferred changes are present; the current action list is not the complete change set.')
    counts = dict.fromkeys(('unchanged', 'create', 'read', 'update', 'delete', 'replace'), 0)
    rows, seen = [], set()
    for index, resource in enumerate(changes):
        location = f'Resource change {index + 1}'
        if not isinstance(resource, dict):
            raise InvalidPlan(f'{location} must be an object.')
        address, mode = resource.get('address'), resource.get('mode')
        deposed = resource.get('deposed', '')
        if not isinstance(address, str) or not address or len(address) > 2048:
            raise InvalidPlan(f'{location} has an invalid address.')
        if mode not in ('managed', 'data') or not isinstance(deposed, str):
            raise InvalidPlan(f'{location} has an invalid mode or deposed key.')
        # Terraform permits a current and a deposed object at the same address.
        identity = (address, deposed)
        if identity in seen:
            raise InvalidPlan('Duplicate resource address and deposed key.')
        seen.add(identity)
        change = resource.get('change')
        actions = change.get('actions') if isinstance(change, dict) else None
        if not isinstance(actions, list) or not all(isinstance(a, str) for a in actions):
            raise InvalidPlan(f'{location} has invalid actions.')
        key = tuple(actions)
        if key not in ACTIONS:
            raise InvalidPlan(f'{location} has an unsupported action combination; review the policy before proceeding.')
        category, reason = ACTIONS[key]
        if mode == 'data' and reason:
            reason = 'Data-source removal or replacement: inspect state semantics; this is not evidence of managed infrastructure destruction.'
        counts[category] += 1
        rows.append({'address': address, 'deposed': deposed, 'mode': mode,
                     'actions': actions, 'category': category, 'reason': reason})
    rows.sort(key=lambda row: (row['address'], row['deposed']))
    blocked = bool(findings or any(row['reason'] for row in rows))
    return {'status': 'review_required' if blocked else 'no_destructive_changes',
            'sha256': hashlib.sha256(payload).hexdigest(), 'counts': counts,
            'findings': findings, 'resources': rows}


def cell(value):
    """Escape opaque addresses so plan strings cannot create Markdown or HTML."""
    text = html.escape(''.join(c if c.isprintable() else ' ' for c in value))
    for character in ('|', '`', '[', ']', '*', '_', '\\'):
        text = text.replace(character, f'&#{ord(character)};')
    return text


def markdown(result):
    titles = {'review_required': 'REVIEW REQUIRED', 'no_destructive_changes': 'NO DESTRUCTIVE CHANGES FOUND',
              'invalid_plan': 'INVALID OR UNSUPPORTED PLAN'}
    lines = ['# Terraform change review', '', f'**Result: {titles[result["status"]]}**', '',
             f'Policy: {POLICY}', '', f'Input JSON SHA-256: {result["sha256"]}', '',
             'This action review is not approval to apply. Resource values, variables and outputs are omitted.', '']
    if result['status'] == 'invalid_plan':
        return '\n'.join(lines + [cell(result['error']), ''])
    lines += ['## Summary', '', '| Action | Resource objects |', '| --- | ---: |']
    lines += [f'| {name} | {count} |' for name, count in result['counts'].items()]
    if result['findings']:
        lines += ['', '## Plan-level review', ''] + [f'- {finding}' for finding in result['findings']]
    lines += ['', '## Resource review', '', '| Address | Mode | Actions | Decision and reason |', '| --- | --- | --- | --- |']
    for row in result['resources']:
        label = row['address'] + (f' (deposed: {row["deposed"]})' if row['deposed'] else '')
        decision = 'REVIEW: ' + row['reason'] if row['reason'] else 'No destructive action identified.'
        lines.append(f'| {cell(label)} | {row["mode"]} | {cell(" -> ".join(row["actions"]))} | {decision} |')
    if not result['resources']:
        lines.append('| None | — | — | No resource changes listed. |')
    lines += ['', 'Limits: updates can still disrupt service. This policy does not evaluate attribute values, cost,',
              'network reachability, drift, output changes or Terraform check results. It does not authenticate',
              'the JSON or prove that a later apply uses the same saved plan.', '']
    return '\n'.join(lines)


def write_report(path, content):
    """Replace the report atomically, including rejected/invalid plan reports."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.plan-review-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path, help='Output of terraform show -json saved.tfplan')
    parser.add_argument('--output', type=Path, help='Markdown report path; otherwise print to stdout')
    args = parser.parse_args(argv)
    if args.output and args.output.resolve() == args.plan.resolve():
        parser.exit(2, 'Report path must not overwrite the input plan.\n')
    payload = b''
    try:
        with args.plan.open('rb') as stream:
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise InvalidPlan('Plan exceeds the 10 MiB input limit.')
        result = review(payload)
        code = 1 if result['status'] == 'review_required' else 0
    except (OSError, InvalidPlan) as error:
        # Do not echo raw JSON or OS paths: errors can contain private input.
        message = str(error) if isinstance(error, InvalidPlan) else 'Unable to read input plan.'
        result = {'status': 'invalid_plan', 'error': message,
                  'sha256': hashlib.sha256(payload).hexdigest() if len(payload) <= MAX_BYTES and payload else 'unavailable'}
        code = 2
    report = markdown(result)
    try:
        if args.output:
            write_report(args.output, report)
            print(f'Terraform change review: {result["status"]} (exit {code})')
        else:
            print(report, end='')
    except OSError:
        parser.exit(2, 'Unable to write the review report.\n')
    return code


if __name__ == '__main__': sys.exit(main())
