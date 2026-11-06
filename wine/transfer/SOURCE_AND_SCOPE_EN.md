# Wine Quality transfer evaluation

The evaluation contains every one of the 36 cases specified before raw data acquisition: 18 deterministic record partitions, each examined with top-k values of 2 and 3. All cases were eligible and retained. Selection did not depend on obtaining a particular disagreement.

The source comprises 1,599 red and 4,898 white wine records with physicochemical measurements and sensory quality labels. The two research codings score the proportions with quality at least 6 and at least 7. They represent different estimands. The grouping and selection rules define hypothetical analytical tasks.

## Specification and provenance

The [pre-acquisition protocol](PREACQUISITION_PROTOCOL.json) fixes the source, codings, grouping, partition rule, eligibility conditions and complete candidate retention. Its SHA-256 is:

```text
799e007b5f945c9ff33117e2c548ad59c65fbfcd8f3c24d4a22d91b177bb5435
```

Alcohol bands are below 10, from 10 to below 11 and at least 11. The pH bands are below 3.2 and at least 3.2. These cut points were fixed before raw acquisition as research conventions; they are neither safety standards nor thresholds fitted to these outcomes.

An [initial specification](PREACQUISITION_PROTOCOL_v1_BEFORE_STEERING.json) was amended before acquisition to include both k values for each partition and a compact three-state representation. Both versions remain in the evidence record. The [acquisition-order check](ACQUISITION_ORDER_CHECK.json) reconciles local protocol and acquisition times. This records the project's chronology; it provides neither public preregistration nor an independently certified timestamp.

The directory retains source bytes, acquisition hashes, every candidate disposition, record assignments and the full reference answers in [private_transfer_key.json](private_transfer_key.json). The filename distinguishes that answer ledger from the case descriptions; it does not indicate omitted answers.

## Complete results

| Outcome | Cases |
| --- | ---: |
| Identical ordered selection | 24 |
| Changed membership | 7 |
| Changed order with the same membership | 5 |
| Total | 36 |

Four order-only cases have neither selected-score nor selection-boundary ties under either coding. They arise from three partitions: blocks 1, 3 and 11. The two cases in block 11 reuse the same records. All five order-only cases come from four blocks.

Across the 72 membership and priority checks, 19 change the required output and 53 preserve it. A further 36 capacity controls preserve the selected count by construction, giving 108 case-target checks in total. The complete classifications and exact scores appear in [ALL_CANDIDATES.json](ALL_CANDIDATES.json), [TRANSFER_SUMMARY.json](TRANSFER_SUMMARY.json) and the reference answer ledger.

## Duplicate content and dependence

Record identifiers are disjoint across the 18 partitions, while both k values reuse each partition. The original duplicate audit uses all CSV field strings without a source-colour field. It finds 993 repeated-content groups, of which 952 cross partitions and contain 2,090 records. No partition was changed after these duplicates were observed.

Identical field strings do not establish that records describe the same physical wine. Conversely, distinct row identifiers do not establish independent wines or source replications: wine-sample and batch identities are unavailable. The [exploratory sensitivity analysis](../../wine_sensitivity/WINE_SENSITIVITY_REPORT.md) examines the consequences of content deduplication and content-based partitioning, including the difference between colour-free and colour-aware identities.

## Verification

The builder uses exact rational arithmetic. A separate verifier reconstructs raw inputs with Decimal comparisons, SQLite counts and integer cross-multiplication ranks, without importing the builder or the decision kernel. It checks all 36 candidates, 432 exact scores and 108 target-specific answers. All 16 retained altered-input probes must be rejected.

These are internal implementation checks. They do not re-execute the excluded original kernel, establish external replication or verify mathematical proofs. The evaluation supplies no human-review outcome or organisational utility estimate. The fixed bank was inspected during its original evaluation and cannot subsequently serve as an unseen evaluation source without an explicit change of study design.

## Attribution and licence

Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009). *Wine Quality* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C56S3T

The source dataset and identified adaptations retain [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Adaptations comprise the research-defined thresholds, groupings, partitions, exact summaries and candidate annotations. Source records remain unchanged. No source-author or repository endorsement is implied.

Source article: Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009). Modeling wine preferences by data mining from physicochemical properties. *Decision Support Systems, 47*(4), 547–553. https://doi.org/10.1016/j.dss.2009.05.016
