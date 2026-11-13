"""Paired single-endpoint portable-proof checks and independent exact re-solving."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations, product
import json
import math
from pathlib import Path
import platform
import random
from statistics import median
from time import perf_counter_ns

from baselines import comparator as z3
from baselines import oracle_holdout as oracle
from check_proof import InvalidProof, parse_json, verify
from intake.pair_margin_dp import solve_prefix as solve_prefix_dp
from proof import produce


ENDPOINTS = ('set', 'prefix')
STATUSES = frozenset(('changed', 'invariant', 'unknown'))
REPEATS = 3
THIN_UNKNOWN_LIMIT = 3
DIRECT_PRODUCTS = 1024
INCIDENCE_NODE_CAP = oracle.BRANCH_NODE_CAP
TIMEOUT_MS = z3.MAX_TIMEOUT_MS
MINIMUM_CLUSTERS = 10
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20261110


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw):
    return sha256(raw).hexdigest()


def aliased_case(case):
    """Use the prior Z3 schema without altering any order-dependent output."""
    mapping = dict(zip(sorted(case['runs']), z3.RUN_IDS))
    metadata = {'stratum': 'natural', 'id': f'natural:{case["qid"]}'} if case['stratum'] == 'synthetic' else {}
    return case | metadata | {'runs': {mapping[name]: passages for name, passages in case['runs'].items()}}


def exact_qflia(alias, endpoint, timeout_ms):
    z3.validate_case(alias)
    smt, variables = z3.encode_case(alias)
    with z3.Z3Session(timeout_ms) as solver:
        solver.eval(smt)
        result = z3.solve_endpoint(alias, solver, variables, endpoint)
        return {'status': result['status'], 'witness': result['witness'], 'route': 'QF_LIA',
                'solver': solver.version, 'reason': result.get('reason'),
                'solver_query_ns': result['solver_query_ns']}


def integer_state(prepared):
    members = tuple(set(run) for run in prepared.runs)
    binary = tuple(sum(prepared.known.get(p, 0) >= 2 for p in run) for run in prepared.runs)
    graded = tuple(sum(prepared.known.get(p, 0) for p in run) for run in prepared.runs)
    patterns = Counter(sum(1 << r for r, passages in enumerate(members) if p in passages)
                       for p in prepared.unknown)
    return (binary, graded), tuple(sorted(patterns.items()))


def structural_rows(endpoint):
    """Independent rank formulation, using four lexical indices."""
    for left in range(4):
        for right in range(4):
            if left == right:
                continue
            if endpoint == 'prefix':
                yield ((0, left, right), (1, right, left))
            else:
                yield tuple((arm, ahead, last) for arm, last in enumerate((left, right))
                            for ahead in range(4) if ahead != last)


def scenario_blocked(rows, fixed_scores, patterns):
    constants = tuple(fixed_scores[arm][i] - fixed_scores[arm][j] - int(i > j)
                      for arm, i, j in rows)
    # Every unknown with the same incidence has the same coefficient and an
    # independent grade. Multiplicity times the exact maximum is therefore exact.
    effects = tuple(tuple(((mask >> i) & 1) - ((mask >> j) & 1) for _, i, j in rows)
                    for mask, _ in patterns)
    for size in range(1, len(rows) + 1):
        for subset in combinations(range(len(rows)), size):
            constant = sum(constants[r] for r in subset)
            binary = tuple(r for r in subset if rows[r][0] == 0)
            graded = tuple(r for r in subset if rows[r][0] == 1)
            for (_, count), effect in zip(patterns, effects):
                b = sum(effect[r] for r in binary)
                g = sum(effect[r] for r in graded)
                constant += count * max(0, g, b + 2 * g, b + 3 * g)
            if constant < 0:
                return True
    return False


def validate_change(prepared, endpoint, witness):
    if not oracle._validate(prepared, endpoint, witness)['accepted']:
        raise RuntimeError(f'independent baseline witness is invalid for {endpoint}')


def point_screen(prepared, endpoint, fixed_scores, patterns):
    singleton_order = all(mask == 15 for mask, _ in patterns)
    for grade in (0,) if singleton_order else (0, 3):
        if grade == 0:
            binary, graded = fixed_scores
        else:
            binary, graded = oracle._direct_totals(prepared, dict.fromkeys(prepared.unknown, grade))
        if endpoint == 'set':
            changed = min(range(4), key=lambda i: (binary[i], -i)) != min(range(4), key=lambda i: (graded[i], -i))
        else:
            changed = sorted(range(4), key=lambda i: (-binary[i], i)) != sorted(range(4), key=lambda i: (-graded[i], i))
        if changed:
            witness = dict.fromkeys(prepared.unknown, grade)
            validate_change(prepared, endpoint, witness)
            return {'status': 'changed', 'witness': witness, 'route': 'exact_point_check'}
    if singleton_order:
        return {'status': 'invariant', 'witness': None, 'route': 'singleton_order_or_all_neutral'}
    return None


def solve_qflia(case, alias, endpoint, timeout_ms):
    prepared = oracle._prepare(case)
    scores, patterns = integer_state(prepared)
    return point_screen(prepared, endpoint, scores, patterns) or exact_qflia(alias, endpoint, timeout_ms)


def solve_structural(case, alias, endpoint, timeout_ms):
    prepared = oracle._prepare(case)
    fixed_scores, patterns = integer_state(prepared)
    point = point_screen(prepared, endpoint, fixed_scores, patterns)
    if point is not None:
        return point
    if all(scenario_blocked(rows, fixed_scores, patterns) for rows in structural_rows(endpoint)):
        return {'status': 'invariant', 'witness': None, 'route': 'all_scenarios_blocked_by_root_bounds'}
    return exact_qflia(alias, endpoint, timeout_ms) | {'route': 'root_screen_then_QF_LIA'}


def score_options(buckets):
    """Use the prior oracle's exact (binary, graded) subtotal support."""
    return [tuple((tuple(b * (r in bucket.incidence) for r in range(4)),
                   tuple(g * (r in bucket.incidence) for r in range(4)), grades)
                  for b, g, grades in bucket.options) for bucket in buckets]


