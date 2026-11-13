"""Extract and independently score primary-scale strict completions."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import independent_reference_snapshot as oracle
import run_empirical as run

HERE=Path(__file__).resolve().parent

def extract(case,table):
    names,unknown,known,terms=run.prepare(case,table)
    assert len(unknown)<=14
    values=[len(unknown),*known,*[v for rows in terms for row in rows for v in row]]
    raw=json.loads(subprocess.run([str(HERE/'find_strict_witnesses')],input=' '.join(map(str,values))+'\n',capture_output=True,text=True,check=True).stdout)
    records={}
    for endpoint in ('set','prefix'):
        for criterion,threshold in (('strict',0),('margin_gt20',20)):
            number=raw[endpoint+'_'+criterion]
            if number<0:records[endpoint+'_'+criterion]=None;continue
            grades=[0]*len(unknown);v=number
            for i in range(len(unknown)-1,-1,-1):grades[i]=v%4;v//=4
            assert v==0
            world=dict(zip(unknown,grades));scores=oracle.scores(case,world,table);outcomes=oracle.outcomes(scores)
            assert outcomes['binary'][endpoint]!=outcomes['graded'][endpoint]
            margins={}
            for p in ('binary','graded'):
                values=sorted(scores[p].values(),reverse=True)
                margins[p]=[values[2]-values[3]] if endpoint=='set' else [values[i]-values[i+1] for i in range(3)]
                assert all(g>threshold for g in margins[p])
            records[endpoint+'_'+criterion]={'completion_index':number,'completion':world,'scores':scores,'outputs':outcomes,'required_gaps':margins,'criterion':f'all required raw integer margins > {threshold}'}
    return raw,records

def main():
    table=oracle.coefficients('quantised_log_discount_floor_gain_v1',1_000_000);assert table==run.coefficient_table('quantised_log_discount_floor_gain_v1',1_000_000)
    # Exhaustive Python independently validates existence and earliest indices.
    validation=Counter()
    for case in oracle.fixtures():
        raw,records=extract(case,table);expected={k:None for k in records}
        for index,world in enumerate(oracle.all_worlds(case)):
            scores=oracle.scores(case,world,table);oo=oracle.outcomes(scores)
            for endpoint in ('set','prefix'):
                if oo['binary'][endpoint]==oo['graded'][endpoint]:continue
                gaps=[]
                for p in ('binary','graded'):
                    values=sorted(scores[p].values(),reverse=True);gaps += [values[2]-values[3]] if endpoint=='set' else [values[i]-values[i+1] for i in range(3)]
                for criterion,t in (('strict',0),('margin_gt20',20)):
                    key=endpoint+'_'+criterion
                    if expected[key] is None and all(g>t for g in gaps):expected[key]=index
            validation['worlds']+=1
        assert {k:(None if v is None else v['completion_index']) for k,v in records.items()}==expected
        validation['cases']+=1
    output={'metric':'quantised_log_discount_floor_gain_v1','scale':1_000_000,'synthetic_validation':dict(validation),'cohorts':{},'note':'Concrete strict witnesses may differ from the producer first change witness. Integer gaps>20 are only a sufficient sign-preservation check for this completion, not real-DCG invariance.'}
    for cohort,source in [('dl21',HERE.parent/'original_replay/replay/dl21/cases.json'),('dl22',HERE.parent/'original_replay/work/ipm_elevate/mars/cases.json')]:
        raw=source.read_bytes();assert sha256(raw).hexdigest()==run.HASHES[cohort]
        expected=json.loads((HERE/cohort/'quantised_log_discount_floor_gain_v1_1000000.json').read_text())
        records={};counts=Counter()
        for case in json.loads(raw):
            result,witnesses=extract(case,table)
            for endpoint in ('set','prefix'):
                target=expected['by_case'][case['id']]['endpoints'][endpoint]
                assert (witnesses[endpoint+'_strict'] is not None)==target['strict_change']
                assert (witnesses[endpoint+'_margin_gt20'] is not None)==(target['conservative_real_metric_strict_change_worlds']>0)
                for criterion in ('strict','margin_gt20'):
                    if witnesses[endpoint+'_'+criterion] is not None:counts[criterion+'_witnesses']+=1
                if case['stratum']=='natural' and endpoint=='set' and target['missed_by_zero'] and witnesses['set_margin_gt20'] is not None:counts['natural_membership_missed_by_zero_with_margin_gt20_witness']+=1
            records[case['id']]={'case_sha256':sha256(run.canonical(case)).hexdigest(),'stratum':case['stratum'],'search':result,'witnesses':witnesses}
        output['cohorts'][cohort]={'input_sha256':run.HASHES[cohort],'counts':dict(counts),'by_case':records}
    output['source_sha256']={name:sha256((HERE/name).read_bytes()).hexdigest() for name in ['find_strict_witnesses.c','extract_strict_witnesses.py','independent_reference_snapshot.py']}
    (HERE/'strict_witnesses_primary.json').write_text(json.dumps(output,sort_keys=True,indent=2)+'\n');print(json.dumps({'synthetic_validation':dict(validation),'cohorts':{c:r['counts'] for c,r in output['cohorts'].items()}},indent=2))

if __name__=='__main__':main()
