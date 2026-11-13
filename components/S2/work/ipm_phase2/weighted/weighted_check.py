"""Independent verifier for versioned weighted split-cover certificates.

Only the trusted case, endpoint and expected metric select the scoring rule.
Untrusted record metadata cannot change the metric, scale, gains or tie rule.
No producer, optimiser, or third-party dependency is imported.
"""
import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path

SCHEMA='paperm_weighted_split_cover_v1'
FLAT='flat_gain_v1'
DISCOUNTED='quantised_log_discount_floor_gain_v1'
WEIGHTS=((0,0,1,1),(0,1,2,3))
SCENARIOS=tuple((a,b) for a in range(4) for b in range(4) if a!=b)
NODE_CAP=4096
RECORD_BYTES_CAP=1_048_576
CASE_FILE_BYTES_CAP=16_777_216
TABLE_FILE_SHA256='b19c450ecb9d0ae55225bfc8c773763714da2396d1e7212cd957176cc0508bab'
HEADER_FIELDS={'schema','case_id','case_sha256','endpoint','metric','request_sha256'}
COMMON_FIELDS=HEADER_FIELDS|{'status'}

class InvalidProof(ValueError): pass

@dataclass
class Counts:
    nodes:int=0
    leaves:int=0
    splits:int=0
    max_depth:int=0
    scenarios:int=0
    rows_in_leaves:int=0

def _unique_object(pairs):
    obj={}
    for key,value in pairs:
        if key in obj: raise InvalidProof('duplicate_json_key')
        obj[key]=value
    return obj

def _reject_constant(value): raise InvalidProof('nonfinite_json_constant')

def _bounded_int(text):
    if len(text)>128: raise InvalidProof('json_integer_digit_budget_exceeded')
    return int(text)

def _finite_float(text):
    value=float(text)
    if not math.isfinite(value): raise InvalidProof('nonfinite_json_number')
    return value

def parse_json(value,*,max_bytes=RECORD_BYTES_CAP):
    try:
        raw=value.encode('utf-8') if type(value) is str else value
        if type(raw) is not bytes or len(raw)>max_bytes: raise InvalidProof('json_type_or_byte_budget')
        return json.loads(raw.decode('utf-8'),object_pairs_hook=_unique_object,
                          parse_int=_bounded_int,parse_float=_finite_float,parse_constant=_reject_constant)
    except InvalidProof: raise
    except (ValueError,UnicodeError,RecursionError) as exc: raise InvalidProof('invalid_json') from exc

def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def _hash(value): return sha256(canonical_bytes(value)).hexdigest()

def _name(value): return type(value) is str and 0<len(value)<=1024

def _grade(value): return type(value) is int and 0<=value<=3

def _prepare(case):
    if type(case) is not dict or not {'id','runs','known','unknown'}<=set(case) or not set(case)<={'id','runs','known','unknown','qid','stratum'}:
        raise InvalidProof('unsupported_case_schema')
    if not _name(case['id']) or any(not _name(case[k]) for k in ('qid','stratum') if k in case):
        raise InvalidProof('invalid_case_metadata')
    runs,known,unknown=case['runs'],case['known'],case['unknown']
    if type(runs) is not dict or len(runs)!=4 or not all(_name(n) for n in runs):
        raise InvalidProof('invalid_run_set')
    for docs in runs.values():
        if type(docs) is not list or len(docs)!=10 or not all(_name(p) for p in docs) or len(set(docs))!=10:
            raise InvalidProof('invalid_ranked_run')
    if type(known) is not dict or not all(_name(p) and _grade(g) for p,g in known.items()):
        raise InvalidProof('invalid_known_grades')
    if type(unknown) is not list or not all(_name(p) for p in unknown) or len(set(unknown))!=len(unknown):
        raise InvalidProof('invalid_unknowns')
    missing=set(unknown)
    if missing.intersection(known) or missing.union(known)!=set().union(*map(set,runs.values())):
        raise InvalidProof('invalid_grade_partition')
    if len(canonical_bytes(case))>RECORD_BYTES_CAP: raise InvalidProof('case_byte_budget')
    # Preserve positions. A passage appearing in both lists can contribute a
    # non-zero difference when the positions differ.
    ordered=tuple(tuple(runs[n]) for n in sorted(runs))
    return ordered,known,missing