def solve_incidence(case, alias, endpoint, timeout_ms):
    started = perf_counter_ns()
    prepared = oracle._prepare(case)
    fixed_scores, patterns = integer_state(prepared)
    point = point_screen(prepared, endpoint, fixed_scores, patterns)
    if point is not None:
        return point
    deadline = started + timeout_ms * 1_000_000
    bit = oracle.ENDPOINT_BITS[endpoint]
    buckets, neutral = oracle._buckets(prepared)
    bounds = oracle._remaining_pair_bounds(buckets)
    choices = score_options(buckets)
    if math.prod(map(len, choices)) <= DIRECT_PRODUCTS:
        route = 'incidence_totals_direct'
        for selected in product(*choices):
            if perf_counter_ns() >= deadline:
                return {'status': 'unknown', 'witness': None, 'route': route, 'reason': 'wall_timeout'}
            binary = tuple(fixed_scores[0][i] + sum(row[0][i] for row in selected) for i in range(4))
            graded = tuple(fixed_scores[1][i] + sum(row[1][i] for row in selected) for i in range(4))
            if oracle._changed_endpoints(binary, graded) & bit:
                witness = dict.fromkeys(neutral, 0)
                for bucket, row in zip(buckets, selected):
                    witness.update(zip(bucket.passages, row[2]))
                validate_change(prepared, endpoint, witness)
                return {'status': 'changed', 'witness': witness, 'route': route}
        return {'status': 'invariant', 'witness': None, 'route': route}

    route = 'incidence_totals_branch_bounds'
    stack = [oracle.Node(0, *fixed_scores, (), bit)]
    visited = 0
    while stack:
        if visited >= INCIDENCE_NODE_CAP or perf_counter_ns() >= deadline:
            return {'status': 'unknown', 'witness': None, 'route': route,
                    'reason': 'node_or_wall_cap', 'nodes': visited}
        node = stack.pop()
        visited += 1
        if node.depth == len(buckets):
            if oracle._changed_endpoints(node.binary, node.graded) & bit:
                witness = oracle._complete(node, buckets, neutral)
                validate_change(prepared, endpoint, witness)
                return {'status': 'changed', 'witness': witness, 'route': route, 'nodes': visited}
            continue
        if not oracle._possibly_changed(node, bounds[node.depth], bit):
            continue
        for binary_add, graded_add, grades in reversed(choices[node.depth]):
            binary = tuple(a + b for a, b in zip(node.binary, binary_add))
            graded = tuple(a + b for a, b in zip(node.graded, graded_add))
            stack.append(oracle.Node(node.depth + 1, binary, graded, node.samples + (grades,), bit))
    return {'status': 'invariant', 'witness': None, 'route': route, 'nodes': visited}


