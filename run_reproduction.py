"""Run the preserved reproducibility components in an unused external directory."""
from hashlib import sha256
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def verify_manifest(directory):
    count = 0
    for line in (directory/'SHA256SUMS.txt').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = directory/name
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Manifest path leaves repository')
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Manifest mismatch: '+name)
        count += 1
    return count


def main():
    if not __debug__:
        raise RuntimeError('Run Python without -O; audit assertions must remain enabled.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check','smoke','proofs','full','figures'])
    parser.add_argument('--output', type=Path, help='An unused directory outside the repository')
    parser.add_argument('--s1-results', type=Path,
        help='Optional completed original S1 directory, read only and checked by source/input hashes')
    parser.add_argument('--cc', default='cc', help='C compiler for S2')
    args = parser.parse_args()
    counts = {'repository':verify_manifest(ROOT),
              'original_S1':verify_manifest(ROOT/'components/S1'),
              'discount_S2':verify_manifest(ROOT/'components/S2')}
    if args.mode == 'check':
        print(json.dumps({'status':'passed','checked_manifest_entries':counts},indent=2))
        return
    if args.output is None:
        parser.error('--output is required for execution')
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        parser.error('Choose an output directory outside the repository to keep generated case data separate')
    if output.exists():
        parser.error('Choose an unused output directory')
    if args.s1_results is not None and args.mode not in ['proofs','full']:
        parser.error('--s1-results applies only to proofs or full')
    if args.mode == 'figures':
        shutil.copytree(ROOT/'components/S2/figures', output)
        for script in ['build_figures.py','export_figures.py']:
            subprocess.run([sys.executable,str(output/'scripts'/script)],check=True)
        print(json.dumps({'status':'passed','figures':str(output)},indent=2))
        return
    s2_mode = 'synthetic' if args.mode == 'smoke' else args.mode
    command = [sys.executable,str(ROOT/'components/S2/run_s2.py'),s2_mode,
               '--output',str(output),'--cc',args.cc]
    if args.mode in ['proofs','full']:
        source = args.s1_results.resolve() if args.s1_results else ROOT/'components/S1'
        command += ['--s1',str(source)]
        if args.s1_results:command.append('--reuse-s1-results')
    subprocess.run(command,check=True)


if __name__ == '__main__':
    main()
