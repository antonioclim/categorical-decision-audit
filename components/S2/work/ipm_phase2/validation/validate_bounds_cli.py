"""Further independent comparisons of row/bound arithmetic and native CLIs."""
from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import independent_reference as ref

HERE = Path(__file__).resolve().parent
WEIGHTED = HERE.parent/'weighted'
sys.path.insert(0, str(WEIGHTED))
import weighted_check as checker
import weighted_proof as producer


def main():
    counts = Counter()
    fixtures = [c for c in ref.fixtures() if 2 <= len(c['unknown']) <= 4][:9]
    metrics = [('flat_gain_v1', 1)] + [('quantised_log_discount_floor_gain_v1', s)
               for s in [10_000, 1_000_000, 100_000_000]]
    for metric, scale in metrics:
        coeff = ref.coefficients(metric, scale)
        for case in fixtures:
            _, cached = ref.audit(case, coeff)
            ranked, known, missing = checker._prepare(case)
            pairs = checker._pair_rows(ranked, known, coeff)
            names = sorted(case['runs'])
            for endpoint in ['set', 'prefix']:
                for a, b in checker.SCENARIOS:
                    rows = checker._scenario_rows(pairs, endpoint, a, b)
                    direct = [(world, ref.margins(ss, endpoint, names[a], names[b]))
                              for world, ss, _ in cached]
                    for world, truth in direct:
                        for j, (fixed, threshold, terms) in enumerate(rows):
                            actual = fixed - threshold + sum(v[world[p]] for p, v in terms.items())
                            assert actual == truth[j]
                            counts['row_value_equalities'] += 1
                    # All nonempty subsets, and root plus a fixed-grade branch,
                    # on two oriented pairs per endpoint. The oracle maximum
                    # directly traverses the residual domain of actual scores.
                    if (a, b) not in [(0, 1), (2, 3)]:
                        continue
                    first = sorted(case['unknown'])[0]
                    for assigned in [{}, {first: 0}, {first: 2}]:
                        residual = [values for world, values in direct
                                    if all(world[p] == grade for p, grade in assigned.items())]
                        for size in range(1, len(rows)+1):
                            for subset in combinations(range(len(rows)), size):
                                fixed, threshold, terms = checker._combine(rows, subset)
                                analytic = fixed - threshold + sum(v[assigned[p]] if p in assigned else high
                                                                  for p, v, high in terms)
                                observed = max(sum(values[j] for j in subset) for values in residual)
                                assert analytic == observed
                                counts['exact_subset_bound_equalities'] += 1

    cli = []
    with tempfile.TemporaryDirectory(prefix='weighted_cli_') as name:
        temp = Path(name)
        case = ref.fixtures()[4]
        casepath = temp/'case.json'; casepath.write_text(json.dumps(case))
        digest = sha256(casepath.read_bytes()).hexdigest()
        recordpath = temp/'record.json'
        for metric, scale in [metrics[0], metrics[2]]:
            produce = subprocess.run([sys.executable, str(WEIGHTED/'weighted_proof.py'), str(casepath),
                '--endpoint','set','--metric',metric,'--scale',str(scale)],capture_output=True,text=True)
            assert produce.returncode == 0, produce.stderr
            record = json.loads(produce.stdout)
            recordpath.write_text(produce.stdout)
            cmd = [sys.executable,str(WEIGHTED/'weighted_check.py'),'--cases',str(casepath),
                '--cases-sha256',digest,'--case-id',case['id'],'--endpoint','set','--record',str(recordpath),
                '--metric',metric,'--scale',str(scale)]
            checked = subprocess.run(cmd,capture_output=True,text=True)
            assert checked.returncode == 0 and json.loads(checked.stdout)['accepted']
            cli.append({'metric':metric,'scale':scale,'case_id':case['id'],'valid_cli':'passed'})
            badcmd = cmd[:];badcmd[badcmd.index('--cases-sha256')+1] = '0'*64
            checked = subprocess.run(badcmd,capture_output=True,text=True)
            assert checked.returncode == 1 and not json.loads(checked.stdout)['accepted']
            counts['cli_hash_rejections'] += 1
            counts['valid_cli_productions_and_checks'] += 1
        # Duplicate keys are rejected by producer CLI, rather than silently
        # inheriting the last value supplied by a JSON parser.
        casepath.write_text('{"id":"a","id":"b"}')
        result = subprocess.run([sys.executable,str(WEIGHTED/'weighted_proof.py'),str(casepath),
                                 '--endpoint','set'],capture_output=True,text=True)
        assert result.returncode == 2
        counts['producer_cli_duplicate_key_rejections'] += 1
        # An unresolved certificate is preserved as an abstention across the
        # two command-line interfaces, and never exits as a verified claim.
        common = next(c for c in ref.fixtures() if c['id']=='all-common-four-unknown')
        casepath.write_text(json.dumps(common));digest=sha256(casepath.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable,str(WEIGHTED/'weighted_proof.py'),str(casepath),
            '--endpoint','set','--node-limit','1'],capture_output=True,text=True)
        assert result.returncode == 3 and json.loads(result.stdout)['status']=='unresolved'
        recordpath.write_text(result.stdout)
        result = subprocess.run([sys.executable,str(WEIGHTED/'weighted_check.py'),
            '--cases',str(casepath),'--cases-sha256',digest,'--case-id',common['id'],
            '--endpoint','set','--record',str(recordpath)],capture_output=True,text=True)
        assert result.returncode == 3 and json.loads(result.stdout)['state']=='unresolved'
        counts['cli_abstention_roundtrips'] += 1
    result = {'status':'passed','scope':'direct full-score row comparison; exact residual-domain maximum; native local CLI',
              'fixtures':len(fixtures),'counts':dict(counts),'cli':cli,
              'source_sha256':{p.name:sha256(p.read_bytes()).hexdigest() for p in [
                  Path(__file__),HERE/'independent_reference.py',WEIGHTED/'weighted_proof.py',WEIGHTED/'weighted_check.py']}}
    (HERE/'bounds_cli_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