BASELINES = {'qflia': solve_qflia, 'structural_qflia': solve_structural, 'incidence_exact': solve_incidence}


def arms_for(endpoint):
    return ('proof', *BASELINES, 'pair_margin_dp') if endpoint == 'prefix' else ('proof', *BASELINES)


def checked_record(case, endpoint):
    started = perf_counter_ns()
    record = produce(case, endpoint)
    wire = json_bytes(record)
    produced = perf_counter_ns()
    try:
        verdict = verify(case, endpoint, parse_json(wire))
    except InvalidProof as error:
        verdict = {'state': 'rejected', 'accepted': False, 'reason': str(error)}
    ended = perf_counter_ns()
    return record, wire, verdict, produced - started, ended - produced


def verify_accepted(verdict, status):
    if isinstance(verdict, dict):
        return verdict.get('accepted') is True and verdict.get('status', status) == status
    return verdict is True


def time_arm(arm, case, alias, endpoint, timeout_ms):
    if arm == 'proof':
        record, wire, verdict, produced, verified = checked_record(case, endpoint)
        producer_status = record['status']
        accepted = verify_accepted(verdict, producer_status)
        result = {'status': producer_status if accepted else 'unknown', 'producer_status': producer_status,
                  'verifier_accepted': accepted, 'verdict': verdict, 'witness': record.get('witness') if accepted else None,
                  'producer_ns': produced, 'verify_ns': verified, 'producer_verify_ns': produced + verified,
                  'certificate_bytes': len(wire), 'certificate_sha256': digest(wire)}
        return result, wire
    started = perf_counter_ns()
    if arm == 'pair_margin_dp':
        result = solve_prefix_dp(case, timeout_ms)
    else:
        result = BASELINES[arm](case, alias, endpoint, timeout_ms)
    result['elapsed_ns'] = perf_counter_ns() - started
    return result, None


def postcheck(case, endpoint, result):
    if result['status'] not in STATUSES:
        raise RuntimeError(f'unsupported endpoint status {result["status"]!r}')
    if result['status'] == 'changed':
        witness = oracle.validate_witness(case, endpoint, result['witness'])
        if not witness['accepted']:
            raise RuntimeError(f'{case["id"]}/{endpoint}: exact witness recheck failed')
    elif result.get('witness') is not None:
        raise RuntimeError('non-changing endpoint returned a witness')


def sample_summary(results):
    statuses = sorted({item['status'] for item in results})
    medians = {key: median([item[key] for item in results]) for key in results[0]
               if key.endswith('_ns') and all(key in item for item in results)}
    return {'status': statuses[0] if len(statuses) == 1 else 'unstable', 'median_ns': medians,
            'repetitions': results}


def measure_cases(cases, timeout_ms, proof_dir):
    # Warm code paths on one authorised input. No warmup timings enter results.
    for endpoint in ENDPOINTS:
        for arm in arms_for(endpoint):
            time_arm(arm, cases[0], aliased_case(cases[0]), endpoint, timeout_ms)
    rows = []
    for case_index, case in enumerate(cases):
        names = sorted(case['runs'])
        memberships = [set(case['runs'][name]) for name in names]
        neutral_count = sum(all(passage in run for run in memberships) for passage in case['unknown'])
        alias = aliased_case(case)
        for endpoint_index, endpoint in enumerate(ENDPOINTS):
            arms = arms_for(endpoint)
            samples = {arm: [] for arm in arms}
            for repeat in range(REPEATS):
                shift = (case_index + endpoint_index + repeat) % len(arms)
                for arm in arms[shift:] + arms[:shift]:
                    result, wire = time_arm(arm, case, alias, endpoint, timeout_ms)
                    postcheck(case, endpoint, result)
                    samples[arm].append(result)
                    if wire is not None and repeat == 0:
                        (proof_dir / f'{case_index:03d}_{endpoint}.json').write_bytes(wire)
            rows.append({'case_id': case['id'], 'qid': case['qid'], 'stratum': case['stratum'], 'endpoint': endpoint,
                         'input_bytes': len(json_bytes(case)), 'unknown_count': len(case['unknown']),
                         'neutral_unknown_count': neutral_count, 'lexical_run_ids': names,
                         'arms': {arm: sample_summary(entries) for arm, entries in samples.items()}})
    return rows


def break_even(producer, verifier, baseline):
    """First independent check count for a strict aggregate cost advantage."""
    saving = baseline - verifier
    return math.floor(producer / saving) + 1 if saving > 0 else None


