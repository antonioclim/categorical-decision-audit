#!/usr/bin/env python3
"""Reconstruct both Wine sensitivity implementations in a disposable copy."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
PLAN='07e1114322f57be40c7f5da397dd4a6d54324ac072080b840c5d17265e9b7d11'
RAW={'winequality-red.csv':'4a402cf041b025d4566d954c3b9ba8635a3a8a01e039005d97d6a710278cf05e',
     'winequality-white.csv':'76c3f809815c17c07212622f776311faeb31e87610d52c26d87d6e361b169836'}


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition,message):
    if not condition: raise ValueError(message)


def main():
    require(digest(ROOT/'EXPLORATORY_PLAN.json')==PLAN,'Exploratory plan hash mismatch')
    for name,expected in RAW.items():
        require(digest(ROOT/'inputs'/name)==expected,'Raw source changed: '+name)
    expected_result=digest(ROOT/'SENSITIVITY_RESULTS.json')
    with tempfile.TemporaryDirectory(prefix='paperm_wine_sensitivity_') as directory:
        stage=Path(directory)/'wine'
        shutil.copytree(ROOT,stage,ignore=shutil.ignore_patterns('__pycache__'))
        for script in ['scripts/run_sensitivity.py','independent/reconstruct_independent.py','scripts/compare_reconstructions.py']:
            result=subprocess.run([sys.executable,str(stage/script)],cwd=stage,text=True,capture_output=True)
            require(result.returncode==0,script+' failed: '+result.stdout+'\n'+result.stderr)
        require(digest(stage/'SENSITIVITY_RESULTS.json')==expected_result,'Raw reconstruction differs from retained result')
        comparison=json.loads((stage/'INDEPENDENT_COMPARISON_QA.json').read_text())
        require(comparison['status']=='PASS','Separate reconstruction comparison failed')
        require((comparison['candidate_checks'], comparison['block_rank_checks'], comparison['group_count_score_checks']) == (144,72,432), 'Separate reconstruction comparison scope differs')
        require(comparison['plan_hashes_match'] and comparison['source_hashes_match'], 'Comparison source/plan bindings failed')
        for name,expected in RAW.items():
            require(digest(stage/'inputs'/name)==expected,'Disposable raw source changed: '+name)
    print(json.dumps({'status':'PASS','scope':'Wine post-outcome exploratory sensitivity only',
                      'plan_sha256':PLAN,'retained_result_reproduced_byte_identically':True,
                      'candidate_classifications_compared':comparison['candidate_checks'],'block_rankings_compared':comparison['block_rank_checks'],
                      'group_count_score_payloads_compared':comparison['group_count_score_checks'],'third_party_dependencies':False,
                      'raw_sources_unchanged':True,'original_kernel_rerun':False,
                      'human_or_organisational_evidence':False},indent=2))


if __name__=='__main__': main()
