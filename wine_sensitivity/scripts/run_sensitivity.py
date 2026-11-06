#!/usr/bin/env python3
"""Post-outcome Wine duplicate/partition sensitivity; read-only source inputs."""
from pathlib import Path
from collections import Counter, defaultdict
from fractions import Fraction
from datetime import datetime, timezone
import csv
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'inputs'
EXPECTED_PLAN = '07e1114322f57be40c7f5da397dd4a6d54324ac072080b840c5d17265e9b7d11'
ARM_IDS = ['A0_original', 'A1_unique_original_blocks', 'A2_rows_content_blocks', 'A3_unique_content_blocks']
GROUPS = [f'G{i:02d}' for i in range(1, 7)]
STATES = ['quality_le_5', 'quality_eq_6', 'quality_ge_7']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(name, obj):
    (ROOT/name).write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)+'\n', encoding='utf-8', newline='\n')


def load_records():
    receipt = json.loads((SOURCE/'ACQUISITION_RECEIPT.json').read_text())
    records, hashes = [], {}
    for colour in ['red', 'white']:
        file = SOURCE/f'winequality-{colour}.csv'
        hashes[file.name] = sha(file.read_bytes())
        require(hashes[file.name] == receipt['files'][file.name]['sha256'], "Validation failed: hashes[file.name] == receipt['files'][file.name]['sha256']")
        with file.open(newline='', encoding='utf-8') as stream:
            for index, row in enumerate(csv.DictReader(stream, delimiter=';'), 1):
                payload = json.dumps({'colour':colour, 'row':row}, ensure_ascii=False,
                                     sort_keys=True, separators=(',',':')).encode()
                content_sha = sha(payload)
                original_token = f'PaperM-R2-Wine-transfer-v1\0{colour}\0{index}'.encode()
                content_token = b'PaperM-M13-Wine-content-block-v1\0'+payload
                alcohol, ph = Fraction(row['alcohol']), Fraction(row['pH'])
                alcohol_band = 0 if alcohol < 10 else 1 if alcohol < 11 else 2
                ph_band = 0 if ph < Fraction(16, 5) else 1
                quality = int(row['quality'])
                require(0 <= quality <= 10, 'Validation failed: 0 <= quality <= 10')
                records.append({'record_id':f'{colour}:{index}', 'colour':colour,
                                'original_row':index, 'content_sha256':content_sha,
                                'original_block':int.from_bytes(hashlib.sha256(original_token).digest(),'big')%18,
                                'content_block':int.from_bytes(hashlib.sha256(content_token).digest(),'big')%18,
                                'group':f'G{2*alcohol_band+ph_band+1:02d}',
                                'state':STATES[0 if quality<=5 else 1 if quality==6 else 2]})
    return records, hashes