def _metric(metric,scale):
    if type(metric) is not str or type(scale) is not int: raise InvalidProof('invalid_expected_metric')
    if metric==FLAT and scale==1:
        table=tuple((0,1,2,3) for _ in range(10))
    elif metric==DISCOUNTED and scale in (10_000,1_000_000,100_000_000):
        raw=Path(__file__).with_name('metric_tables.json').read_bytes()
        if sha256(raw).hexdigest()!=TABLE_FILE_SHA256: raise InvalidProof('uncertified_metric_table_registry')
        table=tuple(tuple(r) for r in json.loads(raw)[str(scale)])
    else: raise InvalidProof('unsupported_expected_metric')
    desc={'name':metric,'scale':scale,'rounding':'none' if metric==FLAT else 'floor_after_gain',
          'gains':[list(g) for g in WEIGHTS],'gain_table_sha256':_hash(table),
          'run_count':4,'depth':10,'top_k':3,'unknown_domain':[0,1,2,3],
          'tie_rule':'ascending lexical run identifier','rank_convention':'one_based_list_order'}
    return table,desc

def _pair_rows(ordered,known,table):
    rank_maps=tuple({p:r for r,p in enumerate(docs)} for docs in ordered)
    pairs={}
    for profile,gains in enumerate(WEIGHTS):
        for left,right in SCENARIOS:
            constant,terms=0,{}
            for passage in set(ordered[left]).union(ordered[right]):
                vector=[]
                for grade in range(4):
                    gain=gains[grade]
                    a=table[rank_maps[left][passage]][gain] if passage in rank_maps[left] else 0
                    b=table[rank_maps[right][passage]][gain] if passage in rank_maps[right] else 0
                    vector.append(a-b)
                if passage in known: constant+=vector[known[passage]]
                elif any(vector): terms[passage]=tuple(vector)
            pairs[profile,left,right]=(constant,int(left>right),terms)
    return pairs

def _scenario_rows(pairs,endpoint,a,b):
    if endpoint=='prefix': return (pairs[0,a,b],pairs[1,b,a])
    return (tuple(pairs[0,i,a] for i in range(4) if i!=a)
            +tuple(pairs[1,i,b] for i in range(4) if i!=b))

def _combine(rows,subset):
    constant,threshold,terms=0,0,{}
    for index in subset:
        fixed,rhs,values=rows[index]
        constant+=fixed
        threshold+=rhs
        for p,vector in values.items():
            current=terms.setdefault(p,[0,0,0,0])
            for d in range(4): current[d]+=vector[d]
    return constant,threshold,tuple((p,v,max(v)) for p,v in terms.items())

def _tree(node,rows,missing,assigned,cache,counts):
    counts.nodes+=1
    if counts.nodes>NODE_CAP: raise InvalidProof('proof_node_budget_exceeded')
    counts.max_depth=max(counts.max_depth,len(assigned))
    if type(node) is not dict: raise InvalidProof('node_not_object')
    if set(node)=={'subset'}:
        subset=node['subset']
        if (type(subset) is not list or not subset or len(subset)>len(rows)
            or not all(type(j) is int and 0<=j<len(rows) for j in subset)
            or any(a>=b for a,b in zip(subset,subset[1:]))):
            raise InvalidProof('invalid_leaf_subset')
        key=tuple(subset)
        if key not in cache: cache[key]=_combine(rows,subset)
        fixed,rhs,terms=cache[key]
        maximum=fixed+sum(v[assigned[p]] if p in assigned else cap for p,v,cap in terms)
        counts.leaves+=1
        counts.rows_in_leaves+=len(subset)
        if maximum>=rhs: raise InvalidProof('leaf_does_not_prove_infeasibility')
        return
    if set(node)!={'split','children'}: raise InvalidProof('invalid_tree_fields')
    p,children=node['split'],node['children']
    if not _name(p) or p not in missing or p in assigned: raise InvalidProof('invalid_split_passage')
    if type(children) is not list or len(children)!=4: raise InvalidProof('incomplete_grade_cover')
    if len(assigned)>=len(missing): raise InvalidProof('excessive_tree_depth')
    counts.splits+=1
    for d in range(4):
        assigned[p]=d
        _tree(children[d],rows,missing,assigned,cache,counts)
    del assigned[p]

def _witness(witness,ordered,known,missing,endpoint,table):
    if type(witness) is not dict or set(witness)!=missing or not all(_grade(g) for g in witness.values()):
        raise InvalidProof('invalid_witness_domain')
    labels=known|witness
    outputs=[]
    for gains in WEIGHTS:
        totals=[]
        for docs in ordered:
            totals.append(sum(table[r][gains[labels[p]]] for r,p in enumerate(docs)))
        prefix=tuple(sorted(range(4),key=lambda i:(-totals[i],i))[:3])
        outputs.append(set(prefix) if endpoint=='set' else prefix)
    if outputs[0]==outputs[1]: raise InvalidProof('witness_does_not_show_change')

