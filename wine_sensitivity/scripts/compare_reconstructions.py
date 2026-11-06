#!/usr/bin/env python3
"""Compare production and separately implemented Wine reconstructions."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'inputs')
    source=parser.parse_args().source
    prod_path=ROOT/'SENSITIVITY_RESULTS.json'
    independent_path=ROOT/'independent/INDEPENDENT_RESULTS.json'
    production=json.loads(prod_path.read_text())
    independent=json.loads(independent_path.read_text())
    require(production['plan_sha256']==independent['plan_sha256'], "Validation failed: production['plan_sha256']==independent['plan_sha256']")
    require(production['source_sha256']==independent['source_sha256'], "Validation failed: production['source_sha256']==independent['source_sha256']")
    expected_arms = ['A0_original', 'A1_unique_original_blocks', 'A2_rows_content_blocks', 'A3_unique_content_blocks']
    require([arm['summary']['arm'] for arm in production['arms']] == expected_arms, 'Production arm membership/order differs')
    require(set(independent['arms']) == set(expected_arms), 'Separate reconstruction arm membership differs')
    candidate_checks=group_checks=block_checks=0
    for arm in production['arms']:
        name=arm['summary']['arm']; other=independent['arms'][name]
        summary=arm['summary']; ref=other['summary']
        expected_candidates = [(block, k) for block in range(18) for k in (2, 3)]
        require([(c['block'], c['k']) for c in arm['candidates']] == expected_candidates, (name, 'candidate membership/order'))
        require([(c['block'], c['k']) for c in other['candidates']] == expected_candidates, (name, 'separate candidate membership/order'))
        require([b['block'] for b in arm['blocks']] == list(range(18)), (name, 'block membership/order'))
        require(set(other['blocks']) == {str(b) for b in range(18)}, (name, 'separate block membership'))
        for first,second in [('source_rows','nrows'),('unique_contents','unique_contents'),
                             ('same_order','same_order'),('membership_change','membership_change'),
                             ('order_only','order_only'),('strict_order_only_no_boundary_ties','strict_no_selected_or_boundary_ties'),
                             ('duplicate_content_groups_crossing_blocks','duplicate_groups_crossing_blocks')]:
            require(summary[first]==ref[second], (name,first))
        for actual,expected in zip(arm['candidates'],other['candidates'],strict=True):
            for field in ['block','k','eligible','change_type','old_order','new_order','selected_score_ties','boundary_ties']:
                require(actual.get(field)==expected.get(field), (name,field,actual,expected))
            require(actual.get('strict_order_only_no_boundary_ties')==expected.get('strict_no_selected_or_boundary_ties'), "Validation failed: actual.get('strict_order_only_no_boundary_ties')==expected.get('strict_no_selected_or_boundary_ties')")
            candidate_checks+=1
        for block in arm['blocks']:
            refblock=other['blocks'][str(block['block'])]
            expected_groups = {f'G{i:02d}' for i in range(1, 7)}
            require(len(block['groups']) == 6 and {g['id'] for g in block['groups']} == expected_groups, (name, block['block'], 'group membership'))
            require(set(refblock['groups']) == expected_groups, (name, block['block'], 'separate group membership'))
            require(block['rows']==refblock['nrows'], "Validation failed: block['rows']==refblock['nrows']")
            require(block['old_rank']==refblock['rankings']['old'], "Validation failed: block['old_rank']==refblock['rankings']['old']")
            require(block['new_rank']==refblock['rankings']['new'], "Validation failed: block['new_rank']==refblock['rankings']['new']")
            block_checks+=1
            for group in block['groups']:
                refgroup=refblock['groups'][group['id']]
                require(group['count_total']==refgroup['n'], "Validation failed: group['count_total']==refgroup['n']")
                require(group['old_score']==refgroup['old'] and group['new_score']==refgroup['new'], "Validation failed: group['old_score']==refgroup['old'] and group['new_score']==refgroup['new']")
                reconstructed={'quality_ge_7':refgroup['new_numerator'],
                               'quality_eq_6':refgroup['old_numerator']-refgroup['new_numerator'],
                               'quality_le_5':refgroup['n']-refgroup['old_numerator']}
                require(group['counts']==reconstructed, "Validation failed: group['counts']==reconstructed")
                group_checks+=1
    require((candidate_checks, block_checks, group_checks) == (144, 72, 432), 'Comparison scope differs from the specified bank')
    old_identity=defaultdict(list)
    colour_identity=defaultdict(list)
    for colour in ['red','white']:
        with (source/f'winequality-{colour}.csv').open(newline='') as stream:
            for index,row in enumerate(csv.DictReader(stream,delimiter=';'),1):
                payload=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
                key=hashlib.sha256(payload).hexdigest()
                block=int.from_bytes(hashlib.sha256(f'PaperM-R2-Wine-transfer-v1\0{colour}\0{index}'.encode()).digest(),'big')%18
                record={'record_id':f'{colour}:{index}','colour':colour,'block':block}
                old_identity[key].append(record)
                colour_identity[(colour,key)].append(record)
    cross_colour=[{'legacy_row_content_sha256':key,'records':rows}
                  for key,rows in old_identity.items() if len({r['colour'] for r in rows})>1]
    def counts(groups):
        crosses=[rows for rows in groups.values() if len({r['block'] for r in rows})>1]
        return {'unique_contents':len(groups),'duplicate_groups':sum(len(rows)>1 for rows in groups.values()),
                'cross_block_duplicate_groups':len(crosses),'rows_in_cross_block_duplicates':sum(len(rows) for rows in crosses)}
    legacy=counts(old_identity); current=counts(colour_identity)
    original_summary=json.loads((source/'TRANSFER_SUMMARY.json').read_text())
    require(legacy['cross_block_duplicate_groups']==original_summary['duplicate_content_groups_crossing_blocks']==952, "Validation failed: legacy['cross_block_duplicate_groups']==original_summary['duplicate_content_groups_crossing_blocks']==952")
    require(legacy['rows_in_cross_block_duplicates']==original_summary['rows_in_cross_block_duplicate_content_groups']==2090, "Validation failed: legacy['rows_in_cross_block_duplicates']==original_summary['rows_in_cross_block_duplicate_content_groups']==2090")
    reconciliation={'legacy_identity':'full parsed CSV row strings, no colour in duplicate key',
                    'new_identity':'colour plus full parsed CSV row strings',
                    'legacy_counts':legacy,'new_counts':current,
                    'cross_colour_content_groups':cross_colour,
                    'interpretation':'M12 counts are reproduced under their own content-only identity. Sensitivity counts differ because colour is part of the new frozen identity; no raw rows or baseline ranking outcomes changed. Neither identity establishes physical sample identity.'}
    (ROOT/'DUPLICATE_IDENTITY_RECONCILIATION.json').write_text(json.dumps(reconciliation,indent=2)+'\n')
    result={'status':'PASS','method':'Production Fraction/Counter compared against separate Decimal/SQLite/integer-crossproduct reconstruction; no production imports in independent calculation',
            'candidate_checks':candidate_checks,'block_rank_checks':block_checks,'group_count_score_checks':group_checks,
            'source_hashes_match':True,'plan_hashes_match':True,'production_result_sha256':digest(prod_path),
            'independent_result_sha256':digest(independent_path),'legacy_duplicate_counts_reproduced':True}
    (ROOT/'INDEPENDENT_COMPARISON_QA.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
