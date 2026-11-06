#!/usr/bin/env python3
"""Independent raw-CSV/SQLite/integer recheck of all retained Wine dossiers.

This verifier imports no builder, Fraction scorer or retained decision kernel.
It is a separate internal implementation, not external scientific replication.
"""
from __future__ import annotations

import copy
import csv
from decimal import Decimal
import functools
import hashlib
import json
import math
from itertools import combinations
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'transfer'
STATES = ['quality_le_5', 'quality_eq_6', 'quality_ge_7']
EXPECTED_PROTOCOL = '799e007b5f945c9ff33117e2c548ad59c65fbfcd8f3c24d4a22d91b177bb5435'
RAW_ZIP_SHA = '3ed56667f4b828242bd732d7d1dd7f2861e54432239d7fa63877014cbb0304d4'
RAW_SHA = {'winequality-red.csv': '4a402cf041b025d4566d954c3b9ba8635a3a8a01e039005d97d6a710278cf05e',
           'winequality-white.csv': '76c3f809815c17c07212622f776311faeb31e87610d52c26d87d6e361b169836'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rat(n, d):
    common = math.gcd(n, d)
    n, d = n//common, d//common
    return str(n) if d == 1 else f'{n}/{d}'


def database():
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE source (record_id TEXT PRIMARY KEY, block INTEGER, gid TEXT, quality INTEGER, raw_signature TEXT)')
    raw_count = 0
    for colour in ['red', 'white']:
        path = DATA / f'winequality-{colour}.csv'
        require(hashlib.sha256(path.read_bytes()).hexdigest() == RAW_SHA[path.name], 'Raw source changed.')
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream, delimiter=';')
            for index, row in enumerate(reader, 1):
                alcohol, ph = Decimal(row['alcohol']), Decimal(row['pH'])
                a = int(alcohol >= Decimal('10')) + int(alcohol >= Decimal('11'))
                b = int(ph >= Decimal('3.2'))
                gid = f'G{2*a+b+1:02d}'
                q = int(row['quality'])
                require(0 <= q <= 10, 'Unexpected quality value.')
                token = 'PaperM-R2-Wine-transfer-v1\0' + colour + '\0' + str(index)
                block = int(hashlib.sha256(token.encode()).hexdigest(), 16) % 18
                signature = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                db.execute('INSERT INTO source VALUES (?,?,?,?,?)', (f'{colour}:{index}', block, gid, q, signature))
                raw_count += 1
    db.commit()
    return db, raw_count


