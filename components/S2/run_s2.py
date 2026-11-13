"""Reproduce the position-discount supplement in a new local working directory."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
S1_ZIP_SHA256 = '282a9e4f56db609734da2ebb07d5682af4c5753ba087b47dab0ceea3c3b220a8'
S1_MANIFEST_SHA256 = 'ab8a77ef0d3fc2bd0298a7c36693112695154a113e934bbc1aa0f93b76c85c3d'
CASES = {
    'dl21': ('replay/dl21/cases.json', '20cc22dcc68041622b507078d449ceb39b9bfcab2fdc727d31bab3fbcdca732b'),
    'dl22': ('work/ipm_elevate/mars/cases.json', '7d1bf9def75a146a50383dc817e83e99520d96259f771db860beb06a89581a66')}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def manifest(root):
    entries = []
    for line in (root/'SHA256SUMS.txt').read_text().splitlines():
        expected, rel = line.split('  ', 1)
        file = root/rel
        if not file.resolve().is_relative_to(root.resolve()):
            raise ValueError('Manifest path leaves its directory')
        if digest(file) != expected:
            raise ValueError('File digest differs: '+rel)
        entries.append(rel)
    return entries


def safe_extract(source, target):
    with ZipFile(source) as archive:
        for entry in archive.infolist():
            path = target/entry.filename
            if not path.resolve().is_relative_to(target.resolve()):
                raise ValueError('Archive path leaves its directory')
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('A source archive must not contain symlinks')
        archive.extractall(target)


def main():
    if not __debug__:
        raise RuntimeError('Run Python without -O; audit assertions are required.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['synthetic', 'proofs', 'full'])
    parser.add_argument('--output', type=Path, required=True, help='An unused output directory')
    parser.add_argument('--s1', type=Path, help='Original S1 ZIP or extracted S1 directory')
    parser.add_argument('--reuse-s1-results', action='store_true',
                        help='Read hash-checked reconstructed cases/results from the supplied S1 directory')
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    args = parser.parse_args()
    if args.mode != 'synthetic' and args.s1 is None:
        parser.error('--s1 is required for empirical modes')
    if args.reuse_s1_results and (args.s1 is None or not args.s1.is_dir()):
        parser.error('--reuse-s1-results requires an extracted S1 directory with completed replay outputs')
    if args.output.exists():
        parser.error('The output directory already exists; choose an unused path')
    if args.output.resolve().is_relative_to((HERE/'work').resolve()):
        parser.error('Choose an output directory outside this supplement\'s work/ source tree')
    manifest(HERE)
    output = args.output.resolve()
    output.mkdir(parents=True)
    shutil.copytree(HERE/'work', output/'work')
    phase = output/'work/ipm_phase2'
    receipt = {'mode':args.mode, 'status':'running', 'commands':[],
               'timing_scope':'Execution diagnostics; not a matched latency experiment',
               'input_redistribution':'Reconstructed inputs and generated case-level records remain local'}
    logdir = output/'logs';logdir.mkdir()

    def command(argv, label):
        start = time.perf_counter()
        logfile = logdir/(f'{len(receipt["commands"])+1:02d}_'+label+'.log')
        with logfile.open('w') as log:
            proc = subprocess.run(argv, cwd=output, stdout=log, stderr=subprocess.STDOUT)
        row = {'label':label, 'exit_code':proc.returncode,
               'seconds':time.perf_counter()-start, 'log':str(logfile.relative_to(output))}
        receipt['commands'].append(row)
        (output/'execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps(row), flush=True)
        if proc.returncode:
            raise RuntimeError(f'{label} failed; inspect {logfile}')

    def script(relative, *arguments):
        command([sys.executable, str(phase/relative), *map(str, arguments)], relative.replace('/','_').replace('.py',''))

    try:
        script('weighted/test_weighted.py')
        script('validation/validate_weighted.py')
        script('validation/validate_bounds_cli.py')
        for name in ['exhaustive_weighted', 'compare_scales', 'find_strict_witnesses']:
            command([args.cc, '-O3', '-std=c11', '-Wall', '-Wextra', '-Werror',
                     str(phase/'empirical'/(name+'.c')), '-o', str(phase/'empirical'/name)], 'compile_'+name)
        script('empirical/validate_enumerator.py')
        script('empirical/validate_scale_diagnostics.py')
        if args.mode != 'synthetic':
            supplied = args.s1.resolve()
            if supplied.is_file():
                if digest(supplied) != S1_ZIP_SHA256:
                    raise ValueError('S1 ZIP does not match the retained original bytes')
                supplied = output/'s1_extracted'
                supplied.mkdir()
                safe_extract(args.s1, supplied)
            if digest(supplied/'SHA256SUMS.txt') != S1_MANIFEST_SHA256:
                raise ValueError('S1 source manifest differs from the retained original')
            source_entries = manifest(supplied)
            destination = phase/'original_replay';destination.mkdir()
            if args.reuse_s1_results:
                receipt['source_mode'] = 'Reused reconstructed input bytes after source/case hash checks'
                for rel in [* [item[0] for item in CASES.values()], 'replay/dl21.json', 'replay/dl22.json']:
                    target = destination/rel;target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(supplied/rel, target)
            else:
                receipt['source_mode'] = 'Rebuilt from original S1 in an isolated local copy'
                for rel in [*source_entries, 'SHA256SUMS.txt']:
                    target = destination/rel;target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(supplied/rel,target)
                command(['bash', str(destination/'run_review.sh'), 'replay'], 'original_S1_replay')
            for cohort, (rel, expected) in CASES.items():
                casepath = destination/rel
                if digest(casepath) != expected:
                    raise ValueError('Reconstructed case bytes differ for '+cohort)
                script('weighted/run_weighted.py', '--cases',casepath,'--cases-sha256',expected,
                       '--protocol',phase/'PROTOCOL_DISCOUNT.md','--output',phase/'weighted'/f'empirical_{cohort}')
            script('validation/validate_empirical_records.py')
            if args.mode == 'full':
                for cohort, (rel, _) in CASES.items():
                    casepath = destination/rel
                    script('empirical/run_empirical.py',cohort,casepath,phase/'empirical'/cohort)
                    script('empirical/diagnose_scales.py',cohort,casepath,phase/'empirical'/f'{cohort}_scale_diagnostics.json')
                script('empirical/extract_strict_witnesses.py')
                script('empirical/reconcile_results.py')
                script('validation/validate_empirical_reconciliation.py')
                actual = json.loads((phase/'empirical/primary_summary.json').read_text())
                expected = json.loads((HERE/'expected/aggregate_expectations.json').read_text())
                for field in ['tables','pointwise_scale_diagnostics','strict_witness_counts','total_case_metric_completions']:
                    assert actual[field] == expected[field], field
                for cohort in CASES:
                    assert actual['proof_reconciliation'][cohort]['counts'] == expected['proof_reconciliation'][cohort]['counts']
                receipt['aggregate_comparison'] = 'All declared deterministic aggregate fields match'
                receipt['case_metric_completions'] = actual['total_case_metric_completions']
            receipt['portable_requests'] = 1328
        receipt['status'] = 'passed'
        (output/'execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps({'status':receipt['status'],'mode':args.mode,'output':str(output)},indent=2))
    except Exception:
        receipt['status'] = 'failed'
        (output/'execution_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
