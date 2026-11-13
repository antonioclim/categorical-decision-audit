"""Produce versioned four-run top-three evidence for flat or quantised gain.

Position order is part of the trusted case. A shared unknown passage has one
grade under every run and both profiles. The proof verifier is a separate
module and does not import this producer.
"""
import argparse
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path

SCHEMA = 'paperm_weighted_split_cover_v1'
FLAT = 'flat_gain_v1'
DISCOUNTED = 'quantised_log_discount_floor_gain_v1'
SCALES = (10_000, 1_000_000, 100_000_000)
GAINS = ((0,0,1,1),(0,1,2,3))
NODE_LIMIT = 4096
RECORD_BYTES_CAP = 1_048_576
TABLE_FILE_SHA256 = 'b19c450ecb9d0ae55225bfc8c773763714da2396d1e7212cd957176cc0508bab'

def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def digest(value):
    return sha256(canonical_bytes(value)).hexdigest()

def metric_table(metric, scale):
    if type(metric) is not str or type(scale) is not int:
        raise ValueError('Metric and scale have invalid types')
    if metric == FLAT and scale == 1:
        return tuple((0,1,2,3) for _ in range(10))
    if metric != DISCOUNTED or scale not in SCALES:
        raise ValueError('Unsupported metric or scale')
    raw=Path(__file__).with_name('metric_tables.json').read_bytes()
    if sha256(raw).hexdigest()!=TABLE_FILE_SHA256:
        raise ValueError('Metric table registry differs from certified bytes')
    return tuple(tuple(row) for row in json.loads(raw)[str(scale)])

def descriptor(metric,scale):
    table=metric_table(metric,scale)
    return {'name':metric,'scale':scale,'rounding':'none' if metric==FLAT else 'floor_after_gain',
            'gains':[list(g) for g in GAINS], 'gain_table_sha256':digest(table),
            'run_count':4,'depth':10,'top_k':3,'unknown_domain':[0,1,2,3],
            'tie_rule':'ascending lexical run identifier','rank_convention':'one_based_list_order'}

def _name(value):
    return type(value) is str and 0<len(value)<=1024

def prepare(case):
    if type(case) is not dict or not {'id','runs','known','unknown'}<=set(case) or not set(case)<={'id','runs','known','unknown','qid','stratum'}:
        raise ValueError('Unsupported case fields')
    if not _name(case['id']) or any(not _name(case[k]) for k in ('qid','stratum') if k in case):
        raise ValueError('Invalid case metadata')
    runs,known,unknown=case['runs'],case['known'],case['unknown']
    if type(runs) is not dict or len(runs)!=4 or not all(_name(n) for n in runs):
        raise ValueError('Exactly four named runs are required')
    for docs in runs.values():
        if type(docs) is not list or len(docs)!=10 or not all(_name(p) for p in docs) or len(set(docs))!=10:
            raise ValueError('Each run requires ten distinct passage ids')
    if type(known) is not dict or not all(_name(p) and type(g) is int and 0<=g<=3 for p,g in known.items()):
        raise ValueError('Invalid known grades')
    if type(unknown) is not list or not all(_name(p) for p in unknown) or len(set(unknown))!=len(unknown):
        raise ValueError('Invalid unknown passage ids')
    if set(unknown)&set(known) or set(unknown)|set(known)!=set().union(*map(set,runs.values())):
        raise ValueError('Known and unknown ids must partition the run union')
    if len(canonical_bytes(case))>RECORD_BYTES_CAP:
        raise ValueError('Case exceeds one MiB')
    return tuple(tuple(runs[n]) for n in sorted(runs)),known,tuple(sorted(unknown))

def identity(case,endpoint,metric,scale):
    head={'schema':SCHEMA,'case_id':case['id'],'case_sha256':digest(case),'endpoint':endpoint,
          'metric':descriptor(metric,scale)}
    return head|{'request_sha256':digest(head)}

def orientations(endpoint):
    for a in range(4):
        for b in range(4):
            if a==b: continue
            if endpoint=='set':
                yield [(0,i,a) for i in range(4) if i!=a]+[(1,i,b) for i in range(4) if i!=b]
            else:
                yield [(0,a,b),(1,b,a)]

def row_data(spec,runs,known,unknown,table):
    ranks=[{p:r for r,p in enumerate(docs)} for docs in runs]
    rows=[]
    for profile,left,right in spec:
        def effect(p,g):
            gain=GAINS[profile][g]
            return ((table[ranks[left][p]][gain] if p in ranks[left] else 0)
                    -(table[ranks[right][p]][gain] if p in ranks[right] else 0))
        fixed=sum(effect(p,g) for p,g in known.items())-int(left>right)
        terms=[tuple(effect(p,g) for g in range(4)) for p in unknown]
        rows.append((fixed,terms))
    return rows