def verify(case,endpoint,record,*,metric=DISCOUNTED,scale=1_000_000):
    counts=Counts()
    status=record.get('status') if type(record) is dict else None
    route='binding'
    try:
        if type(endpoint) is not str or endpoint not in ('set','prefix'): raise InvalidProof('invalid_expected_endpoint')
        ordered,known,missing=_prepare(case)
        table,desc=_metric(metric,scale)
        if type(record) is not dict: raise InvalidProof('record_not_object')
        record_bytes=len(canonical_bytes(record))
        if record_bytes>RECORD_BYTES_CAP: raise InvalidProof('record_byte_budget_exceeded')
        head={'schema':SCHEMA,'case_id':case['id'],'case_sha256':_hash(case),'endpoint':endpoint,'metric':desc}
        expected=head|{'request_sha256':_hash(head)}
        supplied={key:record.get(key) for key in HEADER_FIELDS}
        # Canonical comparison also rejects bool/int and int/float confusion.
        if canonical_bytes(supplied)!=canonical_bytes(expected): raise InvalidProof('request_binding_mismatch')
        if status=='changed':
            route='witness'
            if set(record)!=COMMON_FIELDS|{'witness'}: raise InvalidProof('invalid_changed_fields')
            _witness(record['witness'],ordered,known,missing,endpoint,table)
        elif status=='invariant':
            route='split_cover'
            if set(record)!=COMMON_FIELDS|{'trees'}: raise InvalidProof('invalid_invariant_fields')
            trees=record['trees']
            if type(trees) is not list or len(trees)!=12: raise InvalidProof('twelve_scenarios_required')
            pairs=_pair_rows(ordered,known,table)
            for tree,(a,b) in zip(trees,SCENARIOS):
                _tree(tree,_scenario_rows(pairs,endpoint,a,b),missing,{}, {},counts)
                counts.scenarios+=1
        elif status=='unresolved':
            route='abstention'
            if set(record)!=COMMON_FIELDS|{'reason'} or record['reason'] not in ('node_limit','record_byte_limit'):
                raise InvalidProof('invalid_unresolved_fields')
            return {'accepted':False,'state':'unresolved','status':status,'route':route,'reason':record['reason']}
        else: raise InvalidProof('unknown_status')
        return {'accepted':True,'state':'verified','status':status,'route':route,'record_bytes':record_bytes,**vars(counts)}
    except InvalidProof as exc:
        return {'accepted':False,'state':'rejected','status':status,'route':route,'reason':str(exc),**vars(counts)}
    except (ValueError,TypeError,UnicodeError,RecursionError,OSError):
        return {'accepted':False,'state':'rejected','status':None,'route':route,'reason':'malformed_input_or_registry',**vars(counts)}

def _read(path,limit):
    with path.open('rb') as stream: raw=stream.read(limit+1)
    if len(raw)>limit: raise InvalidProof('file_byte_budget_exceeded')
    return raw

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--cases-sha256',required=True)
    p.add_argument('--case-id',required=True)
    p.add_argument('--endpoint',choices=('set','prefix'),required=True)
    p.add_argument('--record',type=Path,required=True)
    p.add_argument('--metric',choices=(FLAT,DISCOUNTED),default=DISCOUNTED)
    p.add_argument('--scale',type=int,default=1_000_000)
    args=p.parse_args()
    try:
        raw=_read(args.cases,CASE_FILE_BYTES_CAP)
        if sha256(raw).hexdigest()!=args.cases_sha256: raise InvalidProof('trusted_case_file_digest_mismatch')
        cases=parse_json(raw,max_bytes=CASE_FILE_BYTES_CAP)
        if type(cases) is dict: cases=[cases]
        if type(cases) is not list or not all(type(c) is dict and _name(c.get('id')) for c in cases): raise InvalidProof('invalid_case_file')
        selected={c['id']:c for c in cases}
        if len(selected)!=len(cases) or args.case_id not in selected: raise InvalidProof('missing_or_duplicate_case_id')
        result=verify(selected[args.case_id],args.endpoint,parse_json(_read(args.record,RECORD_BYTES_CAP)),metric=args.metric,scale=args.scale)
    except (ValueError,OSError) as exc:
        result={'accepted':False,'state':'rejected','route':'input','reason':str(exc)}
    print(json.dumps(result,sort_keys=True,ensure_ascii=False,allow_nan=False))
    return 0 if result['accepted'] else 3 if result['state']=='unresolved' else 1

if __name__=='__main__': raise SystemExit(main())
