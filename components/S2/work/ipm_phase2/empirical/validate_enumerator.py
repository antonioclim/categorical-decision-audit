"""Validate compiled traversal against an independently written Python oracle."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

HERE=Path(__file__).resolve().parent
import independent_reference_snapshot as independent
import run_empirical as run

def main():
    started=perf_counter();counts=Counter();tables={}
    for metric,scale in run.METRICS:
        actual=run.coefficient_table(metric,scale);certified=independent.coefficients(metric,scale)
        assert actual==certified
        tables[f'{metric}:{scale}']={'sha256':sha256(run.canonical(actual)).hexdigest(),'table':actual,'independent_certification':'rational logarithm enclosure'}
        for case in independent.fixtures():
            got=run.run_case(case,metric,scale)
            joint=Counter();changes=Counter();strict=Counter();robust=Counter()
            names=sorted(case['runs']);name_indices={n:i for i,n in enumerate(names)}
            for world in independent.all_worlds(case):
                ss=independent.scores(case,world,certified)
                oo=independent.outcomes(ss)
                orders=[]
                for p in ('binary','graded'):
                    full=tuple(sorted(names,key=lambda n:(-ss[p][n],n)))
                    orders.append(tuple(name_indices[n] for n in full))
                joint[orders[0],orders[1]]+=1
                for endpoint in ('set','prefix'):
                    change=oo['binary'][endpoint]!=oo['graded'][endpoint]
                    changes[endpoint]+=int(change)
                    gaps=[]
                    for p in ('binary','graded'):
                        values=sorted(ss[p].values(),reverse=True)
                        gaps.extend([values[2]-values[3]] if endpoint=='set' else [values[i]-values[i+1] for i in range(3)])
                    strict[endpoint]+=int(change and all(g>0 for g in gaps))
                    robust[endpoint]+=int(change and all(g>20 for g in gaps))
                counts['python_completions_checked']+=1
            observed={(run.ORDERINGS[v['binary_order_index']],run.ORDERINGS[v['graded_order_index']]):v['count'] for v in got['joint_full_orders']}
            assert observed==dict(joint),(metric,scale,case['id'],'joint')
            for endpoint in ('set','prefix'):
                result=got['endpoints'][endpoint]
                assert result['change_worlds']==changes[endpoint]
                assert result['strict_change_worlds']==strict[endpoint]
                if metric!='flat_gain_v1':assert result['conservative_real_metric_strict_change_worlds']==robust[endpoint]
            counts['case_metric_checks']+=1
    # Reject wide reference domains without launching an exponential C run.
    case={'id':'wide-40','runs':{n:[f'{n}-{i}' for i in range(10)] for n in 'ABCD'},'known':{},'unknown':[f'{n}-{i}' for n in 'ABCD' for i in range(10)]}
    assert run.run_case(case,'flat_gain_v1',1)['status']=='unresolved'
    counts['budget_checks']+=1
    result={'status':'passed','counts':dict(counts),'fixtures':len(independent.fixtures()),'metrics':4,'tables':tables,'elapsed_seconds':perf_counter()-started,'compiler_flags':['cc','-O3','-std=c11','-Wall','-Wextra','-Werror'],'compiler_version':subprocess.run(['cc','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],'c_source_sha256':sha256((HERE/'exhaustive_weighted.c').read_bytes()).hexdigest(),'c_binary_sha256':sha256((HERE/'exhaustive_weighted').read_bytes()).hexdigest(),'independent_oracle_sha256':sha256((HERE/'independent_reference_snapshot.py').read_bytes()).hexdigest(),'scope':'synthetic validation of direct integer enumeration and independently certified coefficient tables; original validation preceded empirical extension execution and this rerun fixes a standalone oracle snapshot'}
    (HERE/'enumerator_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='tables'},indent=2))

if __name__=='__main__':main()
