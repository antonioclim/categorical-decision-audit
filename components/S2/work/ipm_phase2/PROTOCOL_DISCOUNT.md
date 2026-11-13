# Analysis protocol for the position-discount extension

Protocol fixed on 12 November 2026 before computing the new discounted empirical outcomes. This is a private prospective analysis specification for this follow-up, not a public preregistration. The original R06 analyses and their negative latency result remain intact.

## Question and scope

Test whether the reported limits of all-zero and two-constant-completion screening persist when the same four depth-ten lists receive fixed position discounts. The target remains within-query top-three membership or ordered prefix under the same shared completion. No claim about optimal annotation, realised relevance labels, RAG performance, real-valued DCG invariance or a new latency advantage is presupposed.

Primary cohort is the frozen 76-case DL22 slate. Report 70 naturally incomplete and six observed cases separately. Secondary cohort is the unchanged DL21 90-case suite, reporting observed, naturally incomplete and masked strata separately. Masks and observed cases from the same query are not independent observations.

Required case-file SHA-256 values

- DL21 `20cc22dcc68041622b507078d449ceb39b9bfcab2fdc727d31bab3fbcdca732b`
- DL22 `7d1bf9def75a146a50383dc817e83e99520d96259f771db860beb06a89581a66`

These values identify the canonical case bytes from the existing reconstruction protocol. File digests must be reconciled against the original runner before use. No query, grade, run or completion may be selected according to a discounted outcome.

## Metrics

Retain binary gain `(0,0,1,1)` and linear graded gain `(0,1,2,3)`. The control is the original unweighted total. For the extension, the contribution of gain `a` at one-based rank `r` is `floor(S*a/log2(r+1))`. The primary scale is `S=1000000`; sensitivity scales are `S=10000` and `S=100000000`. This is downward quantisation of the whole discounted gain. It is not gain times a separately rounded discount. It is not exponential-gain nDCG.

All nonzero coefficients for gains 1 through 3 and ranks 1 through 10 must be certified against the mathematical floor using exact integer inequalities or rigorous rational logarithm enclosures. Numerical approximations may propose a candidate but cannot alone certify it. The fixed table, scale, gains, rounding rule, tie rule and ranked case must be bound to each request. Each missing passage has exactly one grade across its occurrences and both gain profiles.

Ranks run from 1 through 10. Lists contain distinct passage identifiers. Run names are sorted lexically and ties in total score favour the earlier name. The new proof reduction remains specific to four runs and top three. Scenarios cover possible discrepancies; prefix scenarios can overlap.

## Proof route

Use a separately reconstructed integer checker. A certificate covers all twelve change scenarios with complete four-way branch coverage and strictly negative bounds on nonempty subsets of scenario rows. A change record contains a complete shared assignment and must reproduce the requested discrepancy. The producer and checker both enforce a cumulative maximum of 4096 proof nodes and a record limit of 1 MiB. Budget exhaustion is unresolved and is not invariance.

The checker must reconstruct rank-dependent pair contributions from the trusted case, retaining effects of passages shared at unequal ranks. Changing ranks, metric identity, scale, gains, endpoint, input digest or coefficient-table binding must invalidate an incompatible record. The old flat checker remains unchanged and is not advertised as supporting weighted scores.

## Independent reference and recorded endpoints

Run independent direct enumeration for domains of at most `2^28` completions per case. Domains above that limit are unresolved by this reference. A compiled integer enumerator may be used for practical runtime, after comparison with a separately written Python scorer on synthetic cases. Do not use the producer's rows as the direct-scoring oracle. Record executable and source hashes, compiler flags and completion counts.

For each metric, case and endpoint, record total completions, number with disagreement, existence of disagreement, all-zero disagreement, all-three disagreement, change missed by zero, change missed by both constant points and change despite equal marginal attainable output sets. Maintain joint outcomes so marginal equality can be distinguished from pointwise agreement. Counts over completions are combinatorial counts without a probability model.

Record strict membership changes only when both profiles have positive position-three versus position-four margins. Strict prefix changes require all three adjacent margins positive in both full orders. Do not conflate a non-strict illustrative witness with another strict witness from the same case.

Report all proof outcomes including unresolved cases. Cross-check accepted proof verdicts against exact enumeration wherever complete enumeration is available. Record witness checks and rejected malformed records independently. A passing producer/checker agreement alone is not a fully independent result.

## Sensitivity and limitations

Compare per-case outcomes at the three fixed scales. Report disagreements, ties and small score margins rather than suppressing them. Agreement among scales is empirical sensitivity evidence for those discrete definitions, not proof of equality with real-valued DCG.

For real-valued score F and integer total Q at depth D=10, exact downward quantisation gives `0 <= F-Q/S < D/S`. A conservative pair-margin discrepancy bound is `2D/S`. A strictly positive normalised quantised margin larger than this bound keeps its sign under the real-valued score; equivalently a raw integer margin greater than `2D` suffices. Apply any such statement only to the concrete margin proved or checked, not automatically to all completions.

No new speed hypothesis is tested here. Timings are execution diagnostics unless a separate matched protocol is declared before measurement. The original DL21 prespecified latency criterion and its result are retained. No budget savings or optimal acquisition policy follow from existential pivotality.

## Completion and reporting

Reproduce the existing unweighted DL19–DL22, synthetic, SMT, SAT/DRAT and handoff acceptance counts with unchanged S1 separately. Record environment/version mismatches, inaccessible sources and failed counts explicitly. Keep original and new timing measurements distinguishable.

The reference audit verifies each of the 20 current scientific entries using primary-source metadata and claim support. Inaccessible full text must be labelled. A resolving DOI alone does not demonstrate that a claim is supported.
