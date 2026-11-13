"""Independent integer exhaustive audit; no proof producer/checker imports."""
import argparse
from collections import Counter
from decimal import Decimal, localcontext
from hashlib import sha256
from itertools import permutations
import json
from pathlib import Path
import platform
import subprocess
from time import perf_counter

HERE=Path(__file__).resolve().parent
ORDERINGS=tuple(permutations(range(4)))
METRICS=(('flat_gain_v1',1),('quantised_log_discount_floor_gain_v1',10_000),('quantised_log_discount_floor_gain_v1',1_000_000),('quantised_log_discount_floor_gain_v1',100_000_000))
HASHES={'dl21':'20cc22dcc68041622b507078d449ceb39b9bfcab2fdc727d31bab3fbcdca732b','dl22':'7d1bf9def75a146a50383dc817e83e99520d96259f771db860beb06a89581a66'}
PROTOCOL_SHA256='2512503c45c5aa18e30d4905ac2c45ecd5a74373e9cb4ddde20535eeb05d714a'

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def coefficient_table(metric,scale):
    if metric=='flat_gain_v1':
        if scale!=1: raise ValueError('Flat scale must equal one')
        return tuple((0,1,2,3) for _ in range(10))
    if metric!='quantised_log_discount_floor_gain_v1' or scale not in (10_000,1_000_000,100_000_000):
        raise ValueError('Unsupported metric or scale')
    result=[]
    with localcontext() as c:
        c.prec=100
        for rank in range(1,11):
            base=rank+1
            if base&(base-1)==0:
                exponent=base.bit_length()-1
                result.append(tuple(gain*scale//exponent for gain in range(4)))
            else:
                discount=Decimal(2).ln()/Decimal(base).ln()
                result.append(tuple(int(Decimal(gain*scale)*discount) for gain in range(4)))
    return tuple(result)

def prepare(case,table):
    names=tuple(sorted(case['runs']));unknown=tuple(sorted(case['unknown']))
    assert len(names)==4
    assert len(set(unknown))==len(unknown)
    assert set(unknown).isdisjoint(case['known'])
    assert set(unknown)|set(case['known'])==set().union(*map(set,case['runs'].values()))
    assert all(len(v)==len(set(v))==10 for v in case['runs'].values())
    assert all(type(g) is int and 0<=g<=3 for g in case['known'].values())
    ranks={name:{p:i for i,p in enumerate(case['runs'][name])} for name in names}
    known=[];terms=[]
    for profile in ('binary','graded'):
        for name in names:
            known.append(sum(table[rank][int(case['known'][p]>=2) if profile=='binary' else case['known'][p]] for p,rank in ranks[name].items() if p in case['known']))
    for p in unknown:
        terms.append([[table[ranks[name][p]][int(d>=2) if profile=='binary' else d] if p in ranks[name] else 0 for d in range(4)] for profile in ('binary','graded') for name in names])
    return names,unknown,known,terms

def score_order(case,completion,table,profile):
    labels=case['known']|completion
    names=tuple(sorted(case['runs']))
    scores=[sum(table[rank][int(labels[p]>=2) if profile=='binary' else labels[p]] for rank,p in enumerate(case['runs'][name])) for name in names]
    order=tuple(sorted(range(4),key=lambda i:(-scores[i],i)))
    return scores,order

def run_case(case,metric,scale,binary=None):
    table=coefficient_table(metric,scale)
    names,unknown,known,terms=prepare(case,table)
    worlds=4**len(unknown)
    header={'case_id':case['id'],'case_sha256':sha256(canonical(case)).hexdigest(),'stratum':case.get('stratum','unspecified'),'qid':case.get('qid'),'unknown_count':len(unknown),'metric':metric,'scale':scale,'table_sha256':sha256(canonical(table)).hexdigest(),'worlds':worlds}
    if worlds>2**28:return header|{'status':'unresolved','reason':'enumeration_budget','completions_checked':0}
    values=[len(unknown),*known,*[x for rows in terms for row in rows for x in row]]
    t=perf_counter()
    proc=subprocess.run([str(binary or HERE/'exhaustive_weighted')],input=' '.join(map(str,values))+'\n',capture_output=True,text=True,check=True)
    raw=json.loads(proc.stdout)
    assert raw['worlds']==worlds and sum(raw['joint'])==worlds
    joint=[{'binary_order_index':b,'graded_order_index':g,'count':raw['joint'][b*24+g]} for b in range(24) for g in range(24) if raw['joint'][b*24+g]]
    point={}
    for grade,label in ((0,'zero'),(3,'three')):
        completion=dict.fromkeys(unknown,grade)
        b=score_order(case,completion,table,'binary')[1];g=score_order(case,completion,table,'graded')[1]
        point[label]={'set':b[3]!=g[3],'prefix':b!=g}
    endpoints={}
    for e in ('set','prefix'):
        transform=(lambda o:tuple(sorted(o[:3]))) if e=='set' else (lambda o:o[:3])
        marginal_b=sorted({transform(ORDERINGS[r['binary_order_index']]) for r in joint})
        marginal_g=sorted({transform(ORDERINGS[r['graded_order_index']]) for r in joint})
        change=raw[e+'_change_worlds']
        endpoints[e]={'change_worlds':change,'strict_change_worlds':raw['strict_'+e+'_change_worlds'],'any_change':change>0,'strict_change':raw['strict_'+e+'_change_worlds']>0,'all_zero_disagrees':point['zero'][e],'all_three_disagrees':point['three'][e],'missed_by_zero':change>0 and not point['zero'][e],'missed_by_both_points':change>0 and not point['zero'][e] and not point['three'][e],'equal_marginal_sets':marginal_b==marginal_g,'change_with_equal_marginal_sets':change>0 and marginal_b==marginal_g,'marginal_binary':marginal_b,'marginal_graded':marginal_g,'always_change':change==worlds}
        if metric!='flat_gain_v1':
            endpoints[e]['conservative_real_metric_strict_change_worlds']=raw['margin_gt20_'+e+'_change_worlds']
    return header|{'status':'exact','completions_checked':worlds,'elapsed_seconds':perf_counter()-t,'endpoints':endpoints,'joint_full_orders':joint}

def summarise(cases):
    strata={}
    for stratum in sorted({c['stratum'] for c in cases}):
        rows=[c for c in cases if c['stratum']==stratum];exact=[c for c in rows if c['status']=='exact']
        out={'cases':len(rows),'exact':len(exact),'unresolved':len(rows)-len(exact),'completions_checked':sum(c['completions_checked'] for c in rows)}
        for endpoint in ('set','prefix'):
            keys=['any_change','strict_change','all_zero_disagrees','all_three_disagrees','missed_by_zero','missed_by_both_points','equal_marginal_sets','change_with_equal_marginal_sets','always_change']
            out[endpoint]={k:sum(c['endpoints'][endpoint][k] for c in exact) for k in keys}
        strata[stratum]=out
    return strata

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cohort',choices=HASHES);p.add_argument('cases',type=Path);p.add_argument('output',type=Path);p.add_argument('--flat-only',action='store_true');a=p.parse_args()
    raw=a.cases.read_bytes();digest=sha256(raw).hexdigest();assert digest==HASHES[a.cohort],(digest,HASHES[a.cohort])
    protocol=HERE.parent/'PROTOCOL_DISCOUNT.md'
    if not a.flat_only and not protocol.is_file():raise RuntimeError('Frozen protocol required before discounted empirical outcomes')
    if not a.flat_only and sha256(protocol.read_bytes()).hexdigest()!=PROTOCOL_SHA256:raise RuntimeError('Frozen protocol digest differs')
    cases=json.loads(raw)
    a.output.mkdir(parents=True,exist_ok=True)
    for metric,scale in (METRICS[:1] if a.flat_only else METRICS):
        path=a.output/f'{metric}_{scale}.json'
        if path.exists():raise RuntimeError(f'Will not overwrite {path}')
        start=perf_counter();results=[]
        for i,case in enumerate(cases):
            result=run_case(case,metric,scale);results.append(result)
            print(f'{a.cohort} {scale} {i+1}/{len(cases)} {case["id"]} {result["status"]} worlds={result["worlds"]} elapsed={perf_counter()-start:.2f}s',flush=True)
        result={'cohort':a.cohort,'input_sha256':digest,'protocol_sha256':sha256(protocol.read_bytes()).hexdigest() if protocol.exists() else None,'metric':metric,'scale':scale,'coefficient_table':coefficient_table(metric,scale),'coefficient_table_sha256':sha256(canonical(coefficient_table(metric,scale))).hexdigest(),'python':platform.python_version(),'c_source_sha256':sha256((HERE/'exhaustive_weighted.c').read_bytes()).hexdigest(),'c_binary_sha256':sha256((HERE/'exhaustive_weighted').read_bytes()).hexdigest(),'case_count':len(cases),'completions_checked':sum(x['completions_checked'] for x in results),'elapsed_seconds':perf_counter()-start,'orderings':ORDERINGS,'by_stratum':summarise(results),'by_case':{r['case_id']:r for r in results},'coefficient_note':'Decimal100 independently reconstructs table; exact certification must be crosschecked separately','real_metric_note':'Positive cut-off or prefix gaps >20 integer units imply signs stable under conservative error bound 2D/scale, D=10. This is only a sufficient witness-level condition, not exact real-DCG invariance.'}
        path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'saved':str(path),'by_stratum':result['by_stratum']}),flush=True)

if __name__=='__main__':main()
