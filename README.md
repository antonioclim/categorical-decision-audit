# When Relevance Coding Changes the Shortlist

Reproducibility software for exact evidence about retrieval run selection under
shared incomplete judgements.

**Distribution:** 2.0.0, supporting research version R07 and manuscript
revision R07-D2. This snapshot was prepared locally on 12 November 2026 for
the existing [categorical-decision-audit repository](https://github.com/antonioclim/categorical-decision-audit).
At preparation, this distribution had not been uploaded or published and no
new DOI had been confirmed. The historical v1.0.0 release remains a separate,
unchanged snapshot; see `CHANGELOG.md` for the change of empirical scope.

No general public licence is designated for the author's original materials
in this distribution. Identified third-party notices remain applicable;
see `RIGHTS.md`. Preparation does not grant additional reuse permissions.

## Research question and result

For four fixed depth-ten runs and a top-three decision, do binary and linear
graded relevance codings agree at every admissible common completion? Each
missing passage has one grade across all its occurrences and both codings.
The software either provides a separating completion or a finite certificate
whose integer bounds can be reconstructed by a separate checker.

The original experiments use flat gains. The extension uses the declared
integer rule `floor(S*gain/log2(rank+1))`, with a primary scale of 1,000,000 and
two sensitivity scales. This is not nDCG or a universal real-valued DCG
certificate. In 70 naturally incomplete DL22 cases, the primary discounted
rule admits 48 membership changes; zero-filling finds 12 and misses 36, all of
which admit strict changes. All 1,328 extension/control requests agree with
complete independent enumeration. Existence verdicts are stable across the
tested scales, but individual completions can change their outcomes.

The original DL21 latency result remains unfavourable: the median paired
verification-to-solving ratio was 6.426. New execution times are local
diagnostics and do not replace that result. Completion counts are not
independent observations or probabilities.

## Contents

| Path | Purpose |
|---|---|
| `components/S1/` | Preserved original flat-score reconstruction, exact baselines, SAT/DRAT and handoff experiments |
| `components/S2/` | Preserved discounted producer/checker, certified coefficients, independent reference, synthetic validation, aggregate expectations and figures |
| `run_reproduction.py` | Unified entry point; all generated results go to a new directory outside this repository |
| `requirements.txt`, `ENVIRONMENT.md` | Python packages and separate system dependencies for full reconstruction |
| `CITATION.cff` | Software citation metadata with the confirmed author and version; verified repository URL; no unconfirmed DOI or release date |
| `SOURCE_COMPONENTS.json` | Original archive identities and verification of each preserved component |
| `RIGHTS.md`, `THIRD_PARTY_NOTICES.md` | Actual licensing state and retained third-party attribution |

No raw third-party run files or qrels are bundled. Real passage-level cases,
witness assignments, signing outputs and execution logs are generated locally.
The included synthetic cases and aggregate figure inputs are sufficient for
the offline smoke test and deterministic figure regeneration. No GitHub
Actions workflow is included.

## Verify the package

Use Python 3.12 without `-O`. From the repository root:

```bash
python3 run_reproduction.py check
```

The outer manifest and both preserved component manifests must pass. A digest
checks identity of bytes; it does not authenticate a provider or confer reuse
rights.

## Offline smoke test

With a local C compiler available as `cc`:

```bash
python3 run_reproduction.py smoke --output ../paper-m-smoke
```

This executes the flat compatibility cases, independent weighted/control
synthetic validation, mutation and invalid-input checks, exact row/bound
comparisons, native CLI checks and the independent C reference tests. It uses
the Python standard library and a C compiler. It neither downloads data nor
claims a full TREC reproduction.

Every execution path requires an unused output directory. On subsequent runs,
choose another name. The repository itself remains unchanged.

## Reproduce all experiments

Install the full environment described in `ENVIRONMENT.md`, then run:

```bash
python3 run_reproduction.py full --output ../paper-m-full
```

The runner copies S1 to a separate workspace, reconstructs the pinned inputs
from the original providers and runs S1's checks. It then checks the case
digests and performs the full S2 proof, enumeration, scale-sensitivity and
strict-witness analyses. Exact aggregate fields must match the recorded
expectations. The initial source acquisition needs read-only network access.

If original S1 has already been reconstructed, its completed directory can be
used without changing it:

```bash
python3 run_reproduction.py full --s1-results ../S1_completed --output ../paper-m-cached
```

`S1_completed` denotes the existing S1 directory with its unchanged source
manifest and completed `replay` results. The runner verifies the source and
case hashes, copies only the relevant inputs and performs the complete S2
analysis. This cached mode does not reexecute S1 itself.

For a shorter empirical check:

```bash
python3 run_reproduction.py proofs --s1-results ../S1_completed --output ../paper-m-proofs
```

This mode produces and checks all 1,328 requests and independently rescores the
emitted witnesses. It does not enumerate every completion in the large DL22
domains. Use `full` for that independent reference.

## Regenerate the figures

For a new figure directory, with LibreOffice and Poppler installed:

```bash
python3 run_reproduction.py figures --output ../paper-m-figures
```

The three editable ODG figures are generated from aggregate JSON/CSV inputs,
then exported to vector PDF and 600 dpi PNG. Every visible label, bar, matrix
cell and axis element is a native Draw object. The figure README explains
individual editing and the application roundtrip test. An existing ODG can
also be edited directly in LibreOffice Draw.

## Expected coverage

| Analysis | Deterministic result |
|---|---:|
| Original portable requests, including DL22 | 856 |
| Original SAT/DRAT requests | 332 |
| Original mutation checks | 74 |
| Original handoff trials | 1,031 |
| Extension/control requests | 1,328 |
| Extension changes / invariances / unresolved | 842 / 486 / 0 |
| Complete independent case–metric completions | 578,121,052 |

The units differ and must not be added as independent observations. The
original and extended formats have different metadata and byte counts. The
new format does not inherit the original handoff benchmark. Methods, metric
limits and aggregate tables are documented inside the two components.

## Citation and provenance

Use `CITATION.cff` for software distribution 2.0.0. The associated manuscript
is *When Relevance Coding Changes the Shortlist: Exact evidence for retrieval
run selection under shared incomplete judgements*, revision R07-D2. No journal
publication or acceptance is implied. Component files are preserved byte for byte; the
repository entry point and documentation only organise their execution.
The clean S2 protocol transcription and its two driver hash updates are
documented within S2. Its scientific specification is unchanged.

Reconstructed source files and passage-level records should not be committed
or redistributed merely because their providers permit public downloads.
The manifests retain the actual providers, revisions and hashes. Consult the
applicable source terms; this repository assigns no licence to those data.
