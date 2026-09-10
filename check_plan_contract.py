"""Check the reviewer against real Terraform JSON without cloud resources.

Only a built-in terraform_data resource is applied in a temporary local state.
No provider download, provisioner, Azure credential or network resource is used.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import plan_review


def terraform(folder, *arguments):
    """Use the real CLI with a bounded wait; never evaluate shell commands."""
    result = subprocess.run(['terraform', f'-chdir={folder}', *arguments],
                            stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise RuntimeError(f'Terraform {arguments[0]} failed: {result.stderr[-2000:]}')
    return result.stdout


def main():
    root = Path(__file__).resolve().parent
    observations = []
    with tempfile.TemporaryDirectory(prefix='terraform-plan-contract-') as folder:
        temporary = Path(folder)
        (temporary / 'main.tf').write_text(
            'terraform { required_version = ">= 1.9, < 2.0" }\n'
            'resource "terraform_data" "example" { input = "synthetic-local-state" }\n')
        terraform(folder, 'init', '-backend=false', '-input=false', '-no-color')
        for name, flags, expected in (
            ('create', [], 0), ('unchanged', [], 0),
            ('replace', ['-replace=terraform_data.example'], 1),
            ('destroy', ['-destroy'], 1),
        ):
            terraform(folder, 'plan', '-input=false', '-no-color', '-out=case.tfplan', *flags)
            source = temporary / 'case.json'
            source.write_text(terraform(folder, 'show', '-json', 'case.tfplan'), encoding='utf-8')
            report = root / f'reports/plan-review/contract-{name}.md'
            result = subprocess.run([sys.executable, str(root / 'plan_review.py'), str(source),
                                     '--output', str(report)], capture_output=True, text=True, check=False)
            if result.returncode != expected:
                raise RuntimeError(f'{name}: expected review exit {expected}, got {result.returncode}: {result.stderr}')
            parsed = plan_review.review(source.read_bytes())
            category = {'create': 'create', 'unchanged': 'unchanged', 'replace': 'replace', 'destroy': 'delete'}[name]
            if parsed['counts'][category] != 1:
                raise RuntimeError(f'{name}: Terraform did not generate the intended action.')
            observations.append({'scenario': name, 'exit_code': result.returncode, 'status': parsed['status']})
            if name == 'create':
                # Apply only the provider-free fixture so later plans have a
                # genuine prior state. Replacements/destroy are planned only.
                terraform(folder, 'apply', '-input=false', '-no-color', 'case.tfplan')
    evidence = {'result': 'passed', 'scope': 'built-in terraform_data; temporary local state only',
                'observations': observations}
    plan_review.write_report(root / 'reports/plan-review/contract-evidence.json', json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__': main()
