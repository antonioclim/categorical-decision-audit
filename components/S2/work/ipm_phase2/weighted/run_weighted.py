"""Run the four prospectively specified metric variants on pinned case bytes."""
import argparse
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
import platform
from time import perf_counter

import weighted_proof as p
import weighted_check as c

VARIANTS=((p.FLAT,1),(p.DISCOUNTED,10_000),(p.DISCOUNTED,1_000_000),(p.DISCOUNTED,100_000_000))
PROTOCOL_SHA256='2512503c45c5aa18e30d4905ac2c45ecd5a74373e9cb4ddde20535eeb05d714a'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,required=True)
    parser.add_argument('--cases-sha256',required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raw=args.cases.read_bytes()
    if sha256(raw).hexdigest()!=args.cases_sha256: parser.error('Case file hash mismatch')
    if sha256(args.protocol.read_bytes()).hexdigest()!=PROTOCOL_SHA256: parser.error('Prospective protocol hash mismatch')
    cases=c.parse_json(raw,max_bytes=c.CASE_FILE_BYTES_CAP)
    if type(cases) is not list: parser.error('Expected case list')
    ids=[case.get('id') for case in cases if type(case) is dict]
    if len(ids)!=len(cases) or len(set(ids))!=len(ids): parser.error('Invalid or duplicate case ids')
    for case in cases: p.prepare(case)
    if args.output.exists(): parser.error('Use a new output directory')
    args.output.mkdir(parents=True)
    records=[]
    counters=defaultdict(Counter)
    start=perf_counter()
    for metric,scale in VARIANTS:
        key=f'{metric}:{scale}'
        for case in cases:
            for endpoint in ('set','prefix'):
                begin=perf_counter()
                record=p.produce(case,endpoint,metric=metric,scale=scale)
                production=perf_counter()-begin
                # Simulate JSON transport; checker receives decoded wire bytes.
                wire=p.canonical_bytes(record)
                begin=perf_counter()
                result=c.verify(case,endpoint,c.parse_json(wire),metric=metric,scale=scale)
                checking=perf_counter()-begin
                if record['status']!='unresolved' and not result['accepted']:
                    raise RuntimeError((case['id'],endpoint,key,result))
                if record['status']=='unresolved' and result['state']!='unresolved':
                    raise RuntimeError((case['id'],endpoint,key,result))
                stratum=case.get('stratum','unspecified')
                counters[key][record['status']]+=1
                counters[key][f'{stratum}:{endpoint}:{record["status"]}']+=1
                if result['accepted']: counters[key]['verified']+=1
                records.append({'case_id':case['id'],'qid':case.get('qid'), 'stratum':stratum,
                    'metric':metric,'scale':scale,'endpoint':endpoint,'record':record,'verification':result,
                    'production_seconds':production,'check_seconds':checking})
        print(key,dict(counters[key]),flush=True)
    here=Path(__file__).resolve().parent
    summaries={'status':'completed','cases':len(cases),'requests':len(records),'case_file_sha256':args.cases_sha256,
               'protocol_sha256':PROTOCOL_SHA256,'python':platform.python_version(),'metrics':{key:dict(value) for key,value in counters.items()},
               'source_sha256':{name:sha256((here/name).read_bytes()).hexdigest() for name in ('weighted_proof.py','weighted_check.py','metric_tables.json','run_weighted.py')},
               'elapsed_seconds':perf_counter()-start,'timing_scope':'Execution diagnostics on a shared host; not a matched speed benchmark',
               'validation_scope':'Producer records checked by separate reconstruction; compare with independent enumeration separately'}
    (args.output/'records.json').write_text(json.dumps(records,sort_keys=True,indent=2)+'\n')
    (args.output/'summary.json').write_text(json.dumps(summaries,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summaries.items() if k!='metrics'},indent=2))

if __name__=='__main__': main()