def bound_data(rows):
    for size in range(1,len(rows)+1):
        for subset in combinations(range(len(rows)),size):
            fixed=sum(rows[j][0] for j in subset)
            columns=list(zip(*(rows[j][1] for j in subset)))
            vectors=[tuple(map(sum,zip(*col))) for col in columns]
            maxima=[max(v) for v in vectors]
            yield subset,fixed+sum(maxima),vectors,maxima

def changed(runs,labels,endpoint,table):
    outcomes=[]
    for gains in GAINS:
        scores=[sum(table[r][gains[labels[p]]] for r,p in enumerate(docs)) for docs in runs]
        order=tuple(sorted(range(4),key=lambda i:(-scores[i],i))[:3])
        outcomes.append(tuple(sorted(order)) if endpoint=='set' else order)
    return outcomes[0]!=outcomes[1]

def resolve(rows,unknown,count,node_limit):
    data=[]
    for subset,maximum,vectors,maxima in bound_data(rows):
        if maximum<0:
            if count[0]>=node_limit: return 'unresolved',None
            count[0]+=1
            return 'invariant',{'subset':list(subset)}
        data.append((subset,maximum,vectors,maxima))
    order=sorted(range(len(unknown)),key=lambda k:(-sum(max(t[k])-min(t[k]) for _,t in rows),k))
    order=[k for k in order if any(any(t[k]) for _,t in rows)]
    assignment={}
    def descend(depth,bounds,current):
        if count[0]>=node_limit: return 'unresolved',None
        count[0]+=1
        for maximum,(subset,_,_,_) in zip(bounds,data):
            if maximum<0: return 'invariant',{'subset':list(subset)}
        # Every coefficient at grade zero is zero for both registered metrics.
        if all(v>=0 for v in current):
            return 'changed',{p:assignment.get(k,0) for k,p in enumerate(unknown)}
        if depth==len(order): raise AssertionError('Uncovered infeasible singleton')
        k=order[depth]
        children=[]
        for grade in range(4):
            assignment[k]=grade
            child_bounds=[v+terms[k][grade]-maxima[k] for v,(_,_,terms,maxima) in zip(bounds,data)]
            child_current=[v+terms[k][grade] for v,(_,terms) in zip(current,rows)]
            state,payload=descend(depth+1,child_bounds,child_current)
            if state!='invariant': return state,payload
            children.append(payload)
        del assignment[k]
        return 'invariant',{'split':unknown[k],'children':children}
    return descend(0,[d[1] for d in data],[fixed for fixed,_ in rows])

def produce(case,endpoint,*,metric=DISCOUNTED,scale=1_000_000,node_limit=NODE_LIMIT):
    if type(endpoint) is not str or endpoint not in ('set','prefix'):
        raise ValueError('Unknown endpoint')
    if type(node_limit) is not int or not 1<=node_limit<=NODE_LIMIT:
        raise ValueError('Node limit outside 1..4096')
    runs,known,unknown=prepare(case)
    table=metric_table(metric,scale)
    head=identity(case,endpoint,metric,scale)
    for grade in (0,3):
        witness=dict.fromkeys(unknown,grade)
        if changed(runs,known|witness,endpoint,table):
            return head|{'status':'changed','witness':witness}
    count,trees=[0],[]
    for spec in orientations(endpoint):
        state,payload=resolve(row_data(spec,runs,known,unknown,table),unknown,count,node_limit)
        if state=='unresolved': return head|{'status':'unresolved','reason':'node_limit'}
        if state=='changed':
            if not changed(runs,known|payload,endpoint,table): raise AssertionError('Invalid witness')
            return head|{'status':'changed','witness':payload}
        trees.append(payload)
    record=head|{'status':'invariant','trees':trees}
    if len(canonical_bytes(record))>RECORD_BYTES_CAP:
        return head|{'status':'unresolved','reason':'record_byte_limit'}
    return record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case',type=Path)
    parser.add_argument('--endpoint',choices=('set','prefix'),required=True)
    parser.add_argument('--metric',choices=(FLAT,DISCOUNTED),default=DISCOUNTED)
    parser.add_argument('--scale',type=int,default=1_000_000)
    parser.add_argument('--node-limit',type=int,default=NODE_LIMIT)
    args=parser.parse_args()
    # Reuse only the strict JSON input parser; production and verification
    # score construction do not share code.
    from weighted_check import parse_json
    try:
        with args.case.open('rb') as stream: raw=stream.read(RECORD_BYTES_CAP+1)
        case=parse_json(raw,max_bytes=RECORD_BYTES_CAP)
        record=produce(case,args.endpoint,metric=args.metric,scale=args.scale,node_limit=args.node_limit)
    except (ValueError,OSError,TypeError,UnicodeError,RecursionError) as exc:
        parser.exit(2,f'Invalid input: {exc}\n')
    print(json.dumps(record,ensure_ascii=False,sort_keys=True,allow_nan=False))
    return 3 if record['status']=='unresolved' else 0

if __name__=='__main__':
    raise SystemExit(main())
