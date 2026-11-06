#!/usr/bin/env python3
"""Build all prespecified Wine Quality transfer dossiers, without outcome selection."""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
import csv
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'transfer'
EXPECTED_PROTOCOL = '799e007b5f945c9ff33117e2c548ad59c65fbfcd8f3c24d4a22d91b177bb5435'
STATES = ['quality_le_5', 'quality_eq_6', 'quality_ge_7']
NAMESPACE = 'PaperM-R2-Wine-transfer-v1'
WEIGHTS = {'old': dict(zip(STATES, ['0', '1', '1'])), 'new': dict(zip(STATES, ['0', '0', '1']))}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def write(name, value):
    (DATA / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def build():
    protocol_raw = (DATA / 'PREACQUISITION_PROTOCOL.json').read_bytes()
    if sha(protocol_raw) != EXPECTED_PROTOCOL:
        raise ValueError('The retained preacquisition specification changed.')
    receipt = json.loads((DATA / 'ACQUISITION_RECEIPT.json').read_text())
    if receipt['protocol_sha256'] != EXPECTED_PROTOCOL:
        raise ValueError('Acquisition was not bound to the current specification.')
    blocks = {i: [] for i in range(18)}
    rows, payloads = [], defaultdict(list)
    for colour in ['red', 'white']:
        file = DATA / f'winequality-{colour}.csv'
        if sha(file.read_bytes()) != receipt['files'][file.name]['sha256']:
            raise ValueError('Raw source hash changed: ' + file.name)
        with file.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream, delimiter=';')
            if not {'alcohol', 'pH', 'quality'} <= set(reader.fieldnames):
                raise ValueError('Required source columns missing.')
            for index, row in enumerate(reader, 1):
                quality = int(row['quality'])
                if quality < 0 or quality > 10:
                    raise ValueError('Out-of-schema quality; no silent filtering.')
                alcohol, ph = Fraction(row['alcohol']), Fraction(row['pH'])
                alcohol_band = 0 if alcohol < 10 else 1 if alcohol < 11 else 2
                ph_band = 0 if ph < Fraction(16, 5) else 1
                group = f'G{2 * alcohol_band + ph_band + 1:02d}'
                state = STATES[0 if quality <= 5 else 1 if quality == 6 else 2]
                record_id = f'{colour}:{index}'
                token = f'{NAMESPACE}\0{colour}\0{index}'.encode()
                block = int.from_bytes(hashlib.sha256(token).digest(), 'big') % 18
                payload = canonical(row)
                record = {'record_id': record_id, 'colour': colour, 'data_row': index,
                          'block': block, 'group_id': group, 'state': state,
                          'row_content_sha256': sha(payload)}
                rows.append(record)
                blocks[block].append(record)
                payloads[sha(payload)].append(record)
    if not rows:
        raise ValueError('No source rows.')
    alcohol_labels = ['alcohol<10', '10<=alcohol<11', 'alcohol>=11']
    ph_labels = ['pH<3.2', 'pH>=3.2']
    group_labels = {f'G{2*a+b+1:02d}': alcohol_labels[a] + '|' + ph_labels[b]
                    for a in range(3) for b in range(2)}
    cases, keys, candidate_results = [], [], []
    for block in range(18):
        counts = {group: Counter({s: 0 for s in STATES}) for group in group_labels}
        for row in blocks[block]:
            counts[row['group_id']][row['state']] += 1
        nonempty = [g for g in group_labels if sum(counts[g].values())]
        score = {side: {g: sum(counts[g][s] * Fraction(WEIGHTS[side][s]) for s in STATES)
                         / sum(counts[g].values()) for g in nonempty} for side in ['old', 'new']}
        ranks = {side: sorted(nonempty, key=lambda g: (-score[side][g], g)) for side in ['old', 'new']}
        for k in [2, 3]:
            cid = f'R2-W{block+1:02d}-K{k}'
            if len(nonempty) < k + 1:
                candidate_results.append({'case_id': cid, 'block': block, 'k': k,
                                          'eligible': False, 'reason': 'Fewer than k+1 nonempty groups.'})
                continue
            old, new = ranks['old'][:k], ranks['new'][:k]
            kind = 'same_order' if old == new else 'order_only' if set(old) == set(new) else 'membership_change'
            selected_ties = {side: len({score[side][g] for g in ranks[side][:k]}) < k for side in ['old', 'new']}
            boundary_ties = {side: score[side][ranks[side][k-1]] == score[side][ranks[side][k]] for side in ['old', 'new']}
            reversals = [[a, b] for a, b in combinations(sorted(set(old) & set(new)), 2)
                         if (score['old'][a]-score['old'][b])*(score['new'][a]-score['new'][b]) < 0]
            strict_order_only = kind == 'order_only' and not any(selected_ties.values())
            profile = {'old_label': 'quality_at_least_6', 'new_label': 'quality_at_least_7',
                       'old_weights': WEIGHTS['old'], 'new_weights': WEIGHTS['new']}
            groups = [{'id': g, 'label': group_labels[g], 'counts': dict(counts[g]),
                       'count_total': sum(counts[g].values()),
                       'old_score': str(score['old'][g]), 'new_score': str(score['new'][g])} for g in nonempty]
            tie_note = ('Selected-score ties occur under at least one coding. ' if any(selected_ties.values()) else 'No equal scores occur within either selected list. ')
            tie_note += ('A score tie also crosses at least one selection boundary. ' if any(boundary_ties.values()) else 'No score tie crosses either selection boundary. ')
            tie_note += 'Apply the displayed deterministic tie convention; no tie-independent robustness is implied.'
            case = {
                'case_id': cid, 'title': 'Wine quality definition review ' + cid,
                'source_case_id': f'WineQuality-partition-{block+1:02d}-k{k}',
                'source_kind': 'observed physicochemical wine measurements and sensory quality labels',
                'source_ref': 'https://doi.org/10.24432/C56S3T',
                'source_sha256': receipt['raw_zip_sha256'],
                'scope': 'current supplied allocation only',
                'context': {'attribute': 'record_partition', 'value': f'B{block+1:02d}',
                            'grouped_attributes': ['alcohol_band', 'pH_band']},
                'states': STATES, 'profiles': profile, 'groups': groups,
                'rule': {'kind': 'top_k', 'k': k, 'direction': 'highest_first',
                         'tie_break': 'ascending fixed group ID (alcohol band then pH band)'},
                'old_order': old, 'new_order': new, 'tie_note': tie_note,
                'provenance_note': 'Observed source records are partitioned and grouped by prespecified research rules. The definition change and group-selection rule are hypothetical; this is not an observed organisational migration or wine-safety recommendation.',
                'evidence': [
                    {'id': 'E1', 'title': 'Source and supplied allocation', 'detail': 'UCI Wine Quality, DOI https://doi.org/10.24432/C56S3T; records assigned to one of 18 SHA-256 partitions before scoring. Wine properties and sensory labels are observed source variables; the review task is hypothetical.'},
                    {'id': 'E2', 'title': 'Old and new coding profiles', 'detail': 'Old score is the proportion with sensory quality at least 6; new score is the proportion with quality at least 7. These are different research-defined estimands, not official policy versions or interchangeable definitions.'},
                    {'id': 'E3', 'title': 'Decision rule and tie rule', 'detail': f'Select {k} nonempty groups by decreasing exact score, breaking ties by ascending fixed group ID. Review concerns the supplied partition only.'},
                    {'id': 'E4', 'title': 'Group counts and exact scores', 'detail': 'Scores use exact count-weighted means of the displayed state weights. Groups use fixed alcohol cut points 10 and 11 and pH cut point 3.2, chosen before raw acquisition rather than optimised from outcomes.'},
                    {'id': 'E5', 'title': 'Selected groups in priority order', 'detail': 'The two lists contain only the selected top-k group IDs in rule order. Preservation of count, membership and ordered selection are separate review requirements.'},
                ],
            }
            key = {'case_id': cid, 'block': block, 'change_type': kind,
                   'targets': {'CAPACITY': 'APPROVE', 'MEMBERSHIP': 'APPROVE' if set(old)==set(new) else 'REJECT',
                               'PRIORITY': 'APPROVE' if old==new else 'REJECT'},
                   'selected_score_ties': selected_ties, 'boundary_ties': boundary_ties,
                   'strict_order_only': strict_order_only,
                   'strict_pair_reversals_within_common_selected_groups': reversals,
                   'source_record_ids': [r['record_id'] for r in blocks[block]]}
            cases.append(case);keys.append(key)
            candidate_results.append({'case_id': cid, 'block': block, 'k': k, 'eligible': True,
                                      'change_type': kind, 'strict_order_only': strict_order_only,
                                      'selected_score_ties': selected_ties, 'boundary_ties': boundary_ties})
    duplicate_contents = [v for v in payloads.values() if len(v) > 1]
    across_blocks = [v for v in duplicate_contents if len({r['block'] for r in v}) > 1]
    summary = {'status': 'TRANSFER_CASE_BANK_COMPUTATION_NOT_HUMAN_EVIDENCE',
               'raw_rows': len(rows), 'rows_by_colour': dict(Counter(r['colour'] for r in rows)),
               'blocks': 18, 'candidate_cases': 36, 'retained_cases': len(cases),
               'excluded_cases': [x for x in candidate_results if not x['eligible']],
               'change_counts': dict(Counter(k['change_type'] for k in keys)),
               'distinct_blocks_by_change_type': {kind: sorted({k['block']+1 for k in keys if k['change_type']==kind}) for kind in ['same_order','order_only','membership_change']},
               'strict_order_only_count': sum(k['strict_order_only'] for k in keys),
               'strict_order_only_distinct_blocks': sorted({k['block']+1 for k in keys if k['strict_order_only']}),
               'strict_order_only_without_boundary_ties_count': sum(k['strict_order_only'] and not any(k['boundary_ties'].values()) for k in keys),
               'case_target_cells': len(keys)*3,
               'unsafe_membership_priority_cells': sum(k['targets'][t]=='REJECT' for k in keys for t in ['MEMBERSHIP','PRIORITY']),
               'safe_membership_priority_cells': sum(k['targets'][t]=='APPROVE' for k in keys for t in ['MEMBERSHIP','PRIORITY']),
               'capacity_control_cells': len(keys),
               'record_partitions_disjoint': len({r['record_id'] for r in rows}) == len(rows),
               'duplicate_content_groups': len(duplicate_contents),
               'duplicate_content_groups_crossing_blocks': len(across_blocks),
               'rows_in_cross_block_duplicate_content_groups': sum(len(v) for v in across_blocks),
               'dependence': 'Two rules reuse each record partition. Exact duplicate raw row contents cross partitions, and source batch/sample identities are not provided; disjoint record IDs do not establish independent biological samples or source replication.',
               'protocol_sha256': EXPECTED_PROTOCOL}
    public = {'schema_version': 'PaperM-R2-transfer-casebank-v1', 'status': 'preacquisition_specified_transfer_computation_not_human_study',
              'targets': {'CAPACITY': 'equal selected count', 'MEMBERSHIP': 'equal selected identities irrespective of order',
                          'PRIORITY': 'equal selected sequence'}, 'cases': cases}
    write('public_transfer_cases.json', public)
    write('private_transfer_key.json', {'schema_version': 'PaperM-R2-transfer-key-v1',
                                      'status': 'private_reference_answers_not_participant_data', 'cases': keys})
    write('ALL_CANDIDATES.json', candidate_results)
    write('RECORD_PARTITION_MAP.json', {'namespace': NAMESPACE, 'records': rows})
    write('TRANSFER_SUMMARY.json', summary)
    write('DUPLICATE_ROW_CONTENT_AUDIT.json', {'duplicate_content_groups': [
        {'row_content_sha256': v[0]['row_content_sha256'], 'record_ids': [r['record_id'] for r in v],
         'blocks': sorted({r['block'] for r in v})} for v in duplicate_contents]})
    write('TRANSFER_PROVENANCE.json', {'source': json.loads(protocol_raw)['source'],
                                     'raw_inputs': receipt['files'], 'protocol_sha256': EXPECTED_PROTOCOL,
                                     'public_bank_sha256': sha((DATA/'public_transfer_cases.json').read_bytes()),
                                     'licence_scope': 'CC BY 4.0 source and identified adaptations retain attribution; no claim of novel observed policy changes or human efficacy.'})
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    build()
