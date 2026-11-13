"""Exact shared-completion cross-scale and tie diagnostics."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter
import run_empirical as run

HERE=Path(__file__).resolve().parent
SCALES=(10_000,1_000_000,100_000_000)
PAIRS=((0,1),(0,2),(1,2))

def inspect(case):
    all_terms=[];all_known=[];unknown=tuple(sorted(case['unknown']))
    if len(unknown)>14:return {'case_id':case['id'],'status':'unresolved','completions_checked':0}
    for scale in SCALES:
        names,u,known,terms=run.prepare(case,run.coefficient_table('quantised_log_discount_floor_gain_v1',scale))
        assert u==unknown;all_known+=known;all_terms.append(terms)
    flattened=[len(unknown),*all_known]
    for u in range(len(unknown)):
        for scale in range(3):
            for row in all_terms[scale][u]:flattened+=row
    proc=subprocess.run([str(HERE/'compare_scales')],input=' '.join(map(str,flattened))+'\n',capture_output=True,text=True,check=True)
    raw=json.loads(proc.stdout);assert raw['worlds']==4**len(unknown)
    pairs=[]
    for p,(a,b) in enumerate(PAIRS):
        d={'scales':[SCALES[a],SCALES[b]],'any_full_order_change_worlds':raw['any_order_changes'][p], 'agreement_indicator_changed_worlds':dict(zip(('set','prefix'),raw['indicator_changes'][p*2:p*2+2]))}
        for j,profile in enumerate(('binary','graded')):d[profile]=dict(zip(('set','prefix'),raw['output_changes'][p*4+j*2:p*4+j*2+2]))
        pairs.append(d)
    margins=[]
    for scale_id,scale in enumerate(SCALES):
        d={'scale':scale}
        for profile_id,profile in enumerate(('binary','graded')):
            k=scale_id*2+profile_id
            d[profile]={name:raw[name][k] for name in ['cut_ties','any_ties','small_positive_cut','small_positive_any','min_positive_cut','min_positive_any']}
        margins.append(d)
    return {'case_id':case['id'],'case_sha256':sha256(run.canonical(case)).hexdigest(),'stratum':case.get('stratum'),'unknown_count':len(unknown),'status':'exact','completions_checked':raw['worlds'],'pairs':pairs,'margins':margins}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cohort',choices=run.HASHES);p.add_argument('cases',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    raw=a.cases.read_bytes();assert sha256(raw).hexdigest()==run.HASHES[a.cohort]
    protocol=HERE.parent/'PROTOCOL_DISCOUNT.md';assert sha256(protocol.read_bytes()).hexdigest()==run.PROTOCOL_SHA256
    if a.output.exists():raise RuntimeError('Output already exists')
    cases=json.loads(raw);start=perf_counter();results=[]
    for i,case in enumerate(cases):
        results.append(inspect(case));print(f'{a.cohort} scales {i+1}/{len(cases)} {case["id"]}',flush=True)
    summary={}
    for stratum in sorted({r['stratum'] for r in results}):
        rows=[r for r in results if r['stratum']==stratum];summary[stratum]={'cases':len(rows),'completions_checked':sum(r['completions_checked'] for r in rows),'pairs':[]}
        for pi,(aidx,bidx) in enumerate(PAIRS):
            pairs=[r['pairs'][pi] for r in rows if r['status']=='exact']
            x={'scales':[SCALES[aidx],SCALES[bidx]],'cases_with_any_full_order_change':sum(r['any_full_order_change_worlds']>0 for r in pairs),'full_order_change_worlds':sum(r['any_full_order_change_worlds'] for r in pairs),'agreement_indicator_changed_worlds':{e:sum(r['agreement_indicator_changed_worlds'][e] for r in pairs) for e in ('set','prefix')}}
            summary[stratum]['pairs'].append(x)
    result={'cohort':a.cohort,'input_sha256':sha256(raw).hexdigest(),'protocol_sha256':run.PROTOCOL_SHA256,'source_sha256':sha256((HERE/'compare_scales.c').read_bytes()).hexdigest(),'binary_sha256':sha256((HERE/'compare_scales').read_bytes()).hexdigest(),'scales':SCALES,'case_count':len(results),'completions_checked':sum(r['completions_checked'] for r in results),'elapsed_seconds':perf_counter()-start,'by_stratum':summary,'by_case':{r['case_id']:r for r in results},'note':'These compare exactly the same completion across scales; counts carry no probability model. Small positive means integer gap 1..20. Minimum -1 denotes no strictly positive gap observed.'}
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
