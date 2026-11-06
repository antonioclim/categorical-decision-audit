# H11 computational transport protocol

**Study:** Different Definitions, Same Decision? An Executable Audit for Categorical Decision Support  
**Protocol:** H11-v1, developed and frozen locally on 5 November 2026  
**Reader edition:** M13-repository-r1

This reader edition formats the study protocol and omits editorial workflow material. The historical freeze identifies the original files; this edition is bound separately in `PROJECTION_MANIFEST.json` and is not presented as the original frozen byte sequence.

## 1. Question and claim boundary

Can the unchanged aggregate decision-audit contract, with a source-specific encoding fixed before reading the new source rows, be checked reliably under common offered-claim quotas and common computation caps? Report correct conclusive yield together with exactly which claims are accepted, rejected or unresolved. Compare a certificate-oriented verifier with a separately implemented competent adaptive verifier receiving the same problem, rule, candidate evidence and computation cap. Retain equality, loss and advantage alike.

This is controlled computational transport. It does not measure analyst effectiveness, deployment outcomes, predictive accuracy or social benefit. It does not introduce mathematical propositions or alter the author's proofs.

## 2. Excluded source and chronology

Bohanec, M. (1988). *Car Evaluation* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5JP48

The [source metadata](https://archive.ics.uci.edu/dataset/19/car+evaluation) were inspected on 5 November 2026. The dataset is licensed under CC BY 4.0. It derives from a hierarchical decision model and is not a sample of observed purchases, safety outcomes or organisational decisions.

Only landing-page metadata and schema were read in H1. The raw labels and rows were not downloaded, read or used for tuning in H1. Public familiarity and possible model pretraining are not controlled: this is not formal blinding. Source exclusion means exclusion from the inspected project development inputs, not exclusion from world knowledge. The source was chosen for its published categorical schema, distinct provenance and direct relation to decision modelling, not observed favourable outcomes. No other new source will be substituted after results.

The local freeze binds the original protocol, case list, scripts and tests before H2 acquisition. It is an internal chronology record, not an externally timestamped preregistration. Preserve any post-freeze correction as an explicit amendment; do not silently replace code, budgets, exclusions, encodings or endpoints.

## 3. Eligibility and exact encoding

Read all 1,728 configurations with six categorical features and one class. Require exactly one instance of every schema feature combination, valid classes, no duplicates and no missing values. Otherwise stop with an acquisition or schema failure, retain the bytes and do not drop records to obtain a convenient cohort. The published feature category order, also used as the tie order, is recorded in the original `experiment.py`.

The four classes are `unacc`, `acc`, `good` and `vgood`. The fixed profiles assign these weights:

| Profile | `unacc` | `acc` | `good` | `vgood` |
| --- | ---: | ---: | ---: | ---: |
| `adequate` | 0 | 1 | 1 | 1 |
| `good_or_better` | 0 | 0 | 1 | 1 |
| `ordinal` | 0 | 1/3 | 2/3 | 1 |

These are stipulated, substantively different criteria. The ordinal spacing is an analytical convention, not a source-validated utility scale. Their agreement does not establish interchangeability; disagreement is not a data error.

For each context fixing exactly one feature to one category, group records by each unordered pair of the remaining features. Count the four classes per group. All positive row denominators are fixed. Scores are exact weighted proportions. These are fully observed aggregate, effectively single-world cases. They cannot validate uncertain-pool certification or large-feasible-set scalability.

Cross each of the three profile pairs with top-*k*, where *k* = 1, 2 or 4, under selected-set and ordered-prefix semantics, plus inclusive thresholds 1/4, 1/2 and 3/4. Rank descending and resolve score ties by the declared Cartesian group order. No full-cohort *k* is included. Thresholds are fixed capacities only where resulting group counts match; do not present a threshold as a common-quota comparison when selected group counts differ.

Enumerate 5,670 schema-defined base specifications. Select 128 by SHA-256 order with namespace `PaperM-H11-v1`, using their feature, profile and rule identifiers only. The selected case list is frozen in `CASE_SELECTION.json` before source acquisition. No class count, agreement, margin, cost or yield enters case selection. Overlapping slices and profile pairs are dependent: no independent-sample confidence interval, significance test, population prevalence estimate or pseudo-replication claim is supported.

## 4. Claims, controlled faults and comparator fairness

For each base case create one clean exact claim and seven planted variants:

1. An internally coherent false equivalence verdict.
2. A wrong but admissible action.
3. A missing action.
4. A stale problem binding.
5. A stale rule binding.
6. A stale profiles binding.
7. A stale source binding.

This yields 1,024 offered claims. The four binding-fault classes are engineering coverage, not four independent scientific phenomena. The false-verdict variant also changes an action so that the claimed verdict remains internally consistent with the supplied actions. The wrong-action variant keeps the true verdict but changes evidence while preserving that internal consistency. Neither can be rejected merely by comparing the two supplied action arrays. Report every fault class separately, and the clean, false-verdict and wrong-action subset separately from provenance faults. Fault frequencies are not real-world rates.

Each claim binds the full problem, rule, profiles and source bytes. Both arms may check those bindings, exploit all supplied actions and witnesses, take competent early exits and choose efficient exact verification strategies. Neither gets expected validity, mutation class or oracle result. They share no imported calculation helper. They are separately coded within the same project, not external institutional replications. A common independent exact oracle constructs the benchmark truth; targeted hand-computed and differential tests check it.

An additional bridge runs the unchanged aggregate engine core retained in F2 (`0.6.1rc1`) on every base case, comparing actions and verdicts and checking that different estimands are not collapsed when actions agree. Exact source hashes are retained. This checks the original aggregate core, not the full DSS interface, uncertain-pool solver or a new released software version. Both compared budgeted verification modules are new validation code, not substitutes for that engine. Binding a source digest does not independently prove that a contingency table was faithfully extracted; the retained adapter, raw bytes, schema checks and separate table-consistency tests provide that transformation evidence.

The fixed output is `ACCEPT` when the claim and evidence are validated, `REJECT` when an invalid claim or invalid evidence is demonstrated, or `ABSTAIN` when the cap prevents resolution. A mathematically true statement with an invalid binding or invalid evidence is still an invalid audit claim. Report acceptance of mathematically false statements separately from acceptance of invalid evidence for mathematically true statements.

## 5. Budgets, common quotas and retained evidence

Computation caps per claim and arm are 32, 128 and 512 units; the primary cap is 128. One evaluated count-times-weight score term costs one unit, including zero terms; one rational score-to-score or score-to-threshold comparison costs one unit. Other schema, hash and control work is outside this cap. Units therefore constitute an explicit limited resource model, not total computational cost. Wall time includes the complete call and is descriptive; one call is not a robust runtime benchmark. Alternate arm order deterministically. The oracle is unbounded and outside both arm caps.

Common offered-claim quotas are prefixes of 128, 256, 512 and 1,024 in fixed SHA-256 claim-ID order. Both arms see the same identities in the same order. The primary endpoint is all 1,024 claims at cap 128. Do not select a favourable budget or prefix afterwards. For each endpoint retain numerators, denominators, exact rational yields, accepted, rejected and abstained identity lists, per-fault composition and between-arm identity differences. Do not delete abstentions through complete-case analysis.

**Correct conclusive yield** = (valid `ACCEPT` + invalid `REJECT`) / offered claims.

Also report valid acceptance yield, false rejection, invalid acceptance and mathematical false acceptance. A benefit claim requires zero invalid acceptance and false rejection on retained cases, a favourable primary difference and retained case-composition evidence. This is a descriptive finite-bank result, not a general guarantee. Report a zero or negative primary difference.

As a secondary diagnostic, retain selected group identities, number of underlying rows, full class composition and good or very-good share for each source case. For top-*k* the group quota is common; also report represented-row counts. This share is computed from the same classes used in the profiles. It is endogenous descriptive composition, not independent outcome yield, accuracy or utility. Retain both set membership changes and ordered-prefix differences.

## 6. Development, failure handling and reporting

H1 uses a full factorial fixture explicitly labelled as synthetic, with labels determined by a fixed hash of feature values. No UCI labels are imitated or reconstructed. Test exact arithmetic, ties, malformed inputs, stale bindings, all planted faults, budget exhaustion, verifier-to-oracle agreement and reproduction from a clean extraction. Repair development defects before freezing and retain the development test report.

H2 checks the freeze, acquires the UCI bytes, records the receipt and hashes, and executes unchanged code. Preserve all outcomes. Acquisition failure, verifier discrepancy or failed integrity checks block confirmatory interpretation; diagnose them openly. Any source-aware repair is amended and exploratory, not silently confirmatory.

