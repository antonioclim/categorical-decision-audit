"""Reconcile every portable verdict with the separate C traversal outputs.

This reads produced evidence only; it does not rerun the large domains and
does not import either proof implementation or the C driver as an oracle.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import independent_reference as ref

HERE = Path(__file__).resolve().parent
PHASE = HERE.parent
METRICS = [('flat_gain_v1', 1)] + [
    ('quantised_log_discount_floor_gain_v1', s)
    for s in [10_000, 1_000_000, 100_000_000]]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def main():
    counts, files, strata = Counter(), {}, {}

    def read(path):
        raw = path.read_bytes()
        files[str(path.relative_to(PHASE))] = sha256(raw).hexdigest()
        return json.loads(raw)

    c_source = PHASE/'empirical/exhaustive_weighted.c'
    c_binary = PHASE/'empirical/exhaustive_weighted'
    c_hash = sha256(c_source.read_bytes()).hexdigest()
    binary_hash = sha256(c_binary.read_bytes()).hexdigest()
    validation = read(PHASE/'empirical/enumerator_validation.json')
    assert validation['status'] == 'passed'
    assert validation['c_source_sha256'] == c_hash
    assert validation['c_binary_sha256'] == binary_hash
    assert validation['independent_oracle_sha256'] == sha256(
        (HERE/'independent_reference.py').read_bytes()).hexdigest()
    for cohort, casepath in [
        ('dl21', PHASE/'original_replay/replay/dl21/cases.json'),
        ('dl22', PHASE/'original_replay/work/ipm_elevate/mars/cases.json')]:
        cases = {row['id']: row for row in read(casepath)}
        requests = read(PHASE/'weighted'/f'empirical_{cohort}'/'records.json')
        indexed = {(r['case_id'], r['metric'], r['scale'], r['endpoint']): r['record']
                   for r in requests}
        assert len(indexed) == len(requests) == len(cases) * 8
        for metric, scale in METRICS:
            doc = read(PHASE/'empirical'/cohort/f'{metric}_{scale}.json')
            assert doc['input_sha256'] == sha256(casepath.read_bytes()).hexdigest()
            assert doc['c_source_sha256'] == c_hash
            assert doc['c_binary_sha256'] == binary_hash
            coefficients = ref.coefficients(metric, scale)
            assert doc['coefficient_table'] == [list(row) for row in coefficients]
            assert doc['coefficient_table_sha256'] == sha256(canonical(coefficients)).hexdigest()
            assert set(doc['by_case']) == set(cases)
            counts['metric_documents_checked'] += 1
            strata[f'{cohort}:{metric}:{scale}'] = doc['by_stratum']
            for cid, row in doc['by_case'].items():
                assert row['status'] == 'exact'
                assert row['case_sha256'] == sha256(canonical(cases[cid])).hexdigest()
                assert row['worlds'] == row['completions_checked'] == 4**len(cases[cid]['unknown'])
                assert sum(x['count'] for x in row['joint_full_orders']) == row['worlds']
                counts['independent_C_metric_completions'] += row['worlds']
                counts['metric_cases_checked'] += 1
                for endpoint in ['set', 'prefix']:
                    record = indexed[cid, metric, scale, endpoint]
                    target = row['endpoints'][endpoint]
                    assert record['status'] in ('changed', 'invariant')
                    assert (record['status'] == 'changed') == target['any_change']
                    assert record['case_sha256'] == row['case_sha256']
                    counts['portable_verdicts_matching_independent_C'] += 1
                    change = 0
                    for cell in row['joint_full_orders']:
                        b = doc['orderings'][cell['binary_order_index']]
                        g = doc['orderings'][cell['graded_order_index']]
                        differs = b[3] != g[3] if endpoint == 'set' else b[:3] != g[:3]
                        change += cell['count'] * differs
                    assert target['change_worlds'] == change
                    assert target['any_change'] == (change > 0)
                    assert target['always_change'] == (change == row['worlds'])
                    counts['joint_distribution_endpoint_reconstructions'] += 1
    assert counts['portable_verdicts_matching_independent_C'] == 1328
    assert counts['independent_C_metric_completions'] == 578121052
    result = {
        'status': 'passed', 'counts': dict(counts), 'source_files_sha256': files,
        'reviewed_C_source_sha256': c_hash, 'C_binary_sha256': binary_hash,
        'reviewer_sources_sha256': {p.name: sha256(p.read_bytes()).hexdigest()
                                   for p in [Path(__file__), HERE/'independent_reference.py']},
        'scope': 'All 1328 portable verdicts match separate complete C traversal. '
                 'This reconciliation inspects existing evidence; it does not rerun '
                 'the wide domains. C code and driver reviewed statically; standalone '
                 'C validation crosschecks against independent Python direct scores.'}
    (HERE/'empirical_reconciliation_validation.json').write_text(
        json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'counts': result['counts']}, indent=2))


if __name__ == '__main__':
    main()
