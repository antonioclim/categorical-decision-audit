from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter
import diagnose_scales as ds
import run_empirical as run

HERE=Path(__file__).resolve().parent
import independent_reference_snapshot as independent

def main():
    start=perf_counter();counts=Counter()
    tables={s:independent.coefficients('quantised_log_discount_floor_gain_v1',s) for s in ds.SCALES}
    for case in independent.fixtures():
        actual=ds.inspect(case);expected=[{'any':0,'indicator':Counter(),'binary':Counter(),'graded':Counter()} for _ in ds.PAIRS]
        margins=[{p:{'cut_ties':0,'any_ties':0,'small_positive_cut':0,'small_positive_any':0,'min_positive_cut':None,'min_positive_any':None} for p in ('binary','graded')} for _ in ds.SCALES]
        for world in independent.all_worlds(case):
            data={s:independent.scores(case,world,tables[s]) for s in ds.SCALES}
            outcomes={s:independent.outcomes(data[s]) for s in ds.SCALES}
            for si,s in enumerate(ds.SCALES):
                for p in ('binary','graded'):
                    values=sorted(data[s][p].values(),reverse=True);gaps=[values[k]-values[k+1] for k in range(3)];m=margins[si][p]
                    m['cut_ties']+=gaps[2]==0;m['any_ties']+=0 in gaps;m['small_positive_cut']+=0<gaps[2]<=20;m['small_positive_any']+=any(0<g<=20 for g in gaps)
                    if gaps[2]>0:m['min_positive_cut']=min(m['min_positive_cut'] or gaps[2],gaps[2])
                    for gap in gaps:
                        if gap>0:m['min_positive_any']=min(m['min_positive_any'] or gap,gap)
            for pi,(a,b) in enumerate(ds.PAIRS):
                a,b=ds.SCALES[a],ds.SCALES[b];x=expected[pi]
                x['any']+=any(outcomes[a][p]['prefix']!=outcomes[b][p]['prefix'] for p in ('binary','graded'))
                for e in ('set','prefix'):
                    x['indicator'][e]+=(outcomes[a]['binary'][e]!=outcomes[a]['graded'][e])!=(outcomes[b]['binary'][e]!=outcomes[b]['graded'][e])
                    for p in ('binary','graded'):x[p][e]+=outcomes[a][p][e]!=outcomes[b][p][e]
            counts['worlds']+=1
        for pi,want in enumerate(expected):
            got=actual['pairs'][pi]
            assert got['any_full_order_change_worlds']==want['any']
            assert got['agreement_indicator_changed_worlds']==want['indicator']
            for p in ('binary','graded'):assert got[p]==want[p]
        for si,want in enumerate(margins):
            for p in ('binary','graded'):
                for k in ('min_positive_cut','min_positive_any'):
                    if want[p][k] is None:want[p][k]=-1
                assert actual['margins'][si][p]==want[p]
        counts['cases']+=1
    result={'status':'passed','counts':dict(counts),'scales':ds.SCALES,'source_sha256':sha256((HERE/'compare_scales.c').read_bytes()).hexdigest(),'binary_sha256':sha256((HERE/'compare_scales').read_bytes()).hexdigest(),'oracle_sha256':sha256((HERE/'independent_reference_snapshot.py').read_bytes()).hexdigest(),'elapsed_seconds':perf_counter()-start,'scope':'Independent Python score enumeration validates cross-scale same-completion diagnostics and all tie/minimum/small-margin counters on67 synthetic cases before empirical diagnostics'}
    (HERE/'scale_diagnostics_validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
