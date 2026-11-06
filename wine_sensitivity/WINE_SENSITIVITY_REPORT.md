# Duplicate content and partition sensitivity in Wine Quality

**Analysis date:** 6 November 2026. **Status:** exploratory, after the original Wine outcomes were known.

Strict order-only changes occur in all four specified configurations. However, only two of the four original strict examples remain strict when repeated contents are represented by their first occurrence in the original blocks. Equal totals of strict cases in two arms therefore do not establish persistence of the same examples.

## Plan and identity definition

The [exploratory plan](EXPLORATORY_PLAN.json) was fixed and hashed before these sensitivity computations, after the original results and duplicate audit were known. Its SHA-256 is:

```text
07e1114322f57be40c7f5da397dd4a6d54324ac072080b840c5d17265e9b7d11
```

The analysis retains both codings, alcohol/pH thresholds, six groups, top-2/top-3 rules and deterministic tie order from the original protocol. A unique content identity comprises **source colour and all 12 CSV fields as their original strings**. There is no rounding, label transformation or merging across the red and white files. The representative is the first occurrence within its source-colour file.

Content-based blocks use a single SHA-256 rule with a fixed namespace. No alternative key or namespace was selected in response to sensitivity outcomes. Every arm reports all 36 candidates; all were eligible. The two k values reuse each block. Blocks in A2/A3 contain different records from equally numbered blocks in A0/A1.

The local plan digest records a fixed specification. It does not provide independent timestamping or retroactively preregister the original findings.

## Complete arm results

| Arm | Rows | Unique colour/content identities | Same order | Changed membership | Order-only | Strict order-only | Blocks with a strict case |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A0: all rows, original blocks | 6,497 | 5,320 | 24 | 7 | 5 | 4 | 3 |
| A1: first occurrences, representatives' original blocks | 5,320 | 5,320 | 22 | 10 | 4 | 4 | 4 |
| A2: all rows, content-hash blocks | 6,497 | 5,320 | 19 | 10 | 7 | 7 | 6 |
| A3: unique contents, content-hash blocks | 5,320 | 5,320 | 17 | 10 | 9 | 9 | 7 |

Strict order-only cases preserve membership while changing order and have neither selected-score nor selection-boundary ties under either coding.

A0 reproduces the original 36 candidate classifications and their group-score payloads. In A2, all records with the same colour/content identity enter the same block, while their multiplicities still contribute to scores. A3 also removes that multiplicity. These constructions alter observational weighting and cohort composition. They do not identify independent physical wines or establish that repeated records are source errors.

Strict cases are:

- **A1:** W01-K2, W02-K3, W09-K3 and W11-K2.
- **A2:** W01-K3, W07-K2, W08-K2, W08-K3, W09-K2, W15-K2 and W18-K2.
- **A3:** W01-K3, W05-K2, W05-K3, W07-K2, W08-K2, W08-K3, W15-K2, W16-K2 and W18-K2.

Every candidate, including those without a strict change, is retained in [CANDIDATE_LEDGER.csv](CANDIDATE_LEDGER.csv) and [SENSITIVITY_RESULTS.json](SENSITIVITY_RESULTS.json).

## Persistence of the four original strict examples

| Original strict case | A1 outcome | Strict order-only change persists? |
| --- | --- | --- |
| R2-W01-K2 | Order-only change | Yes |
| R2-W03-K2 | Identical ordered selection | No |
| R2-W11-K2 | Order-only change | Yes |
| R2-W11-K3 | Membership change | No |

For W03-K2, A1 selects G05, G06 under both codings. For W11-K3, the old coding selects G05, G06, G03 and the new coding selects G06, G05, G04. The latter example remains decision-sensitive, but its change is in membership rather than order alone. The strict-case total of four in both A0 and A1 conceals the loss of two original strict examples and the appearance of two different ones.

## Reconciliation of duplicate identities

The original audit grouped the 12 CSV field strings without source colour. This sensitivity includes colour in accordance with its fixed plan. Both definitions were reconstructed from the same unchanged source files.

| Identity definition | Unique contents | Repeated-content groups | Groups crossing original blocks | Rows in cross-block groups |
| --- | ---: | ---: | ---: | ---: |
| Original: CSV fields without colour | 5,318 | 993 | 952 | 2,090 |
| Sensitivity: colour and CSV fields | 5,320 | 992 | 951 | 2,087 |

Two field-identical groups span both colour files: `{red:837, red:838, white:2632}` and `{red:1132, white:3375}`. Their original content hashes and record-level blocks are retained in [DUPLICATE_IDENTITY_RECONCILIATION.json](DUPLICATE_IDENTITY_RECONCILIATION.json). This difference in identity definitions accounts for the count discrepancy; it is not an arithmetic correction to the original audit.

## Execution and verification

The main calculation uses CSV, Counter and Fraction. The separate reconstruction uses CSV, Decimal, SQLite and integer cross-products without importing the main aggregation or ranking implementation. The [comparison receipt](INDEPENDENT_COMPARISON_QA.json) records agreement on **144 candidate classifications, 72 block-ranking pairs and 432 group count/score payloads**. Each group payload contains two exact scores. This differs from the 432 score checks in the original Wine verification, which reuse group payloads across two k values.

The retained [execution receipt](EXECUTION_RECEIPT.json) binds the plan, scripts, result and raw source hashes. The supplied verifier runs both calculations in a temporary copy, compares their results and checks byte-identical reproduction of `SENSITIVITY_RESULTS.json`. Retained source bytes remain unchanged. The command does not rerun the original decision kernel, budgeted verifiers or historical timings.

## Interpretation

The existence of strict order-only changes persists across the three specified sensitivity arms, while the identity of the original examples is less stable. The content key includes the quality label, so content-based partitioning is not outcome-blind. Equally numbered blocks across different partition rules are not matched cohorts, and overlapping rules do not create independent replications.

These finite-bank results do not estimate prevalence in a population of organisations, wines or policies. They provide neither external replication nor human-review efficacy, organisational utility or a comparative advantage over the retained competent verifier. Reporting all arms and the attrition of original examples is necessary to assess the sensitivity honestly.

## Source

Cortez, P., Cerdeira, A., Almeida, F., Matos, T., & Reis, J. (2009). *Wine Quality* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C56S3T

The source and identified data-derived adaptations retain [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