def verify(public, key, candidates, partition_map, summary):
    require(hashlib.sha256((DATA/'PREACQUISITION_PROTOCOL.json').read_bytes()).hexdigest() == EXPECTED_PROTOCOL, 'Protocol changed.')
    require(hashlib.sha256((DATA/'wine_quality_uci.zip').read_bytes()).hexdigest() == RAW_ZIP_SHA, 'Raw ZIP changed.')
    require(public['schema_version'] == 'PaperM-R2-transfer-casebank-v1', 'Wrong public schema.')
    require(public['status'] == 'preacquisition_specified_transfer_computation_not_human_study', 'Scope marker changed.')
    require(set(public['targets']) == {'CAPACITY','MEMBERSHIP','PRIORITY'}, 'Targets changed.')
    db, raw_count = database()
    cases = {c['case_id']:c for c in public['cases']}
    keys = {c['case_id']:c for c in key['cases']}
    candidate_lookup = {c['case_id']:c for c in candidates}
    expected_ids = {f'R2-W{b+1:02d}-K{k}' for b in range(18) for k in [2,3]}
    require(set(cases)==set(keys)==expected_ids, 'Missing, duplicated or extra candidate retained.')
    require(len(public['cases'])==len(key['cases'])==36, 'Duplicate case IDs.')
    require({c['case_id'] for c in candidates} == expected_ids and len(candidates)==36, 'Candidate coverage changed.')
    require(all(c['eligible'] for c in candidates), 'Unexpected retrospective exclusion.')
    part = {r['record_id']:r for r in partition_map['records']}
    require(len(part)==len(partition_map['records'])==raw_count, 'Partition-map duplicates/missing rows.')
    for record_id, block, gid, quality, signature in db.execute('SELECT * FROM source'):
        r = part[record_id]
        expected_state = STATES[0 if quality<=5 else 1 if quality==6 else 2]
        require((r['block'],r['group_id'],r['state']) == (block,gid,expected_state), 'Record partition/group/state mismatch.')
        require(r['row_content_sha256'] == hashlib.sha256(signature.encode()).hexdigest(), 'Record content binding changed.')
    classes, strict_ids, no_boundary_ids, checked_scores = {}, [], [], 0
    for cid in sorted(cases):
        c, key_c = cases[cid], keys[cid]
        require(not (set(c) & {'change_type','correct_answer','truth','verdict','strict_order_only'}), 'Private answer leaked into public dossier.')
        block = int(cid.split('-')[1][1:])-1
        k = int(cid.split('-')[2][1:])
        require(c['rule']=={'kind':'top_k','k':k,'direction':'highest_first','tie_break':'ascending fixed group ID (alcohol band then pH band)'}, 'Rule changed.')
        require(c['scope']=='current supplied allocation only', 'Scope inflated.')
        require(c['context']=={'attribute':'record_partition','value':f'B{block+1:02d}','grouped_attributes':['alcohol_band','pH_band']},'Displayed partition/grouping context changed.')
        require(c['states']==STATES, 'State mapping changed.')
        require(c['source_ref']=='https://doi.org/10.24432/C56S3T', 'Source reference changed.')
        require(c['source_sha256']==RAW_ZIP_SHA,'Displayed source binding changed.')
        require(c['source_kind']=='observed physicochemical wine measurements and sensory quality labels','Displayed source kind changed.')
        require(c['source_case_id']==f'WineQuality-partition-{block+1:02d}-k{k}','Archival source case binding changed.')
        require(key_c['block']==block,'Private block binding changed.')
        require(c['profiles']=={'old_label':'quality_at_least_6','new_label':'quality_at_least_7',
                               'old_weights':dict(zip(STATES,['0','1','1'])),
                               'new_weights':dict(zip(STATES,['0','0','1']))}, 'Coding changed.')
        require([e['id'] for e in c['evidence']]==['E1','E2','E3','E4','E5'], 'Evidence identities changed.')
        rows = db.execute('SELECT gid, COUNT(*), SUM(quality>=6), SUM(quality>=7), SUM(quality<=5), SUM(quality=6) FROM source WHERE block=? GROUP BY gid', [block]).fetchall()
        lookup = {r[0]:r[1:] for r in rows}
        require([g['id'] for g in c['groups']] == sorted(lookup), 'Group set/order changed.')
        scores = {'old':{},'new':{}}
        for g in c['groups']:
            index = int(g['id'][1:])-1
            alcohol_label = ['alcohol<10','10<=alcohol<11','alcohol>=11'][index//2]
            ph_label = ['pH<3.2','pH>=3.2'][index%2]
            require(g['label']==alcohol_label+'|'+ph_label,'Displayed group meaning changed.')
            total, old, new, low, middle = lookup[g['id']]
            require(g['count_total']==total, 'Group denominator changed.')
            require(g['counts']==dict(zip(STATES,[low,middle,new])), 'Grouped source count changed.')
            for side, numerator in [('old',old),('new',new)]:
                require(g[side+'_score']==rat(numerator,total), 'Exact score changed.')
                scores[side][g['id']] = (numerator,total)
                checked_scores += 1
        def order(side):
            def compare(a,b):
                an,ad = scores[side][a];bn,bd = scores[side][b]
                delta = an*bd-bn*ad
                return (-1 if delta>0 else 1) if delta else (a>b)-(a<b)
            return sorted(lookup,key=functools.cmp_to_key(compare))
        full = {side:order(side) for side in ['old','new']}
        selected = {side:full[side][:k] for side in ['old','new']}
        require(c['old_order']==selected['old'] and c['new_order']==selected['new'], 'Selected sequence changed.')
        old,new = selected['old'],selected['new']
        kind = 'same_order' if old==new else 'order_only' if set(old)==set(new) else 'membership_change'
        classes[kind] = classes.get(kind,0)+1
        require(key_c['change_type']==kind, 'Private type changed.')
        require(key_c['targets']=={'CAPACITY':'APPROVE','MEMBERSHIP':'APPROVE' if set(old)==set(new) else 'REJECT','PRIORITY':'APPROVE' if old==new else 'REJECT'}, 'Private target answer changed.')
        def equal(side,a,b):
            an,ad=scores[side][a];bn,bd=scores[side][b]
            return an*bd==bn*ad
        tied={side:any(equal(side,full[side][i],full[side][j]) for i in range(k) for j in range(i)) for side in ['old','new']}
        boundary={side:equal(side,full[side][k-1],full[side][k]) for side in ['old','new']}
        strict=kind=='order_only' and not any(tied.values())
        require(key_c['selected_score_ties']==tied and key_c['boundary_ties']==boundary and key_c['strict_order_only']==strict,'Tie/strict classification changed.')
        reversals=[]
        for a,b in combinations(sorted(set(old)&set(new)),2):
            an,ad=scores['old'][a];bn,bd=scores['old'][b]
            xn,xd=scores['new'][a];yn,yd=scores['new'][b]
            if (an*bd-bn*ad)*(xn*yd-yn*xd)<0:
                reversals.append([a,b])
        require(key_c['strict_pair_reversals_within_common_selected_groups']==reversals,'Strict-pair reversal list changed.')
        require(candidate_lookup[cid]=={'case_id':cid,'block':block,'k':k,'eligible':True,'change_type':kind,
                                       'strict_order_only':strict,'selected_score_ties':tied,'boundary_ties':boundary},'Candidate ledger metadata changed.')
        if strict:strict_ids.append(cid)
        if strict and not any(boundary.values()):no_boundary_ids.append(cid)
        expected_records=[r[0] for r in db.execute('SELECT record_id FROM source WHERE block=? ORDER BY rowid',[block])]
        require(key_c['source_record_ids']==expected_records,'Case record provenance changed.')
    duplicates = db.execute('SELECT raw_signature, COUNT(*),COUNT(DISTINCT block) FROM source GROUP BY raw_signature HAVING COUNT(*)>1').fetchall()
    across=[r for r in duplicates if r[2]>1]
    require(summary['raw_rows']==raw_count and summary['change_counts']==classes,'Summary count changed.')
    require(summary['candidate_cases']==summary['retained_cases']==36 and summary['excluded_cases']==[],'Candidate summary changed.')
    expected_blocks={kind:sorted({k['block']+1 for k in keys.values() if k['change_type']==kind}) for kind in ['same_order','order_only','membership_change']}
    require(summary['distinct_blocks_by_change_type']==expected_blocks,'Distinct-block counts changed.')
    require(summary['strict_order_only_distinct_blocks']==sorted({keys[c]['block']+1 for c in strict_ids}),'Strict distinct-block count changed.')
    require(summary['duplicate_content_groups']==len(duplicates) and summary['duplicate_content_groups_crossing_blocks']==len(across),'Duplicate audit changed.')
    require(summary['rows_in_cross_block_duplicate_content_groups']==sum(r[1] for r in across),'Cross-block duplicate record count changed.')
    require(summary['strict_order_only_count']==len(strict_ids) and summary['strict_order_only_without_boundary_ties_count']==len(no_boundary_ids),'Strict yield summary changed.')
    db.close()
    return {'status':'PASS','raw_records':raw_count,'cases':36,'target_answers':108,'exact_group_scores':checked_scores,
            'change_counts':classes,'strict_order_only_case_ids':strict_ids,
            'strict_order_only_without_boundary_ties_case_ids':no_boundary_ids,
            'duplicate_content_groups':len(duplicates),'duplicate_content_groups_crossing_blocks':len(across),
            'rows_in_cross_block_duplicate_content_groups':sum(r[1] for r in across),
            'method':'Raw CSV -> Decimal category boundaries -> SQLite grouped threshold counts -> integer cross-multiplication ranks -> private-answer reconciliation',
            'scope':'Separate internal implementation; not external replication, human evidence or organisational utility.'}


def main():
    public=json.loads((DATA/'public_transfer_cases.json').read_text())
    key=json.loads((DATA/'private_transfer_key.json').read_text())
    candidates=json.loads((DATA/'ALL_CANDIDATES.json').read_text())
    part=json.loads((DATA/'RECORD_PARTITION_MAP.json').read_text())
    summary=json.loads((DATA/'TRANSFER_SUMMARY.json').read_text())
    report=verify(public,key,candidates,part,summary)
    tests=[]
    mutations=[('score',lambda p,k,c,mp,s:p['cases'][0]['groups'][0].__setitem__('old_score','999')),
               ('count',lambda p,k,c,mp,s:p['cases'][0]['groups'][0]['counts'].__setitem__('quality_le_5',999)),
               ('rule',lambda p,k,c,mp,s:p['cases'][0]['rule'].__setitem__('k',1)),
               ('group label',lambda p,k,c,mp,s:p['cases'][0]['groups'][0].__setitem__('label','alcohol>=100')),
               ('context label',lambda p,k,c,mp,s:p['cases'][0]['context'].__setitem__('value','B99')),
               ('source binding',lambda p,k,c,mp,s:p['cases'][0].__setitem__('source_sha256','0'*64)),
               ('candidate block',lambda p,k,c,mp,s:c[0].__setitem__('block',99)),
               ('private block',lambda p,k,c,mp,s:k['cases'][0].__setitem__('block',99)),
               ('strict pair list',lambda p,k,c,mp,s:k['cases'][0].__setitem__('strict_pair_reversals_within_common_selected_groups',[['G98','G99']])),
               ('profile',lambda p,k,c,mp,s:p['cases'][0]['profiles']['new_weights'].__setitem__('quality_eq_6','1')),
               ('private answer',lambda p,k,c,mp,s:k['cases'][0]['targets'].__setitem__('CAPACITY','REJECT')),
               ('partition',lambda p,k,c,mp,s:mp['records'][0].__setitem__('block',99)),
               ('candidate exclusion',lambda p,k,c,mp,s:c.pop()),
               ('public answer leakage',lambda p,k,c,mp,s:p['cases'][0].__setitem__('correct_answer','APPROVE')),
               ('strict yield',lambda p,k,c,mp,s:s.__setitem__('strict_order_only_count',99)),
               ('duplicate dependence',lambda p,k,c,mp,s:s.__setitem__('duplicate_content_groups_crossing_blocks',0))]
    for name,mutate in mutations:
        args=copy.deepcopy([public,key,candidates,part,summary]);mutate(*args)
        try:verify(*args)
        except (ValueError,KeyError,TypeError):tests.append({'mutation':name,'detected':True})
        else:raise RuntimeError('Undetected mutation: '+name)
    report['mutations']=tests
    report['protocol_sha256']=EXPECTED_PROTOCOL
    (DATA/'INDEPENDENT_TRANSFER_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
