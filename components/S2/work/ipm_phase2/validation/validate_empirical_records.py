"""Independent direct replay of all emitted empirical witnesses.

Also exhaust all DL21 cases and DL22 cases at most 4,096 completions. This
does not claim complete DL22 reference coverage; the separate C enumerator
handles the full cohort. The numerical floor oracle has no producer imports.
"""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import independent_reference as ref

HERE = Path(__file__).resolve().parent
PHASE = HERE.parent


def digest(obj):
    return sha256(json.dumps(obj, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def main():
    started = perf_counter()
    counts = Counter()
    bycohort, margins, casesources, reportsources = {}, defaultdict(Counter), {}, {}
    for cohort, casepath, expected in [
        ('dl21', PHASE/'original_replay/replay/dl21/cases.json', '20cc22dcc68041622b507078d449ceb39b9bfcab2fdc727d31bab3fbcdca732b'),
        ('dl22', PHASE/'original_replay/work/ipm_elevate/mars/cases.json', '7d1bf9def75a146a50383dc817e83e99520d96259f771db860beb06a89581a66')]:
        assert sha256(casepath.read_bytes()).hexdigest() == expected
        casesources[cohort] = expected
        cases = {c['id']: c for c in json.loads(casepath.read_text())}
        recordpath = PHASE/'weighted'/f'empirical_{cohort}'/'records.json'
        reportsources[cohort] = sha256(recordpath.read_bytes()).hexdigest()
        requests = json.loads(recordpath.read_text())
        local = Counter()
        cache = {}
        for request in requests:
            case = cases[request['case_id']]
            metric, scale, endpoint = request['metric'], request['scale'], request['endpoint']
            record = request['record']
            coeff = ref.coefficients(metric, scale)
            assert record['case_sha256'] == digest(case)
            assert record['metric']['gain_table_sha256'] == digest(coeff)
            assert record['metric']['name'] == metric and record['metric']['scale'] == scale
            if record['status'] == 'changed':
                witness = record['witness']
                assert set(witness) == set(case['unknown'])
                assert all(type(g) is int and 0 <= g <= 3 for g in witness.values())
                ss = ref.scores(case, witness, coeff)
                oo = ref.outcomes(ss)
                assert oo['binary'][endpoint] != oo['graded'][endpoint]
                local['independent_witness_replays'] += 1
                if scale > 1:
                    allgaps = []
                    for values in ss.values():
                        ordered = sorted(values.values(), reverse=True)
                        gaps = [ordered[i] - ordered[i+1] for i in range(3)]
                        allgaps.extend(gaps if endpoint == 'prefix' else gaps[2:])
                    key = f'{cohort}:{case["stratum"]}:{scale}:{endpoint}'
                    margins[key]['emitted_witnesses'] += 1
                    margins[key]['all_required_gaps_positive'] += int(min(allgaps) > 0)
                    margins[key]['all_required_gaps_over_20'] += int(min(allgaps) > 20)
            domain = 4**len(case['unknown'])
            if cohort == 'dl21' or domain <= 4096:
                key = (case['id'], metric, scale)
                if key not in cache:
                    rows, truth = [], {'set':False, 'prefix':False}
                    for world in ref.all_worlds(case):
                        ss = ref.scores(case, world, coeff)
                        oo = ref.outcomes(ss)
                        for end in truth:
                            truth[end] |= oo['binary'][end] != oo['graded'][end]
                        rows.append((world, ss, oo))
                    cache[key] = truth, rows
                    local['independent_metric_completions'] += len(rows)
                    local['independent_metric_cases'] += 1
                truth, rows = cache[key]
                assert (record['status'] == 'changed') == truth[endpoint]
                local['independent_exact_request_verdicts'] += 1
                if record['status'] == 'invariant':
                    checks = ref.verify_trees_exhaustively(case, endpoint, record['trees'], rows)
                    local['independent_certificate_trees'] += 1
                    for key, value in checks.items():
                        local[key] += value
            local['bound_requests_inspected'] += 1
        bycohort[cohort] = dict(local)
        counts.update(local)
    result = {'status':'passed', 'counts':dict(counts),'by_cohort':bycohort,
              'case_file_sha256':casesources,'records_file_sha256':reportsources,
              'concrete_witness_margin_diagnostic':{k:dict(v) for k,v in margins.items()},
              'margin_interpretation':'Raw integer margins >20 for every required comparison are sufficient to retain the emitted witness discrepancy for real-valued discounted scores via the conservative 2D/S bound. Counts are for emitted witnesses, not all possible strict changes or universal real-valued invariance.',
              'scope':'All empirical witnesses replayed independently. Complete independent Python verdict and tree checks for all DL21 and DL22 domains <=4096 only. Full DL22 handled by separate compiled enumeration.',
              'source_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),HERE/'independent_reference.py']},
              'elapsed_seconds':perf_counter()-started}
    (HERE/'empirical_record_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='concrete_witness_margin_diagnostic'},indent=2))


if __name__ == '__main__':
    main()
