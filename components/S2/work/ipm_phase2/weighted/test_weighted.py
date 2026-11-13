"""Native integration and flat-compatibility tests for the weighted route.

Independent direct-scoring/oracle tests are provided by the validation task.
This suite checks unchanged flat verdicts, binding and the CLI separately.
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import weighted_proof as p
import weighted_check as c
from build_metric_tables import build

HERE=Path(__file__).resolve().parent
PHASE1=HERE.parents[1]/'ipm_phase1'

def main():
    counts=Counter()
    tables,_=build()
    assert tables==json.loads((HERE/'metric_tables.json').read_text())
    counts['certified_coefficient_tables']=3
    origpath=PHASE1/'supplement/work/paperm_proof/proof.py'
    spec=importlib.util.spec_from_file_location('flat_original_producer',origpath)
    orig=importlib.util.module_from_spec(spec);spec.loader.exec_module(orig)
    cases=json.loads((PHASE1/'supplement/work/paperm_proof/stress_cases.json').read_text())
    records=[]
    for case in cases:
        for endpoint in ('set','prefix'):
            original=orig.produce(case,endpoint)
            record=p.produce(case,endpoint,metric=p.FLAT,scale=1)
            assert original['status']==record['status']
            result=c.verify(case,endpoint,record,metric=p.FLAT,scale=1)
            assert result['accepted']
            counts['flat_requests_matched']+=1
            counts['flat_'+record['status']]+=1
            records.append((case,endpoint,record))
    # Verify strict numeric-type binding and every metric-semantic field.
    case,endpoint,record=records[0]
    for key,value in [('name','unknown'),('scale',True),('gains',[[0,0,1,2],[0,1,2,3]]),
                      ('rounding','round'),('depth',11),('run_count',5),('top_k',2),
                      ('unknown_domain',[0,1,2]),('tie_rule','reverse'),
                      ('rank_convention','zero_based'),('gain_table_sha256','0'*64)]:
        altered=deepcopy(record);altered['metric'][key]=value
        assert not c.verify(case,endpoint,altered,metric=p.FLAT,scale=1)['accepted']
        counts['metric_mutations_rejected']+=1
    for key,value in [('schema','old'),('case_sha256','0'*64),('case_id','wrong'),('endpoint','prefix' if endpoint=='set' else 'set'),('request_sha256','f'*64)]:
        altered=deepcopy(record);altered[key]=value
        assert not c.verify(case,endpoint,altered,metric=p.FLAT,scale=1)['accepted']
        counts['header_mutations_rejected']+=1
    altered_case=deepcopy(case)
    name=sorted(case['runs'])[0]
    altered_case['runs'][name][0],altered_case['runs'][name][1]=altered_case['runs'][name][1],altered_case['runs'][name][0]
    assert not c.verify(altered_case,endpoint,record,metric=p.FLAT,scale=1)['accepted']
    counts['rank_binding_mutations_rejected']+=1
    assert c.verify(case,endpoint,record,metric=p.FLAT,scale=True)['state']=='rejected'
    counts['trusted_boolean_scale_rejected']+=1
    invariant=next(item for item in records if item[2]['status']=='invariant')
    abstention=p.produce(invariant[0],invariant[1],metric=p.FLAT,scale=1,node_limit=1)
    assert abstention['status']=='unresolved'
    assert c.verify(invariant[0],invariant[1],abstention,metric=p.FLAT,scale=1)['state']=='unresolved'
    counts['node_budget_abstention']=1
    # The coefficient table for the primary scale agrees with phase 1.
    sys.path.insert(0,str(PHASE1/'code_review'))
    import quantised_dcg
    assert p.metric_table(p.DISCOUNTED,1_000_000)==quantised_dcg.GAIN_TABLE
    counts['phase1_table_compatibility']=1
    with TemporaryDirectory() as temp:
        cp=Path(temp)/'case.json';rp=Path(temp)/'record.json'
        cp.write_text(json.dumps(case))
        result=subprocess.run([sys.executable,str(HERE/'weighted_proof.py'),str(cp),'--endpoint',endpoint],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        rp.write_text(result.stdout)
        verified=subprocess.run([sys.executable,str(HERE/'weighted_check.py'),'--cases',str(cp),'--cases-sha256',sha256(cp.read_bytes()).hexdigest(),'--case-id',case['id'],'--endpoint',endpoint,'--record',str(rp)],capture_output=True,text=True)
        assert verified.returncode==0,verified.stdout+verified.stderr
        counts['cli_produce_and_verify']=1
    out={'status':'passed','scope':'synthetic integration; no TREC results','counts':dict(counts)}
    (HERE/'integration_tests.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__': main()