def calculate_arm(arm_id, records, partition):
    blocks = {i:[] for i in range(18)}
    for record in records: blocks[record[partition]].append(record)
    duplicate_groups = defaultdict(list)
    for record in records: duplicate_groups[record['content_sha256']].append(record)
    candidates, block_details = [], []
    for block in range(18):
        counts = {group:Counter({s:0 for s in STATES}) for group in GROUPS}
        for record in blocks[block]: counts[record['group']][record['state']] += 1
        nonempty = [g for g in GROUPS if sum(counts[g].values())]
        scores = {side:{} for side in ['old','new']}
        for group in nonempty:
            denominator = sum(counts[group].values())
            scores['old'][group] = Fraction(counts[group]['quality_eq_6']+counts[group]['quality_ge_7'],denominator)
            scores['new'][group] = Fraction(counts[group]['quality_ge_7'],denominator)
        ranks = {side:sorted(nonempty,key=lambda g:(-scores[side][g],g)) for side in ['old','new']}
        group_rows = [{'id':group,'counts':dict(counts[group]),'count_total':sum(counts[group].values()),
                       'old_score':str(scores['old'][group]),'new_score':str(scores['new'][group])}
                      for group in nonempty]
        block_details.append({'block':block,'rows':len(blocks[block]),'groups':group_rows,
                              'old_rank':ranks['old'],'new_rank':ranks['new'],
                              'source_record_ids':[r['record_id'] for r in blocks[block]]})
        for k in [2,3]:
            cid = f'{arm_id}-W{block+1:02d}-K{k}'
            item = {'case_id':cid,'arm':arm_id,'block':block,'k':k,'nrows':len(blocks[block]),
                    'nonempty_groups':len(nonempty),'eligible':len(nonempty)>=k+1}
            if not item['eligible']:
                item['reason']='Fewer than k+1 nonempty groups.'
                candidates.append(item)
                continue
            old, new = ranks['old'][:k], ranks['new'][:k]
            kind = 'same_order' if old==new else 'order_only' if set(old)==set(new) else 'membership_change'
            selected_ties = {side:len({scores[side][g] for g in ranks[side][:k]})<k for side in ['old','new']}
            boundary_ties = {side:scores[side][ranks[side][k-1]]==scores[side][ranks[side][k]] for side in ['old','new']}
            item.update({'change_type':kind,'old_order':old,'new_order':new,
                         'membership_removed':sorted(set(old)-set(new)),
                         'membership_added':sorted(set(new)-set(old)),
                         'selected_score_ties':selected_ties,'boundary_ties':boundary_ties,
                         'strict_order_only':kind=='order_only' and not any(selected_ties.values()),
                         'strict_order_only_no_boundary_ties':kind=='order_only' and not any(selected_ties.values()) and not any(boundary_ties.values())})
            candidates.append(item)
    counter = Counter(c['change_type'] for c in candidates if c['eligible'])
    strict = [c for c in candidates if c.get('strict_order_only_no_boundary_ties')]
    cross = [v for v in duplicate_groups.values() if len({r[partition] for r in v})>1]
    summary = {'arm':arm_id,'source_rows':len(records),'unique_contents':len(duplicate_groups),
               'candidate_count':36,'eligible_count':sum(c['eligible'] for c in candidates),
               'ineligible_count':sum(not c['eligible'] for c in candidates),
               'same_order':counter['same_order'],'membership_change':counter['membership_change'],
               'order_only':counter['order_only'],
               'strict_order_only_no_boundary_ties':len(strict),
               'strict_distinct_blocks':sorted({c['block']+1 for c in strict}),
               'strict_case_ids':[c['case_id'] for c in strict],
               'duplicate_content_groups':sum(len(v)>1 for v in duplicate_groups.values()),
               'duplicate_content_groups_crossing_blocks':len(cross),
               'rows_in_cross_block_duplicates':sum(len(v) for v in cross)}
    return {'summary':summary,'candidates':candidates,'blocks':block_details}


def baseline_validation(baseline):
    original = json.loads((SOURCE/'ALL_CANDIDATES.json').read_text())
    checked = 0
    for old,new in zip(original,baseline['candidates'],strict=True):
        for field in ['block','k','eligible','change_type','selected_score_ties','boundary_ties','strict_order_only']:
            require(old.get(field)==new.get(field), (field,old,new))
        checked += 1
    public = json.loads((SOURCE/'public_transfer_cases.json').read_text())['cases']
    by_block = {b['block']:b for b in baseline['blocks']}
    for case in public:
        block = int(case['case_id'].split('-W')[1][:2])-1
        old_groups = {g['id']:{k:g[k] for k in ['id','counts','count_total','old_score','new_score']} for g in case['groups']}
        require(old_groups == {g['id']:g for g in by_block[block]['groups']}, "Validation failed: old_groups == {g['id']:g for g in by_block[block]['groups']}")
    return {'original_candidate_matches':checked,'original_case_group_payloads_match':len(public)}


