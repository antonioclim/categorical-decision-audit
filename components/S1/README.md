# Relevance coding shortlist study

This supplement reconstructs the inputs and checks the results of *When Relevance Coding Changes the Shortlist*. It contains analysis code, acquisition manifests, synthetic cases and aggregate checks. The original providers host the judgement and run files. The acquisition scripts check the expected size and SHA-256 of each source before use.

## Run the checks

Use an extracted local directory and a Linux x86-64 environment with Bash, GNU coreutils, a C compiler, Python 3.12 and a loadable `libz3.so.4`. The original analysis used Z3 4.13.3.0. Network access is needed for the pinned NIST and raw GitHub URLs on first acquisition. The frozen DL21 catalogue HTML is included because the live page can change independently of the judgement and run bytes. It contains links and provenance for the acquisition check. Leave generated results local, as they can include source-derived identifiers and witness assignments.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install 'numpy==2.3.5' 'python-sat==1.8.dev24' 'cryptography==50.0.0'
bash run_review.sh
```

The runner checks the manifest, reconstructs DL19 through DL22, generates proofs and baseline outcomes, exhaustively reconciles DL22, runs and verifies the generic SAT route and replays the checker mutations and blinded DL21 handoff. The results directory defaults to `replay`. A different unused directory can be passed as the first argument. `expected_checks.json` contains the deterministic acceptance counts. New timings describe the local machine and need not match the manuscript's recorded timings.

## Sources and use

- The TREC Deep Learning Track passage judgements come from NIST. The manifests record the exact files, including the DL22 file with propagated duplicate judgements. See the NIST track data pages for [DL19](https://trec.nist.gov/data/deep2019.html), [DL20](https://trec.nist.gov/data/deep2020.html), [DL21](https://trec.nist.gov/data/deep2021.html) and [DL22](https://trec.nist.gov/data/deep2022.html).
- The Castorini RankLLM Data commit provides retrieval runs. DL22 also uses a pinned ColBERT run to evaluate a candidate slate and three pinned reranker outputs for the selected slate. The four manifests identify the exact paths, commits, hashes and source URLs. Consult the original providers' terms before any redistribution.
- DRAT-trim is included with its upstream licence. NumPy, python-sat, cryptography and Z3 are obtained separately from their providers. The test signing keys in the handoff diagnostic are deterministic test fixtures.
