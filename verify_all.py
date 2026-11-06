#!/usr/bin/env python3
"""Check package integrity and reconstruct the included computational evidence."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
VERSION = '1.0.0'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def included_file(path):
    relative = path.relative_to(ROOT)
    return (path.is_file() and '.git' not in relative.parts
            and '__pycache__' not in relative.parts and path.suffix != '.pyc'
            and relative.as_posix() != 'MANIFEST.json')


def check_manifest():
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text(encoding='utf-8'))
    require(manifest['version'] == VERSION, 'Package version differs from the runner')
    expected = manifest['files_sha256']
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if included_file(p)}
    require(actual == set(expected), 'Package membership differs: missing=' + str(sorted(set(expected)-actual))
            + ', extra=' + str(sorted(actual-set(expected))))
    for relative, digest in expected.items():
        name = PurePosixPath(relative)
        require(not name.is_absolute() and '..' not in name.parts and name.as_posix() == relative,
                'Invalid manifest path: ' + relative)
        path = ROOT / relative
        require(not path.is_symlink() and ROOT in path.resolve().parents,
                'File leaves the package: ' + relative)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'Changed file: ' + relative)
    return len(expected)


def run_json(work, relative, cwd=None):
    result = subprocess.run([sys.executable, str(work / relative)], cwd=cwd or work,
                            text=True, capture_output=True)
    require(result.returncode == 0, relative + ' failed:\n' + result.stdout + result.stderr)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integrity-only', action='store_true', help='Check the full file inventory without running reconstructions')
    args = parser.parse_args()
    require(sys.version_info >= (3, 11), 'Python 3.11 or later is required')
    count = check_manifest()
    print(f'{VERSION} manifest checked: {count} files', flush=True)
    if args.integrity_only:
        print('Package integrity PASS', flush=True)
        return
    with tempfile.TemporaryDirectory(prefix='categorical-decision-audit-') as directory:
        work = Path(directory) / 'package'
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'))
        retained = run_json(work, 'verify.py')
        require(retained['b1']['independent_fixture_action_checks'] == 96 and retained['b1']['matched_pairs'] == 288,
                'B1 verification scope differs')
        require(retained['historical']['historical_requests'] == 2960 and retained['historical']['worked_case_worlds'] == 150,
                'Historical verification scope differs')
        h11 = run_json(work, 'h11/verify_h11.py')
        require(h11['status'] == 'PASS' and h11['cases_reconstructed_from_raw_sql'] == 128
                and h11['claims_independently_labelled'] == 1024 and h11['observations_checked'] == 6144
                and h11['arm_endpoint_reports_checked'] == 24, 'Car Evaluation verification scope differs')
        wine = run_json(work, 'wine/scripts/verify_transfer_bank.py', work / 'wine')
        require(wine['status'] == 'PASS' and wine['cases'] == 36 and wine['exact_group_scores'] == 432
                and wine['target_answers'] == 108 and len(wine['mutations']) == 16
                and all(p['detected'] for p in wine['mutations']), 'Wine transfer verification scope differs')
        sensitivity = run_json(work, 'wine_sensitivity/verify_sensitivity.py', work / 'wine_sensitivity')
        require(sensitivity['status'] == 'PASS' and sensitivity['candidate_classifications_compared'] == 144
                and sensitivity['block_rankings_compared'] == 72
                and sensitivity['group_count_score_payloads_compared'] == 432,
                'Wine sensitivity verification scope differs')
    print(json.dumps({'status': 'PASS', 'version': VERSION, 'manifest_files_checked': count,
                      'retained_projections': retained, 'car_evaluation': h11,
                      'wine_transfer': wine, 'wine_sensitivity': sensitivity}, indent=2), flush=True)
    print(f'{VERSION} verification PASS', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print('Verification FAIL: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
