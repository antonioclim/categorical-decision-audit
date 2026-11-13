"""Retrospective, independently checked SAT/DRUP feasibility on frozen DL21."""

import argparse
from collections import Counter
from functools import lru_cache
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import statistics
import subprocess
from time import perf_counter_ns

TRUE = 1
FALSE = -1
GRADES = range(4)
WEIGHTS = ((0, 0, 1, 1), (0, 1, 2, 3))
ENDPOINTS = ('set', 'prefix')


class Formula:
    def __init__(self):
        self.nvars = 1
        self.clauses = [(TRUE,)]
        self.mux_cache = {}

    def variable(self):
        self.nvars += 1
        return self.nvars

    def clause(self, *literals):
        cleaned = tuple(dict.fromkeys(lit for lit in literals if lit != FALSE))
        if TRUE not in cleaned and not any(-lit in cleaned for lit in cleaned):
            self.clauses.append(cleaned)

    def disjunction(self, literals):
        literals = tuple(dict.fromkeys(lit for lit in literals if lit != FALSE))
        if TRUE in literals or any(-lit in literals for lit in literals):
            return TRUE
        if not literals:
            return FALSE
        if len(literals) == 1:
            return literals[0]
        result = self.variable()
        self.clause(-result, *literals)
        for lit in literals:
            self.clause(result, -lit)
        return result

    def conjunction(self, literals):
        return -self.disjunction(-lit for lit in literals)

    def mux(self, decision, when_true, when_false):
        if decision == TRUE:
            return when_true
        if decision == FALSE:
            return when_false
        if when_true == when_false:
            return when_true
        if when_true == TRUE and when_false == FALSE:
            return decision
        if when_true == FALSE and when_false == TRUE:
            return -decision
        key = (decision, when_true, when_false)
        if key not in self.mux_cache:
            result = self.variable()
            self.clause(-decision, -when_true, result)
            self.clause(-decision, when_true, -result)
            self.clause(decision, -when_false, result)
            self.clause(decision, when_false, -result)
            self.mux_cache[key] = result
        return self.mux_cache[key]

    def xor(self, first, second):
        return self.mux(first, -second, second)

    def at_least(self, terms, threshold):
        """Return a literal for a signed integer threshold using a generic DP circuit."""
        positive = []
        for weight, literal in terms:
            if weight < 0:
                threshold -= weight
                positive.append((-weight, -literal))
            elif weight > 0:
                positive.append((weight, literal))
        suffix_max = [0] * (len(positive) + 1)
        for i in reversed(range(len(positive))):
            suffix_max[i] = suffix_max[i + 1] + positive[i][0]

        @lru_cache(maxsize=None)
        def possible(i, remaining):
            if remaining <= 0:
                return TRUE
            if remaining > suffix_max[i]:
                return FALSE
            weight, literal = positive[i]
            return self.mux(literal, possible(i + 1, remaining - weight),
                            possible(i + 1, remaining))

        return possible(0, threshold)

    def dimacs(self):
        header = f'p cnf {self.nvars} {len(self.clauses)}\n'
        body = ''.join(' '.join([*map(str, clause), '0']) + '\n' for clause in self.clauses)
        return (header + body).encode('ascii')


def case_data(case):
    known = case['known']
    unknown = tuple(sorted(case['unknown']))
    raw_runs = [case['runs'][name] for name in sorted(case['runs'])]
    runs = [frozenset(passages) for passages in raw_runs]
    if len(runs) != 4 or any(len(raw) != 10 or len(run) != 10 for raw, run in zip(raw_runs, runs)):
        raise ValueError('Expected four ten-passage runs')
    if len(set(unknown)) != len(unknown) or set(unknown) & set(known):
        raise ValueError('Unknown passage IDs must be distinct and disjoint')
    if set(known).union(unknown) != frozenset().union(*runs):
        raise ValueError('Known/unknown IDs must partition the run union')
    if any(type(g) is not int or g not in GRADES for g in known.values()):
        raise ValueError('Known grades must be integers 0 through 3')
    return known, unknown, runs