def cluster_upper_bound(units):
    clusters = defaultdict(list)
    for row, _, ratio in units:
        clusters[row['qid']].append(ratio)
    cluster_ids = sorted(clusters)
    if not cluster_ids:
        return None, 0
    randomizer = random.Random(BOOTSTRAP_SEED)
    resampled = []
    for _ in range(BOOTSTRAP_DRAWS):
        sample = []
        for _ in cluster_ids:
            sample.extend(clusters[randomizer.choice(cluster_ids)])
        resampled.append(median(sample))
    upper = sorted(resampled)[math.ceil(0.95 * len(resampled)) - 1]
    return upper, len(cluster_ids)


def timing_summary(units):
    if not units:
        return None
    proof_rows = [row['arms']['proof']['median_ns'] for row, _, _ in units]
    fastest_times = [row['arms'][fastest]['median_ns']['elapsed_ns'] for row, fastest, _ in units]
    produced = [row['producer_ns'] for row in proof_rows]
    verified = [row['verify_ns'] for row in proof_rows]
    combined = [row['producer_verify_ns'] for row in proof_rows]
    input_sizes = [row['input_bytes'] for row, _, _ in units]
    proof_sizes = [row['arms']['proof']['repetitions'][0]['certificate_bytes'] for row, _, _ in units]
    upper, clusters = cluster_upper_bound(units)
    return {
        'requests': len(units), 'query_clusters': clusters,
        'median_ns': {'producer': median(produced), 'verify': median(verified),
                      'producer_verify': median(combined), 'fastest_exact': median(fastest_times)},
        'sum_request_median_ns': {'producer': sum(produced), 'verify': sum(verified),
                                  'producer_verify': sum(combined), 'fastest_exact': sum(fastest_times)},
        'fastest_exact_baseline_counts': dict(Counter(fastest for _, fastest, _ in units)),
        'paired_median_verify_over_fastest': median(ratio for _, _, ratio in units),
        'one_sided_95_upper_cluster_bootstrap_verify_over_fastest': upper,
        'paired_median_producer_verify_over_fastest': median(p / q for p, q in zip(combined, fastest_times)),
        'verify_faster_requests': sum(v < q for v, q in zip(verified, fastest_times)),
        'hypothetical_break_even_checks_vs_fastest': break_even(sum(produced), sum(verified), sum(fastest_times)),
        'median_input_bytes': median(input_sizes), 'median_certificate_bytes': median(proof_sizes),
        'max_certificate_bytes': max(proof_sizes),
    }


def summarise(rows):
    conclusive = {'changed', 'invariant'}
    measured_arms = sorted({arm for row in rows for arm in row['arms']})
    coverage = {arm: dict(Counter(row['arms'][arm]['status'] for row in rows if arm in row['arms']))
                for arm in measured_arms}
    conflicts, losses, verifier_rejections, false_acceptances = [], [], [], []
    independently_adjudicated = Counter()
    units = {'all': [], 'changed': [], 'invariant': []}
    for row in rows:
        key = [row['case_id'], row['endpoint']]
        statuses = {arm: result['status'] for arm, result in row['arms'].items()}
        baseline_statuses = {status for arm, status in statuses.items() if arm != 'proof' and status in conclusive}
        if len(baseline_statuses) > 1 or 'unstable' in statuses.values():
            conflicts.append(key)
        if baseline_statuses and statuses['proof'] not in conclusive:
            losses.append(key)
        if any(r['verdict'].get('state') == 'rejected' for r in row['arms']['proof']['repetitions']):
            verifier_rejections.append(key)
        if len(baseline_statuses) != 1:
            continue
        reference = next(iter(baseline_statuses))
        independently_adjudicated[reference] += 1
        if statuses['proof'] in conclusive and statuses['proof'] != reference:
            false_acceptances.append(key)
            continue
        if statuses['proof'] != reference or 'unstable' in statuses.values():
            continue
        fastest = min((arm for arm, status in statuses.items() if arm != 'proof' and status == reference),
                      key=lambda arm: (row['arms'][arm]['median_ns']['elapsed_ns'], arm))
        ratio = row['arms']['proof']['median_ns']['verify_ns'] / row['arms'][fastest]['median_ns']['elapsed_ns']
        unit = row, fastest, ratio
        units['all'].append(unit)
        units[reference].append(unit)
    return {'requests': len(rows), 'coverage': coverage,
            'independently_adjudicated': dict(independently_adjudicated),
            'baseline_conflicts_or_unstable': conflicts, 'proof_coverage_losses': losses,
            'verifier_rejections': verifier_rejections, 'false_acceptances': false_acceptances,
            'timings_on_agreeing_requests': {status: timing_summary(items) for status, items in units.items()}}


