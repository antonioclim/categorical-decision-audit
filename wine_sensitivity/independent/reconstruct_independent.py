#!/usr/bin/env python3
"""Separate raw-CSV/SQLite reconstruction; no project aggregation/ranking imports."""
from pathlib import Path
import argparse
import csv
from decimal import Decimal
from functools import cmp_to_key
import hashlib
import json
from math import gcd
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
PLAN = ROOT / 'EXPLORATORY_PLAN.json'
EXPECTED_PLAN = '07e1114322f57be40c7f5da397dd4a6d54324ac072080b840c5d17265e9b7d11'
ARMS = {
 'A0_original': ('original_block', '1=1'),
 'A1_unique_original_blocks': ('original_block', 'first_content=1'),
 'A2_rows_content_blocks': ('content_block', '1=1'),
 'A3_unique_content_blocks': ('content_block', 'first_content=1'),
}

def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def fraction(num, den):
    if not den: return None
    d = gcd(num, den)
    a,b = num//d, den//d
    return str(a) if b == 1 else f'{a}/{b}'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'inputs',help='Directory containing the immutable raw CSVs and acquisition receipt')
    args = parser.parse_args()
    data = args.source.resolve()
    require(digest(PLAN.read_bytes()) == EXPECTED_PLAN, 'Validation failed: digest(PLAN.read_bytes()) == EXPECTED_PLAN')
    receipt = json.loads((data/'ACQUISITION_RECEIPT.json').read_text())
    source_hashes = {}
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE r (record_id TEXT, colour TEXT, content TEXT, original_block INTEGER, content_block INTEGER, first_content INTEGER, g TEXT, oldflag INTEGER, newflag INTEGER)')
    seen = set()
    for colour in ['red','white']:
        file = data/f'winequality-{colour}.csv'
        source_hashes[file.name] = digest(file.read_bytes())
        require(source_hashes[file.name] == receipt['files'][file.name]['sha256'], "Validation failed: source_hashes[file.name] == receipt['files'][file.name]['sha256']")
        with file.open(newline='',encoding='utf-8') as f:
            for index,row in enumerate(csv.DictReader(f,delimiter=';'),1):
                payload = json.dumps({'colour':colour,'row':row},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
                identity = digest(payload)
                first = int(identity not in seen)
                seen.add(identity)
                original = int.from_bytes(hashlib.sha256(f'PaperM-R2-Wine-transfer-v1\0{colour}\0{index}'.encode()).digest(),'big') % 18
                content_block = int.from_bytes(hashlib.sha256(b'PaperM-M13-Wine-content-block-v1\0'+payload).digest(),'big') % 18
                alcohol,ph,quality = Decimal(row['alcohol']),Decimal(row['pH']),int(row['quality'])
                band = 0 if alcohol < Decimal('10') else 1 if alcohol < Decimal('11') else 2
                phband = int(ph >= Decimal('3.2'))
                group = f'G{band*2+phband+1:02d}'
                connection.execute('INSERT INTO r VALUES (?,?,?,?,?,?,?,?,?)',(f'{colour}:{index}',colour,identity,original,content_block,first,group,int(quality>=6),int(quality>=7)))
    result = {'plan_sha256':EXPECTED_PLAN,'method':'Independent raw-CSV parse, Decimal group cutpoints, SQLite COUNT/SUM, exact integer cross-products for ordering; no production sensitivity imports','source_sha256':source_hashes,'arms':{}}
    for arm,(column,where) in ARMS.items():
        aggregate = connection.execute(f'SELECT {column},g,COUNT(*),SUM(oldflag),SUM(newflag) FROM r WHERE {where} GROUP BY {column},g').fetchall()
        table = {(b,g):(n,old,new) for b,g,n,old,new in aggregate}
        blocks,candidates = {},[]
        for block in range(18):
            groups = {f'G{j:02d}':table.get((block,f'G{j:02d}'),(0,0,0)) for j in range(1,7)}
            nonempty = [g for g in groups if groups[g][0]]
            rankings = {}
            for side,num_index in [('old',1),('new',2)]:
                def compare(g,h):
                    lhs = groups[g][num_index]*groups[h][0]
                    rhs = groups[h][num_index]*groups[g][0]
                    return -1 if lhs > rhs else 1 if lhs < rhs else -1 if g<h else 1 if g>h else 0
                rankings[side] = sorted(nonempty,key=cmp_to_key(compare))
            block_scores = {g:{'n':n,'old_numerator':old,'new_numerator':new,'old':fraction(old,n),'new':fraction(new,n)} for g,(n,old,new) in groups.items()}
            blocks[str(block)] = {'nrows':sum(v[0] for v in groups.values()),'groups':block_scores,'rankings':rankings}
            for k in [2,3]:
                candidate = {'block':block,'k':k,'eligible':len(nonempty)>=k+1}
                if not candidate['eligible']:
                    candidate.update(reason='Fewer than k+1 nonempty groups.',change_type=None,strict_no_selected_or_boundary_ties=False)
                    candidates.append(candidate)
                    continue
                orders = {side:rankings[side][:k] for side in ['old','new']}
                old,new = orders['old'],orders['new']
                kind = 'same_order' if old==new else 'order_only' if set(old)==set(new) else 'membership_change'
                selected,boundary = {},{}
                for side,num_index in [('old',1),('new',2)]:
                    top = rankings[side]
                    def equal(g,h): return groups[g][num_index]*groups[h][0] == groups[h][num_index]*groups[g][0]
                    selected[side] = any(equal(top[i],top[j]) for i in range(k) for j in range(i+1,k))
                    boundary[side] = equal(top[k-1],top[k])
                candidate.update(change_type=kind,old_order=old,new_order=new,selected_score_ties=selected,boundary_ties=boundary,strict_no_selected_or_boundary_ties=kind=='order_only' and not any(selected.values()) and not any(boundary.values()))
                candidates.append(candidate)
        nrows = connection.execute(f'SELECT COUNT(*) FROM r WHERE {where}').fetchone()[0]
        unique = connection.execute(f'SELECT COUNT(DISTINCT content) FROM r WHERE {where}').fetchone()[0]
        cross = connection.execute(f'SELECT COUNT(*) FROM (SELECT content FROM r WHERE {where} GROUP BY content HAVING COUNT(DISTINCT {column})>1)').fetchone()[0]
        strict = [c for c in candidates if c['strict_no_selected_or_boundary_ties']]
        summary = {'nrows':nrows,'unique_contents':unique,'candidate_count':len(candidates),'eligible':sum(c['eligible'] for c in candidates),'same_order':sum(c['change_type']=='same_order' for c in candidates),'membership_change':sum(c['change_type']=='membership_change' for c in candidates),'order_only':sum(c['change_type']=='order_only' for c in candidates),'strict_no_selected_or_boundary_ties':len(strict),'strict_blocks_1based':sorted({c['block']+1 for c in strict}),'strict_cases':[f'W{c["block"]+1:02d}-K{c["k"]}' for c in strict],'duplicate_groups_crossing_blocks':cross}
        result['arms'][arm] = {'summary':summary,'blocks':blocks,'candidates':candidates}
    require(all(digest((data/name).read_bytes())==value for name,value in source_hashes.items()), 'Validation failed: all(digest((data/name).read_bytes())==value for name,value in source_hashes.items())')
    result['source_unchanged_after_execution'] = True
    result['python'] = sys.version
    output = OUT/'INDEPENDENT_RESULTS.json'
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    (OUT/'INDEPENDENT_RESULTS.sha256').write_text(digest(output.read_bytes())+'  '+output.name+'\n')
    print(json.dumps({arm:v['summary'] for arm,v in result['arms'].items()},indent=2))

if __name__=='__main__': main()