def encode(case, endpoint):
    known, unknown, runs = case_data(case)
    formula = Formula()
    grade_vars = {p: [formula.variable() for _ in GRADES] for p in unknown}
    for values in grade_vars.values():
        formula.clause(*values)
        for first, second in combinations(values, 2):
            formula.clause(-first, -second)
    orders = []
    for weights in WEIGHTS:
        ahead = {}
        for left, right in combinations(range(4), 2):
            # The smaller lexical index wins ties. Opposite order is exact complement.
            sign = {p: int(p in runs[left]) - int(p in runs[right])
                    for p in sorted(runs[left].symmetric_difference(runs[right]))}
            fixed = sum(multiplier * weights[known[p]] for p, multiplier in sign.items() if p in known)
            terms = [(multiplier * weights[g], grade_vars[p][g])
                     for p, multiplier in sign.items() if p in grade_vars for g in GRADES]
            ahead[left, right] = formula.at_least(terms, -fixed)
            ahead[right, left] = -ahead[left, right]
        orders.append(ahead)
    if endpoint == 'set':
        omitted = [[formula.conjunction(ahead[i, j] for i in range(4) if i != j)
                    for j in range(4)] for ahead in orders]
        changes = [formula.xor(left, right) for left, right in zip(*omitted)]
    elif endpoint == 'prefix':
        changes = [formula.xor(orders[0][i, j], orders[1][i, j])
                   for i, j in combinations(range(4), 2)]
    else:
        raise ValueError('Unrecognised endpoint')
    change = formula.disjunction(changes)
    if change == FALSE:
        # Represent a false assertion as contradictory units for checker portability.
        formula.clauses.append((FALSE,))
    else:
        formula.clause(change)
    return formula, grade_vars


def direct_change(case, endpoint, witness):
    known, unknown, runs = case_data(case)
    if set(witness) != set(unknown) or any(type(g) is not int or g not in GRADES for g in witness.values()):
        raise ValueError('Witness grades do not match the shared domain')
    labels = known | witness
    outputs = []
    for weights in WEIGHTS:
        scores = [sum(weights[labels[p]] for p in run) for run in runs]
        order = sorted(range(4), key=lambda i: (-scores[i], i))
        outputs.append(order[:3] if endpoint == 'prefix' else set(order[:3]))
    return outputs[0] != outputs[1]


def verify_encoding(case, endpoint, formula, grade_vars):
    from pysat.solvers import Glucose4

    count = 0
    with Glucose4(bootstrap_with=formula.clauses) as solver:
        for grades in product(GRADES, repeat=len(grade_vars)):
            witness = dict(zip(grade_vars, grades))
            actual = solver.solve(assumptions=[grade_vars[p][g] for p, g in witness.items()])
            if actual != direct_change(case, endpoint, witness):
                raise RuntimeError(f"Encoding disagreement for {case['id']} {endpoint} {witness}")
            count += 1
    return count


def check_drat(checker, dimacs_path, proof_path):
    completed = subprocess.run([str(checker), str(dimacs_path), str(proof_path), '-q'],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=10, check=False, text=True)
    ok = completed.returncode == 0 and 's VERIFIED' in completed.stdout.splitlines()
    return ok, completed.stdout


def checked_unit(case, endpoint, checker, artifacts, check_encoding, encoding_cap):
    from pysat.solvers import Glucose4

    started = perf_counter_ns()
    formula, grade_vars = encode(case, endpoint)
    dimacs = formula.dimacs()
    encoded = perf_counter_ns()
    with Glucose4(bootstrap_with=formula.clauses, with_proof=True) as solver:
        state = solver.solve()
        proof = None if state else solver.get_proof()
        model = solver.get_model() if state else None
    solved = perf_counter_ns()
    receipt = {'variables': formula.nvars, 'clauses': len(formula.clauses),
               'cnf_bytes': len(dimacs), 'cnf_sha256': sha256(dimacs).hexdigest(),
               'encode_ns': encoded - started, 'solve_log_ns': solved - encoded}
    if state is True:
        positive = set(model)
        witness = {}
        for passage, variables in grade_vars.items():
            choices = [grade for grade, var in enumerate(variables) if var in positive]
            if len(choices) != 1:
                raise RuntimeError('SAT model violated one-hot encoding')
            witness[passage] = choices[0]
        if not direct_change(case, endpoint, witness):
            raise RuntimeError(f"Invalid decoded SAT witness {case['id']} {endpoint}")
        receipt.update(status='changed', witness=witness)
    elif state is False:
        if proof is None:
            raise RuntimeError('UNSAT solver supplied no proof trace')
        trace = ('\n'.join(proof) + '\n').encode('ascii') if proof else b''
        cnf_path = artifacts.with_suffix('.cnf')
        proof_path = artifacts.with_suffix('.drat')
        cnf_path.write_bytes(dimacs)
        proof_path.write_bytes(trace)
        verify_started = perf_counter_ns()
        ok, log = check_drat(checker, cnf_path, proof_path)
        checked = perf_counter_ns()
        if not ok:
            raise RuntimeError(f"Independent DRAT check failed for {case['id']} {endpoint}: {log}")
        receipt.update(status='invariant', proof_bytes=len(trace), proof_clauses=len(proof),
                       proof_sha256=sha256(trace).hexdigest(), checker_ns=checked-verify_started,
                       artifact=artifacts.name)
    else:
        receipt.update(status='unknown')
    if check_encoding:
        worlds = 4 ** len(grade_vars)
        receipt['possible_worlds'] = worlds
        if worlds <= encoding_cap:
            receipt['assignments_checked'] = verify_encoding(case, endpoint, formula, grade_vars)
        else:
            receipt['encoding_check_omitted_reason'] = 'per_case_world_cap'
    return receipt


