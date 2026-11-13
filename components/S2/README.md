# Position-discount extension

This supplement accompanies *When Relevance Coding Changes the Shortlist*.
It contains the position-discounted proof producer and independent checker,
certified integer coefficient tables, synthetic validation, direct enumeration
and aggregate expectations for the DL21 and DL22 follow-up. The original
unweighted experiments remain in Supplementary Material S1.

## What is included

- The producer, checker and coefficient registry used in the validated analysis.
- Independent Python score, row, bound, witness and certificate checks.
- C sources for complete enumeration, comparison of the same completion across
  scales and extraction of strict separating completions.
- Synthetic cases, source URLs and input digests, the fixed scientific analysis
  specification and aggregate result tables.
- A runner that creates an unused local workspace and does not overwrite the
  supplement or the supplied S1 directory.

Third-party runs, qrels, reconstructed passage-level cases and real witness
assignments are not included. They are reconstructed locally from S1's pinned
sources. Public accessibility is not treated as permission to redistribute
those source files or the resulting passage-level records. Keep reconstructed
inputs and case-level outputs local unless their applicable rights permit
sharing. The supplement does not assign a new licence to third-party material.

## Scoring and interpretation

The discounted contribution is `floor(S*gain/log2(rank+1))`, with one-based ranks
1–10, binary gains `(0,0,1,1)` and linear graded gains `(0,1,2,3)`. The primary
scale is 1,000,000; sensitivity scales are 10,000 and 100,000,000. The control
uses the unweighted gains. One missing passage has one shared grade across all
its occurrences and both profiles. Ties favour the lexically earlier run.

There are four runs and the endpoints are top-three membership or ordered
prefix. Exactness concerns the declared integer metric. A qualifying concrete
witness with every required integer margin above 20 also establishes its
discrepancy for the corresponding real-valued score. An integer invariance
certificate does not establish real-valued DCG invariance. Completion counts
are combinatorial counts, without a probability model.

The producer may return `unresolved` when its node or record budget is exhausted.
That state is not accepted as change or invariance. The independent empirical
reference similarly reports a domain above `2^28` completions as unresolved.

## Environment

The reference environment is Linux x86-64 with Python 3.12 and a C compiler
available as `cc`. The synthetic and cached-input extension commands use only
the Python standard library and the local compiler. Do not pass Python `-O`:
the validation programs intentionally use assertions.

Rebuilding original S1 additionally requires Bash, GNU coreutils, a loadable
`libz3.so.4` and the packages listed in `requirements_s1.txt`. S1 used Z3
4.13.3.0. See S1's README for its environment and source acquisition details.
Initial reconstruction reads the pinned NIST and raw GitHub URLs. No account,
external write or GitHub Actions is used.

## One-command offline validation

From the extracted supplement directory:

```bash
python3 run_s2.py synthetic --output ../S2_synthetic_run
```

Choose a new output name on a later run. This executes the 208 original flat
compatibility requests, 536 independent weighted/control synthetic requests,
the malformed-input and mutation checks, row/bound comparisons, native command
line checks and the independent C reference validation. It does not claim to
reproduce TREC results. Logs and a machine-readable receipt are written to the
new directory.

## Complete reconstruction and evaluation

Place the original S1 ZIP beside this extracted directory. The command below
uses the adjacent S1 filename in the manuscript package; an alternative path
may be passed with `--s1`. The original bytes and their source manifest are
verified before use.

```bash
python3 run_s2.py full --s1 ../PaperM_IPM_Supplementary_Material_S1.zip --output ../S2_full_run
```

The runner copies the original S1 sources into its own workspace, runs S1's
reconstruction and checks, verifies the two case digests, produces and checks
all 1,328 weighted/control requests, runs complete independent enumeration at
all four metric variants, extracts strict witnesses, compares scales and
reconciles every deterministic aggregate field with `expected/`.

If S1 was already reconstructed, use its directory containing `SHA256SUMS.txt`,
`replay/dl21/cases.json`, `replay/dl21.json`, `replay/dl22.json` and
`work/ipm_elevate/mars/cases.json`:

```bash
python3 run_s2.py full --s1 ../S1_completed --reuse-s1-results --output ../S2_cached_run
```

That path is read only. The relevant verified inputs are copied to a new
workspace; no earlier output is replaced. `proofs` can be substituted for
`full` to produce and check the 1,328 requests and independently rescore every
emitted witness, without reenumerating all large domains. This shorter mode
does not claim complete independent empirical enumeration.

For rebuilding S1 in an isolated Python environment, install its declared
Python dependencies before the full command:

```bash
python3.12 -m venv ../S2_environment
. ../S2_environment/bin/activate
python -m pip install -r requirements_s1.txt
```

The system C compiler, Bash, GNU coreutils and `libz3.so.4` are separate
requirements. The supplement does not install system packages or request
administrator privileges automatically.

## Expected results

The complete extension covers 166 cases, four metric variants and two
endpoints: 1,328 requests, comprising 842 changes and 486 invariances. The
complete reference counts 578,121,052 case–metric completions. These units are
not independent queries. In the 70 naturally incomplete DL22 cases at the
primary discounted scale, membership can change in 48 cases, 47 admit a
strict change and all 36 cases missed by zero-filling admit strict witnesses.
Case-level classifications are stable across the tested scales, but some
individual completions change their outputs. Full tables and sensitivity
counts are retained in `expected/`.

Execution times are local diagnostics and will differ between machines. S1's
negative latency result is retained; this supplement makes no new speed
claim. Production records have a versioned metric descriptor and must not be
assigned the byte counts or handoff timings of S1's older record format.

## Provenance and integrity

`SHA256SUMS.txt` covers every packaged file except itself. The runner checks it
before executing. `source_provenance.json` identifies unchanged source files
and the two driver changes that bind the clean scientific protocol copy.
The producer, checker and registered coefficient table are byte-identical to
the versions validated in the follow-up.

The scientific specification was fixed privately on 12 November 2026 before
the discounted outcomes were calculated. It was not publicly preregistered.
The copy here removes operational correspondence from its original final
paragraph and updates its heading; the method, cohorts, metric definitions,
budgets and analysis choices are unchanged. The original specification digest
is retained in `source_provenance.json`. The earlier internal directory names
are retained solely to keep the validation programs' relative paths stable.
