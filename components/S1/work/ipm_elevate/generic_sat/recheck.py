"""Replay the SAT/DRAT feasibility artifacts without importing a SAT solver."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from pilot import ENDPOINTS, check_drat, direct_change, encode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cases', 'artifact_directory', 'checker'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--expect-cases-sha256', required=True)
    args = parser.parse_args()
    data = args.cases.read_bytes()
    if sha256(data).hexdigest() != args.expect_cases_sha256:
        raise ValueError('Trusted case digest mismatch')
    cases = json.loads(data)
    run = json.loads((args.artifact_directory / 'results.json').read_text())
    if (run['cases_sha256'] != args.expect_cases_sha256 or run['cases'] != len(cases)
            or run['endpoints'] != len(cases) * len(ENDPOINTS)
            or set(run['records']) != {case['id'] for case in cases}):
        raise ValueError('Cohort receipt differs from trusted cases')
    checker = args.checker.resolve(strict=True)
    if sha256(checker.read_bytes()).hexdigest() != run['checker_sha256']:
        raise ValueError('Checker bytes differ from receipt')
    verified = Counter()
    for index, case in enumerate(cases, 1):
        entries = run['records'][case['id']]
        if set(entries) != set(ENDPOINTS):
            raise ValueError('Unexpected endpoints')
        for endpoint, entry in entries.items():
            status = entry['status']
            if status == 'invariant':
                base = f'{index:03d}_{endpoint}'
                if entry['artifact'] != base:
                    raise ValueError('Unexpected certificate path')
                parent = args.artifact_directory / 'certificates'
                dimacs_path = parent / f'{base}.cnf'
                proof_path = parent / f'{base}.drat'
                dimacs = dimacs_path.read_bytes()
                trace = proof_path.read_bytes()
                if (dimacs != encode(case, endpoint)[0].dimacs()
                        or sha256(dimacs).hexdigest() != entry['cnf_sha256']
                        or sha256(trace).hexdigest() != entry['proof_sha256']
                        or len(trace) != entry['proof_bytes']):
                    raise ValueError(f"Certificate binding failed for {case['id']} {endpoint}")
                ok, log = check_drat(checker, dimacs_path, proof_path)
                if not ok:
                    raise ValueError(f"Independent checker failed for {case['id']} {endpoint}: {log}")
            elif status == 'changed':
                if not direct_change(case, endpoint, entry['witness']):
                    raise ValueError(f"Witness does not separate {case['id']} {endpoint}")
            else:
                raise ValueError(f'Unexpected unresolved unit {case["id"]} {endpoint}')
            verified[status] += 1
    print(json.dumps({'cases_sha256': args.expect_cases_sha256, 'checked': dict(verified)}, sort_keys=True))


if __name__ == '__main__':
    main()
