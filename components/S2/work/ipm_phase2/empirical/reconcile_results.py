"""Reconcile independent flat counts and report scale-sensitive results."""
from collections import Counter
from hashlib import sha256
import csv
import json
from pathlib import Path
import run_empirical as run

HERE=Path(__file__).resolve().parent

def main():
    evidence={'status':'passed','flat_control':{},'proof_reconciliation':{},'scale_sensitivity':{},'headline':{},'source_hashes':{}}
    for cohort in ('dl21','dl22'):
        fresh=HERE.parent/'original_replay/replay'/f'{cohort}.json'
        reference=json.loads(fresh.read_text())
        directpath=HERE/cohort/'flat_gain_v1_1.json'
        direct=json.loads(directpath.read_text())
        assert reference['input_sha256']==direct['input_sha256']==run.HASHES[cohort]
        checks=Counter()
        assert set(reference['by_case'])==set(direct['by_case'])
        for cid,row in direct['by_case'].items():
            ref=reference['by_case'][cid]
            assert row['worlds']==ref['worlds'];checks['world_counts']+=1
            for endpoint in ('set','prefix'):
                a=row['endpoints'][endpoint];b=ref['outcomes']['3_'+endpoint]
                for left,right in [('change_worlds','change_worlds'),('strict_change_worlds','strict_change_worlds'),('all_zero_disagrees','zero_change'),('all_three_disagrees','three_change'),('equal_marginal_sets','marginals_equal'),('any_change','common_change')]:
                    assert a[left]==b[right],(cohort,cid,endpoint,left);checks['endpoint_properties']+=1
                assert (not a['always_change'])==b['common_agreement'];checks['endpoint_properties']+=1
                assert len(a['marginal_binary'])==b['binary_outputs'];checks['endpoint_properties']+=1
                assert len(a['marginal_graded'])==b['graded_outputs'];checks['endpoint_properties']+=1
        evidence['flat_control'][cohort]={'case_count':len(direct['by_case']),'completions':direct['completions_checked'],'checks':dict(checks),'reference':'fresh original compressed-incidence enumeration','reference_sha256':sha256(fresh.read_bytes()).hexdigest(),'direct_sha256':sha256(directpath.read_bytes()).hexdigest()}
        docs={s:json.loads((HERE/cohort/f'quantised_log_discount_floor_gain_v1_{s}.json').read_text()) for s in (10_000,1_000_000,100_000_000)}
        comparisons=[]
        for scale in (10_000,100_000_000):
            details=[];counts=Counter()
            for cid,base in docs[1_000_000]['by_case'].items():
                row=docs[scale]['by_case'][cid];diff=[]
                if row['joint_full_orders']!=base['joint_full_orders']:counts['joint_outcome_count_differences']+=1;diff.append('joint_counts')
                for endpoint in ('set','prefix'):
                    for key in ('any_change','strict_change','all_zero_disagrees','all_three_disagrees','missed_by_zero','missed_by_both_points','equal_marginal_sets','change_with_equal_marginal_sets','always_change','change_worlds','strict_change_worlds'):
                        if row['endpoints'][endpoint][key]!=base['endpoints'][endpoint][key]:
                            counts[f'{endpoint}:{key}']+=1;diff.append(f'{endpoint}:{key}')
                if diff:details.append({'case_id':cid,'fields_differing':diff})
            comparisons.append({'reference_scale':1_000_000,'scale':scale,'difference_counts':dict(counts),'details':details})
        evidence['scale_sensitivity'][cohort]=comparisons
        summary=docs[1_000_000]['by_stratum']
        headline={'primary_discount':summary,'flat':direct['by_stratum']}
        for name,doc in [('flat',direct),('discount',docs[1_000_000])]:
            for endpoint in ('set','prefix'):
                rows=[r for r in doc['by_case'].values() if r['stratum']=='natural']
                headline[f'{name}_{endpoint}_natural_strict_missed_by_zero']=sum(r['endpoints'][endpoint]['missed_by_zero'] and r['endpoints'][endpoint]['strict_change'] for r in rows)
                if name=='discount':headline[f'discount_{endpoint}_natural_real_margin_sufficient_cases']=sum(r['endpoints'][endpoint]['conservative_real_metric_strict_change_worlds']>0 for r in rows)
        evidence['headline'][cohort]=headline
        # Compare ALL proof verdicts, including wide empirical domains, to this
        # completely enumerated independent reference. Do not infer correctness
        # merely from producer/checker agreement.
        records_path=HERE.parent/'weighted'/f'empirical_{cohort}'/'records.json'
        records=json.loads(records_path.read_text());seen=set();proof_counts=Counter()
        all_docs={(metric,scale):json.loads((HERE/cohort/f'{metric}_{scale}.json').read_text()) for metric,scale in run.METRICS}
        for item in records:
            key=(item['case_id'],item['metric'],item['scale'],item['endpoint']);assert key not in seen;seen.add(key)
            doc=all_docs[item['metric'],item['scale']];case=doc['by_case'][item['case_id']];truth=case['endpoints'][item['endpoint']]['any_change'];record=item['record']
            assert item['verification']['accepted'] is True
            assert record['status']==('changed' if truth else 'invariant')
            assert record['case_sha256']==case['case_sha256']
            assert record['metric']['name']==item['metric'] and record['metric']['scale']==item['scale']
            assert record['metric']['gain_table_sha256']==doc['coefficient_table_sha256']
            proof_counts[record['status']]+=1;proof_counts['exact_reference_agreements']+=1
        expected_keys={(cid,metric,scale,endpoint) for cid in direct['by_case'] for metric,scale in run.METRICS for endpoint in ('set','prefix')}
        assert seen==expected_keys
        evidence['proof_reconciliation'][cohort]={'status':'passed','counts':dict(proof_counts),'records_sha256':sha256(records_path.read_bytes()).hexdigest(),'scope':'all four metrics and both endpoints matched full independent direct enumeration; no unresolved empirical reference cases'}
    evidence['total_case_metric_completions']=sum(evidence['flat_control'][c]['completions'] for c in ('dl21','dl22'))*4
    evidence['source_hashes']={name:sha256((HERE/name).read_bytes()).hexdigest() for name in ('reconcile_results.py','run_empirical.py','exhaustive_weighted.c','compare_scales.c','find_strict_witnesses.c','extract_strict_witnesses.py','independent_reference_snapshot.py')}
    evidence['interpretation']='Case-level stability across scales does not imply pointwise stability across identical completions. Counts are combinatorial, not probabilities.'
    (HERE/'reconciliation.json').write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n')
    rows=[]
    for cohort in ('dl21','dl22'):
        for metric,scale in run.METRICS:
            doc=json.loads((HERE/cohort/f'{metric}_{scale}.json').read_text())
            for stratum,summary in doc['by_stratum'].items():
                for endpoint in ('set','prefix'):
                    rows.append({'cohort':cohort,'stratum':stratum,'cases':summary['cases'],'metric':metric,'scale':scale,'endpoint':endpoint,**summary[endpoint]})
    with (HERE/'primary_tables.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    compact={'status':'passed','completion_units':'case-metric completions, not independent observations','total_case_metric_completions':evidence['total_case_metric_completions'],'proof_reconciliation':evidence['proof_reconciliation'],'tables':rows,'pointwise_scale_diagnostics':{c:json.loads((HERE/f'{c}_scale_diagnostics.json').read_text())['by_stratum'] for c in ('dl21','dl22')},'strict_witness_counts':{c:r['counts'] for c,r in json.loads((HERE/'strict_witnesses_primary.json').read_text())['cohorts'].items()}}
    (HERE/'primary_summary.json').write_text(json.dumps(compact,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'status':evidence['status'],'flat_control':evidence['flat_control'],'total_case_metric_completions':evidence['total_case_metric_completions'],'scale_sensitivity':{c:[{'scale':r['scale'],'counts':r['difference_counts']} for r in evidence['scale_sensitivity'][c]] for c in ('dl21','dl22')}},indent=2))

if __name__=='__main__':main()
