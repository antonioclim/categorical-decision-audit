#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
review_python=${PYTHON:-python3}
review_cc=${CC:-cc}
review_result=${1:-replay}
if [[ -e "$review_result" ]]; then
  printf 'Choose an unused results directory: %s\n' "$review_result" >&2
  exit 2
fi

sha256sum -c SHA256SUMS.txt
mkdir -- "$review_result"
review_cases21=20cc22dcc68041622b507078d449ceb39b9bfcab2fdc727d31bab3fbcdca732b
review_cases22=7d1bf9def75a146a50383dc817e83e99520d96259f771db860beb06a89581a66
review_cases19=a92ccf1b4976666ec7822d3e488e6d972e7febe5a9881e6b2190ef4912bb2b1d
review_cases20=4d47ccdeced5f335649a6da36958bf3469db2a5c5355bb50658765bb3d529396
review_stress=2b5c3f2187793840862e3da089eba8bcf6703b552d232a0d16a4bda20114be0d
review_proof=work/paperm_proof
review_core=work/ipm_elevate
"$review_python" "$review_proof/fetch_inputs.py" --history
"$review_python" "$review_proof/intake/build_dl21_cases.py" --output-dir "$review_result/dl21"
mkdir -p "$review_proof/intake/frozen/source_inputs"
cp -- "$review_result/dl21/source_inputs/2021.qrels.pass.final.txt" "$review_proof/intake/frozen/source_inputs/"
"$review_python" "$review_core/mars/fetch_dl22.py"
"$review_python" "$review_core/mars/freeze_structure.py"
"$review_python" work/paperm_revision/prepare_holdout.py work/paperm_revision/holdout/inputs --output-dir "$review_result/dl19"
"$review_python" work/dl20_pilot/prepare_cases.py work/ipm/literature --output-dir "$review_result/dl20"
"$review_python" "$review_core/selection.py" "$review_result/dl19/cases.json" "$review_result/dl19.json" --sha256 "$review_cases19"
"$review_python" "$review_core/selection.py" "$review_result/dl20/cases.json" "$review_result/dl20.json" --sha256 "$review_cases20"
"$review_python" "$review_core/selection.py" "$review_result/dl21/cases.json" "$review_result/dl21.json" --sha256 "$review_cases21"
"$review_python" "$review_core/selection.py" "$review_core/mars/cases.json" "$review_result/dl22.json" --sha256 "$review_cases22"
"$review_python" "$review_core/reconcile_dl22.py" "$review_core/mars/cases.json" "$review_result/dl22.json" "$review_result/dl22_direct.json"
"$review_python" "$review_proof/adjudicate_dl21.py" "$review_result/dl21/cases.json" "$review_result/dl21/masked_truth_oracle_only.json" "$review_result/dl21_reference.json" --cases-sha256 "$review_cases21"
"$review_python" "$review_proof/bench_proof.py" "$review_result/dl19/cases.json" "$review_result/dl19_portable" --cases-sha256 "$review_cases19" --cohort DL19
"$review_python" "$review_proof/bench_proof.py" "$review_result/dl20/cases.json" "$review_result/dl20_portable" --cases-sha256 "$review_cases20" --cohort DL20
"$review_python" "$review_proof/bench_proof.py" "$review_result/dl21/cases.json" "$review_result/dl21_portable" --cases-sha256 "$review_cases21" --cohort DL21 --external
"$review_python" "$review_proof/bench_proof.py" "$review_core/mars/cases.json" "$review_result/dl22_portable" --cases-sha256 "$review_cases22" --cohort DL22
"$review_python" "$review_proof/bench_proof.py" "$review_proof/stress_cases.json" "$review_result/stress_portable" --cases-sha256 "$review_stress" --cohort stress
"$review_python" "$review_proof/replay_record_mutations.py" "$review_result/dl21/cases.json" "$review_result/dl21_portable" "$review_result/dl21_mutations.json" --cases-sha256 "$review_cases21"
"$review_cc" -std=gnu11 -O2 -o "$review_result/drat-trim" "$review_core/generic_sat/vendor/drat-trim.c"
"$review_python" "$review_core/generic_sat/pilot.py" "$review_result/dl21/cases.json" "$review_result/dl21_reference.json" "$review_result/drat-trim" "$review_result/sat_dl21" --expect-cases-sha256 "$review_cases21" --check-encoding
"$review_python" "$review_core/generic_sat/pilot.py" "$review_core/mars/cases.json" "$review_result/dl22.json" "$review_result/drat-trim" "$review_result/sat_dl22" --expect-cases-sha256 "$review_cases22" --check-encoding
"$review_python" "$review_core/generic_sat/recheck.py" "$review_result/dl21/cases.json" "$review_result/sat_dl21" "$review_result/drat-trim" --expect-cases-sha256 "$review_cases21"
"$review_python" "$review_core/generic_sat/recheck.py" "$review_core/mars/cases.json" "$review_result/sat_dl22" "$review_result/drat-trim" --expect-cases-sha256 "$review_cases22"
review_handoff_archive="$review_result/handoff_archive"
mkdir -p "$review_handoff_archive/intake/frozen" "$review_result/handoff_blind"
cp -- "$review_proof/check_proof.py" "$review_proof/adjudicate_dl21.py" "$review_handoff_archive/"
cp -- "$review_result/dl21/cases.json" "$review_handoff_archive/intake/frozen/"
ln -s -- "$(realpath "$review_result/dl21_portable")" "$review_handoff_archive/benchmark_dl21"
"$review_python" "$review_core/handoff/handoff.py" --archive "$review_handoff_archive" --output "$review_result/handoff" build
cp -- "$review_result/handoff/requests.json" "$review_result/handoff_blind/"
"$review_python" "$review_core/handoff/handoff.py" --archive "$review_handoff_archive" --output "$review_result/handoff_blind" check
cp -- "$review_result/handoff_blind/blind_results.json" "$review_result/handoff/"
"$review_python" "$review_core/handoff/handoff.py" --archive "$review_handoff_archive" --output "$review_result/handoff" score
"$review_python" verify_replay.py "$review_result"
