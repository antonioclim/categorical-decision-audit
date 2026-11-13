"""Independent exhaustive and hostile validation of the new proof route."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

import independent_reference as ref

HERE = Path(__file__).resolve().parent
WEIGHTED = HERE.parent/'weighted'
sys.path.insert(0, str(WEIGHTED))
import weighted_proof as producer
import weighted_check as checker

METRICS = [('flat_gain_v1', 1)] + [('quantised_log_discount_floor_gain_v1', s)
           for s in [10_000, 1_000_000, 100_000_000]]


def main():
    started = perf_counter()
    counts, statuses = Counter(), Counter()
    cases = ref.fixtures()
    details, mutations, examples = [], [], {}
    for metric, scale in METRICS:
        coeff = ref.coefficients(metric, scale)
        assert coeff == producer.metric_table(metric, scale)
        counts['independently_certified_nonzero_coefficients'] += 30 if scale > 1 else 0
        for case in cases:
            truth, cached = ref.audit(case, coeff)
            counts['completions'] += len(cached)
            counts['scenario_equivalences'] += 2 * len(cached)
            for endpoint in ['set', 'prefix']:
                record = producer.produce(case, endpoint, metric=metric, scale=scale)
                checked = checker.verify(case, endpoint, record, metric=metric, scale=scale)
                assert checked['accepted'], (case['id'], endpoint, record, checked)
                assert (record['status'] == 'changed') == truth[endpoint]
                if record['status'] == 'changed':
                    oo = ref.outcomes(ref.scores(case, record['witness'], coeff))
                    assert oo['binary'][endpoint] != oo['graded'][endpoint]
                    counts['independent_witness_replays'] += 1
                else:
                    values = ref.verify_trees_exhaustively(case, endpoint, record['trees'], cached)
                    counts.update(values)
                    counts['independent_full_tree_checks'] += 1
                statuses[f'{metric}@{scale}:{record["status"]}'] += 1
                counts['verified_requests'] += 1
                details.append({'case_id': case['id'], 'endpoint': endpoint, 'metric': metric,
                                'scale': scale, 'status': record['status'],
                                'worlds': len(cached), 'checker': checked})
                if metric == producer.DISCOUNTED and scale == 1_000_000:
                    examples.setdefault(record['status'], (deepcopy(case), endpoint, deepcopy(record)))
                    if record['status'] == 'changed' and case['unknown']:
                        examples.setdefault('changed_unknown', (deepcopy(case), endpoint, deepcopy(record)))
    assert set(examples) >= {'changed', 'invariant', 'changed_unknown'}

    def rejected(label, case, endpoint, record, **parameters):
        answer = checker.verify(case, endpoint, record, **parameters)
        assert not answer['accepted'], (label, answer)
        mutations.append({'name': label, 'state': answer['state'], 'reason': answer.get('reason')})

    case, endpoint, record = examples['changed_unknown']
    # Valid canonical input transformations do not change the case binding.
    reordered = {key: deepcopy(case[key]) for key in reversed(case)}
    assert checker.verify(reordered, endpoint, record)['accepted']
    counts['canonical_key_order_checks'] += 1
    for field, value in [('case_sha256', '0'*64), ('request_sha256', '0'*64),
                         ('schema', 'unrecognised'), ('case_id', 'wrong'),
                         ('endpoint', 'prefix' if endpoint == 'set' else 'set')]:
        bad = deepcopy(record); bad[field] = value
        rejected('binding_'+field, case, endpoint, bad)
    bad = deepcopy(record); bad['extra'] = 1
    rejected('unexpected_record_field', case, endpoint, bad)
    for field in record['metric']:
        bad = deepcopy(record)
        original = bad['metric'][field]
        bad['metric'][field] = 'changed' if isinstance(original, str) else 42
        rejected('descriptor_'+field, case, endpoint, bad)
    rejected('trusted_expected_metric', case, endpoint, record, metric='flat_gain_v1', scale=1)
    rejected('trusted_expected_scale', case, endpoint, record, scale=10_000)
    bad_case = deepcopy(case)
    name = next(iter(bad_case['runs']))
    bad_case['runs'][name][0], bad_case['runs'][name][1] = bad_case['runs'][name][1], bad_case['runs'][name][0]
    rejected('rank_order_binding', bad_case, endpoint, record)
    bad_case = deepcopy(case)
    passage = next(iter(bad_case['known']))
    bad_case['known'][passage] = (bad_case['known'][passage] + 1) % 4
    rejected('known_grade_binding', bad_case, endpoint, record)
    for grade in [-1, 4, True, 0.0, '0']:
        bad = deepcopy(record)
        bad['witness'][case['unknown'][0]] = grade
        rejected('invalid_witness_grade_'+repr(grade), case, endpoint, bad)
    bad = deepcopy(record); del bad['witness'][case['unknown'][0]]
    rejected('missing_witness_grade', case, endpoint, bad)
    bad = deepcopy(record); bad['witness']['nonexistent'] = 0
    rejected('additional_witness_grade', case, endpoint, bad)

    invariant_case, invariant_endpoint, invariant = examples['invariant']
    bad = deepcopy(invariant); bad.pop('trees'); bad['status'] = 'changed'
    bad['witness'] = dict.fromkeys(invariant_case['unknown'], 0)
    rejected('false_change_with_valid_domain', invariant_case, invariant_endpoint, bad)
    bad = deepcopy(record); bad.pop('witness'); bad['status'] = 'invariant'
    bad['trees'] = deepcopy(invariant['trees'])
    rejected('false_invariance_full_shape', case, endpoint, bad)
    bad = deepcopy(invariant); bad['trees'].pop()
    rejected('missing_scenario', invariant_case, invariant_endpoint, bad)
    for subset in [[], [True], [-1], [99], [0, 0], [1, 0]]:
        bad = deepcopy(invariant); bad['trees'][0] = {'subset': subset}
        rejected('malformed_subset_'+repr(subset), invariant_case, invariant_endpoint, bad)

    # Construct a deliberately redundant but otherwise valid split cover.
    base = [f'n{i}' for i in range(10)]
    common = {'id': 'budget-common-six', 'runs': {n: base[:] for n in 'ABCD'},
              'known': {p: 0 for p in base[6:]}, 'unknown': base[:6]}
    valid = producer.produce(common, 'set')
    assert valid['status'] == 'invariant' and checker.verify(common, 'set', valid)['accepted']
    leaf = valid['trees'][0]
    def full_tree(depth):
        return deepcopy(leaf) if depth == 6 else {'split': base[depth], 'children': [full_tree(depth+1) for _ in range(4)]}
    bad = deepcopy(valid); bad['trees'][0] = full_tree(0)
    answer = checker.verify(common, 'set', bad)
    assert not answer['accepted'] and 'node' in answer.get('reason', ''), answer
    mutations.append({'name': 'cumulative_node_budget', 'state': answer['state'], 'reason': answer.get('reason')})
    bad = deepcopy(valid); bad['trees'][0] = {'split': base[0], 'children': [deepcopy(leaf)]*3}
    rejected('missing_grade_branch', common, 'set', bad)
    bad = deepcopy(valid); bad['trees'][0] = {'split': base[0], 'children': [
        {'split': base[0], 'children': [deepcopy(leaf)]*4}]*4}
    rejected('repeated_grade_split', common, 'set', bad)
    bad = deepcopy(valid); bad['trees'][0] = {'split': base[-1], 'children': [deepcopy(leaf)]*4}
    rejected('split_on_known_grade', common, 'set', bad)
    unresolved = producer.produce(common, 'set', node_limit=1)
    answer = checker.verify(common, 'set', unresolved)
    assert unresolved['status'] == 'unresolved' and not answer['accepted'] and answer['state'] == 'unresolved'
    counts['honest_budget_abstentions'] += 1
    for payload in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                    b'{"x":1e999}', b' '*1_048_577, b'\xff']:
        try:
            checker.parse_json(payload)
        except (ValueError, UnicodeError):
            counts['malformed_json_rejections'] += 1
        else:
            raise AssertionError('Malformed input was parsed')
    invalids = []
    bad = deepcopy(common); bad['known'][base[-1]] = True; invalids.append(('bool_grade', bad))
    bad = deepcopy(common); bad['known'][base[-1]] = -1; invalids.append(('negative_grade', bad))
    bad = deepcopy(common); bad['runs']['A'][0] = bad['runs']['A'][1]; invalids.append(('duplicate_passage', bad))
    bad = deepcopy(common); bad['unknown'].append(base[0]); invalids.append(('duplicate_unknown', bad))
    bad = deepcopy(common); bad['unknown'].append(base[-1]); invalids.append(('partition_overlap', bad))
    bad = deepcopy(common); bad['known']['not_present'] = 1; invalids.append(('extra_known', bad))
    bad = deepcopy(common); bad['runs']['A'].append('extra'); invalids.append(('depth_eleven', bad))
    bad = deepcopy(common); bad['runs']['E'] = base[:]; invalids.append(('five_runs', bad))
    bad = deepcopy(common); bad['constraints'] = []; invalids.append(('unsupported_constraints', bad))
    for label, candidate in invalids:
        rejected('trusted_input_'+label, candidate, 'set', valid)
        try:
            producer.produce(candidate, 'set')
        except (ValueError, TypeError):
            counts['producer_invalid_input_rejections'] += 1
        else:
            raise AssertionError('Producer accepted '+label)
    counts['rejected_record_or_request_mutations'] = len(mutations)
    protocol = HERE.parent/'PROTOCOL_DISCOUNT.md'
    report = {'status': 'passed', 'scope': 'independent synthetic validation; direct scoring and exhaustive leaf checks',
              'protocol_sha256': sha256(protocol.read_bytes()).hexdigest(),
              'source_sha256': {p.name: sha256(p.read_bytes()).hexdigest() for p in [
                  Path(__file__), HERE/'independent_reference.py', WEIGHTED/'weighted_proof.py',
                  WEIGHTED/'weighted_check.py', WEIGHTED/'metric_tables.json']},
              'cases': len(cases), 'counts': dict(counts), 'statuses': dict(statuses),
              'mutations': mutations, 'details': details, 'elapsed_seconds': perf_counter()-started}
    (HERE/'weighted_validation.json').write_text(json.dumps(report, indent=2)+'\n')
    (HERE/'independent_synthetic_cases.json').write_text(json.dumps(cases, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['mutations','details']},indent=2))


if __name__ == '__main__':
    main()