def external_gate(summary, external):
    invariant = summary['timings_on_agreeing_requests']['invariant']
    if not external:
        return {'evaluated': False, 'reason': 'development cohort'}
    complete = not any(summary[key] for key in ('baseline_conflicts_or_unstable', 'proof_coverage_losses',
                                                  'verifier_rejections', 'false_acceptances'))
    cluster_count = invariant['query_clusters'] if invariant else 0
    pass_count = cluster_count >= MINIMUM_CLUSTERS
    pass_latency = bool(invariant and invariant['paired_median_verify_over_fastest'] <= 0.8
                        and invariant['one_sided_95_upper_cluster_bootstrap_verify_over_fastest'] < 1.0)
    return {'evaluated': True, 'passed': complete and pass_count and pass_latency,
            'coverage_and_correctness_passed': complete, 'minimum_query_clusters_passed': pass_count,
            'latency_passed': pass_latency, 'primary_query_clusters': cluster_count,
            'latency_rule': 'median of per-request ratios <= 0.80 and query-cluster bootstrap upper 95% < 1.0'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cases-sha256', required=True)
    parser.add_argument('--cohort', required=True)
    parser.add_argument('--external', action='store_true', help='Evaluate the prespecified external gate')
    parser.add_argument('--timeout-ms', type=int, default=TIMEOUT_MS)
    args = parser.parse_args()
    if not 1 <= args.timeout_ms <= TIMEOUT_MS:
        parser.error('timeout must be in 1..10000 ms')
    raw = args.cases.read_bytes()
    if digest(raw) != args.cases_sha256.lower():
        parser.error('frozen cases hash does not match')
    cases = json.loads(raw, object_pairs_hook=z3.unique_object)
    if not isinstance(cases, list) or not cases or len({case['id'] for case in cases}) != len(cases):
        parser.error('expected a nonempty list of unique cases')
    for case in cases:
        z3.validate_case(aliased_case(case))
    args.output.mkdir(parents=True, exist_ok=False)
    proof_dir = args.output / 'proofs'
    proof_dir.mkdir()
    rows = measure_cases(cases, args.timeout_ms, proof_dir)
    source_paths = (Path(__file__), Path(z3.__file__), Path(oracle.__file__),
                    Path(__file__).with_name('proof.py'), Path(__file__).with_name('check_proof.py'),
                    Path(__file__).parent / 'intake/pair_margin_dp.py')
    metadata = {'cohort': args.cohort, 'cases_sha256': digest(raw), 'cases': len(cases), 'repeats': REPEATS,
                'endpoint_timeout_ms': args.timeout_ms, 'incidence_node_cap': INCIDENCE_NODE_CAP,
                'direct_products': DIRECT_PRODUCTS, 'platform': platform.platform(), 'python': platform.python_version(),
                'sources_sha256': {path.name: digest(path.read_bytes()) for path in source_paths},
                'external': args.external, 'bootstrap_draws': BOOTSTRAP_DRAWS, 'bootstrap_seed': BOOTSTRAP_SEED,
                'timing_unit': 'single endpoint request; Python perf_counter_ns, in-process; one warmup per arm and endpoint',
                'alias_policy_for_prior_qflia': 'rename run IDs by lexical order outside the clock; synthetic cases also receive schema-only natural IDs. Grade assignments and endpoint statuses are invariant to these renamings.',
                'aliases_for_prior_qflia': dict(zip(sorted(cases[0]['runs']), z3.RUN_IDS))}
    groups = {'all': rows, 'thin': [r for r in rows if r['unknown_count'] <= THIN_UNKNOWN_LIMIT],
              'other': [r for r in rows if r['unknown_count'] > THIN_UNKNOWN_LIMIT]}
    groups.update({name: [r for r in rows if r['stratum'] == name] for name in sorted({r['stratum'] for r in rows})})
    groups.update({name: [r for r in rows if r['endpoint'] == name] for name in ENDPOINTS})
    summary = {'metadata': metadata, 'groups': {name: summarise(items) for name, items in groups.items()}}
    summary['external_gate'] = external_gate(summary['groups']['all'], args.external)
    (args.output / 'benchmark.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'all': summary['groups']['all'], 'external_gate': summary['external_gate']}, indent=2))


if __name__ == '__main__':
    main()
