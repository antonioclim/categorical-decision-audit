# Wine duplicate-content sensitivity

This directory contains the exploratory sensitivity analysis included in M13. It examines duplicate content and partition assignment after the original Wine outcomes were known. The [scientific report](WINE_SENSITIVITY_REPORT.md) gives the complete results and their interpretation.

## Reproduce the analysis

Use Python 3.11 or later and the standard library. From this directory, run:

```sh
python verify_sensitivity.py
```

The verifier works in a disposable copy. It checks the fixed exploratory plan and raw CSV hashes, runs both separate reconstructions, compares every candidate classification and ranking and reproduces the retained main result byte for byte. Supplied inputs and outcomes remain unchanged.

To regenerate derived files deliberately in this directory:

```sh
python scripts/run_sensitivity.py
python independent/reconstruct_independent.py
python scripts/compare_reconstructions.py
```

Direct regeneration updates outputs and execution receipts. Each reconstruction accepts `--source PATH`; its default is the included `inputs` directory. That directory supplies both raw CSVs, the acquisition receipt, the original candidate ledger, the case-level group payloads and the original summary.

## Evidence files

| File | Content |
| --- | --- |
| [EXPLORATORY_PLAN.json](EXPLORATORY_PLAN.json) | Fixed four-arm plan, identity definition, endpoints and complete-retention policy |
| [SUMMARY.json](SUMMARY.json) | Arm totals and the outcomes corresponding to the four original strict examples |
| [SENSITIVITY_RESULTS.json](SENSITIVITY_RESULTS.json) | Complete exact results for every arm and candidate |
| [CANDIDATE_LEDGER.csv](CANDIDATE_LEDGER.csv) | All 144 arm/candidate entries |
| [GROUP_SCORE_LEDGER.csv](GROUP_SCORE_LEDGER.csv) | All 432 arm/block/group rows, each with two exact scores |
| [RECORD_ASSIGNMENTS.json](RECORD_ASSIGNMENTS.json) | Original and content-based assignments |
| [DUPLICATE_IDENTITY_RECONCILIATION.json](DUPLICATE_IDENTITY_RECONCILIATION.json) | Reconciliation of colour-free and colour-aware duplicate counts |
| [independent/INDEPENDENT_CHECK.md](independent/INDEPENDENT_CHECK.md) | Separate reconstruction method and historical execution scope |
| [INDEPENDENT_COMPARISON_QA.json](INDEPENDENT_COMPARISON_QA.json) | Completed comparison of both reconstructions |

The main calculation uses Fraction and Counter. The separate implementation uses Decimal, SQLite and integer cross-products without importing the main aggregation or ranking code. Agreement provides internal implementation validation. The 432 group payloads each contain two scores; this denominator differs from the 432 score checks in the original Wine verification.

Only two of the four original strict examples remain strict after first-occurrence selection within original blocks, although every arm contains strict examples. Both top-k rules reuse each block. Content-hash arms create different cohorts, and their content key includes the quality label. Neither independent samples nor outcome-blind partitioning are established.

## Attribution and licence

The files `winequality-red.csv`, `winequality-white.csv` and `winequality.names` retain the UCI Wine Quality source records and documentation.

Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009). *Wine Quality* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C56S3T

Source article: Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009). Modeling wine preferences by data mining from physicochemical properties. *Decision Support Systems, 47*(4), 547–553. https://doi.org/10.1016/j.dss.2009.05.016

The source dataset and identified adaptations retain [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). Adaptations add content keys, partitions, exact summaries, candidate classes and exploratory interpretation. Original source records have not been corrected or overwritten. Package-level terms for other files do not restrict these source rights.