def main():
    global SOURCE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=SOURCE,help='Directory with raw CSVs and retained acquisition/baseline JSONs')
    SOURCE=parser.parse_args().source
    plan = ROOT/'EXPLORATORY_PLAN.json'
    require(sha(plan.read_bytes()) == EXPECTED_PLAN, 'Validation failed: sha(plan.read_bytes()) == EXPECTED_PLAN')
    records, hashes_before = load_records()
    unique = list({r['content_sha256']:r for r in reversed(records)}.values())
    unique.sort(key=lambda r:(['red','white'].index(r['colour']),r['original_row']))
    arms = [calculate_arm(ARM_IDS[0],records,'original_block'),
            calculate_arm(ARM_IDS[1],unique,'original_block'),
            calculate_arm(ARM_IDS[2],records,'content_block'),
            calculate_arm(ARM_IDS[3],unique,'content_block')]
    validation = baseline_validation(arms[0])
    original_strict = [(c['block'],c['k']) for c in arms[0]['candidates'] if c.get('strict_order_only_no_boundary_ties')]
    correspondence = []
    for block,k in original_strict:
        a0 = next(c for c in arms[0]['candidates'] if (c['block'],c['k'])==(block,k))
        a1 = next(c for c in arms[1]['candidates'] if (c['block'],c['k'])==(block,k))
        correspondence.append({'baseline_case':a0['case_id'].replace(ARM_IDS[0],'R2'),
                               'A1_case':a1['case_id'],'baseline_old_order':a0['old_order'],
                               'baseline_new_order':a0['new_order'],'A1_old_order':a1.get('old_order'),
                               'A1_new_order':a1.get('new_order'),'A1_change_type':a1.get('change_type'),
                               'A1_strict_order_only_no_boundary_ties':a1.get('strict_order_only_no_boundary_ties')})
    hashes_after = {name:sha((SOURCE/name).read_bytes()) for name in hashes_before}
    require(hashes_before == hashes_after, 'Validation failed: hashes_before == hashes_after')
    output = {'status':'POST_OUTCOME_EXPLORATORY_SENSITIVITY','plan_sha256':EXPECTED_PLAN,
              'source_sha256':hashes_before,'raw_inputs_unchanged':True,
              'baseline_validation':validation,'arms':arms,'baseline_to_A1_strict_cases':correspondence}
    write_json('SENSITIVITY_RESULTS.json',output)
    write_json('SUMMARY.json',{'summaries':[a['summary'] for a in arms],
                              'baseline_to_A1_strict_cases':correspondence})
    write_json('RECORD_ASSIGNMENTS.json',{'records':records,'retained_first_occurrences':[r['record_id'] for r in unique]})
    with (ROOT/'CANDIDATE_LEDGER.csv').open('w',newline='') as stream:
        fields=['case_id','arm','block','k','nrows','nonempty_groups','eligible','change_type','old_order','new_order','strict_order_only_no_boundary_ties','selected_score_ties','boundary_ties','reason']
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for arm in arms:
            for case in arm['candidates']:
                writer.writerow({key:json.dumps(value,sort_keys=True) if isinstance(value,(list,dict)) else value for key,value in case.items()})
    with (ROOT/'GROUP_SCORE_LEDGER.csv').open('w',newline='') as stream:
        fields=['arm','block','group','count_total',*STATES,'old_score','new_score']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for arm in arms:
            for block in arm['blocks']:
                for group in block['groups']:
                    writer.writerow({'arm':arm['summary']['arm'],'block':block['block'],'group':group['id'],'count_total':group['count_total'],**group['counts'],'old_score':group['old_score'],'new_score':group['new_score']})
    write_json('EXECUTION_RECEIPT.json',{'completed_utc':datetime.now(timezone.utc).isoformat(),
                                      'plan_sha256':EXPECTED_PLAN,'script_sha256':sha(Path(__file__).read_bytes()),
                                      'source_hashes_before':hashes_before,'source_hashes_after':hashes_after,
                                      'result_sha256':sha((ROOT/'SENSITIVITY_RESULTS.json').read_bytes()),
                                      'baseline_validation':validation,'candidate_records':sum(len(a['candidates']) for a in arms)})
    print(json.dumps({'summaries':[a['summary'] for a in arms],'baseline_to_A1':correspondence},indent=2))


if __name__ == '__main__': main()