def load_reference(path):
    doc = json.loads(path.read_text())
    if 'by_case' in doc and isinstance(doc['by_case'], dict):
        return doc['by_case']
    if 'cases' in doc and isinstance(doc['cases'], dict):
        return doc['cases']
    if 'per_case' in doc and isinstance(doc['per_case'], dict):
        return doc['per_case']
    return doc


def summary(rows):
    totals = Counter(row['status'] for row in rows)
    positive = [row for row in rows if row['status'] == 'invariant']
    medians = {key: statistics.median(row[key] for row in positive)
               for key in ('cnf_bytes', 'proof_bytes', 'proof_clauses', 'encode_ns', 'solve_log_ns', 'checker_ns')}
    return {'status_counts': dict(totals), 'positive_medians': medians,
            'empty_proofs': sum(row['proof_clauses'] == 0 for row in positive),
            'nonempty_proofs': sum(row['proof_clauses'] > 0 for row in positive),
            'encoding_assignments_checked': sum(row.get('assignments_checked', 0) for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cases', 'reference', 'checker', 'output'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--expect-cases-sha256', required=True)
    parser.add_argument('--check-encoding', action='store_true')
    parser.add_argument('--max-encoding-worlds', type=int, default=4096)
    args = parser.parse_args()
    raw = args.cases.read_bytes()
    cases_hash = sha256(raw).hexdigest()
    if cases_hash != args.expect_cases_sha256:
        raise ValueError('Input digest mismatch')
    cases = json.loads(raw)
    args.output.mkdir(parents=True, exist_ok=False)
    artifacts = args.output / 'certificates'
    artifacts.mkdir()
    checker = args.checker.resolve(strict=True)
    results = {}
    for index, case in enumerate(cases, 1):
        if case['id'] in results:
            raise ValueError('Duplicate case ID')
        results[case['id']] = {
            endpoint: checked_unit(case, endpoint, checker, artifacts / f'{index:03d}_{endpoint}',
                                   args.check_encoding, args.max_encoding_worlds)
            for endpoint in ENDPOINTS
        }
    reference = load_reference(args.reference)
    for case_id, endpoints in results.items():
        for endpoint, record in endpoints.items():
            target = reference[case_id]
            if 'endpoints' in target:
                expected = target['endpoints'][endpoint]['status']
            else:
                flag = target['outcomes'][f'3_{endpoint}']['common_change']
                if type(flag) is not bool:
                    raise ValueError('Reference did not adjudicate the requested endpoint')
                expected = 'changed' if flag else 'invariant'
            if record['status'] != expected:
                raise RuntimeError(f'{case_id} {endpoint} {record["status"]} != {expected}')
    rows = [row for endpoints in results.values() for row in endpoints.values()]
    document = {'cases_sha256': cases_hash, 'cases': len(results), 'endpoints': len(rows),
                'checker_sha256': sha256(checker.read_bytes()).hexdigest(),
                'reference_sha256': sha256(args.reference.read_bytes()).hexdigest(),
                'summary': summary(rows), 'records': results}
    (args.output / 'results.json').write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')
    print(json.dumps(document['summary'], indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
