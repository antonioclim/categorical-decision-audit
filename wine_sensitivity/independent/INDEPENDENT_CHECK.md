# Separate reconstruction of the Wine sensitivity analysis

**Historical reconstruction report:** 6 November 2026.

This implementation read the frozen plan and original CSVs without importing or inspecting the main sensitivity aggregation/ranking implementation. It uses Decimal comparisons for grouping, SQLite for aggregation and integer cross-products for ranking. It reconstructs all four specified arms and all 36 candidates per arm. Every candidate was eligible.

The source SHA-256 values matched the retained acquisition receipt and remained unchanged after execution. The plan hash was checked explicitly.

## Reconstructed results

| Arm | Same order | Changed membership | Order-only | Strict order-only | Blocks with a strict case | Rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A0: original | 24 | 7 | 5 | 4 | 3 | 6,497 |
| A1: unique contents in original blocks | 22 | 10 | 4 | 4 | 4 | 5,320 |
| A2: all rows in content-hash blocks | 19 | 10 | 7 | 7 | 6 | 6,497 |
| A3: unique contents in content-hash blocks | 17 | 10 | 9 | 9 | 7 | 5,320 |

A0 contains 5,320 unique colour/content identities. Only W01-K2 and W11-K2 of the four original strict cases remain strict under A1. W03-K2 becomes identical order; W11-K3 changes membership. A2/A3 blocks contain different records from equally numbered A0/A1 blocks, so new strict cases are not matched replications.

## Identity and comparison scope

The sensitivity plan includes source colour in content identity. It produces 951 repeated-content groups crossing the original blocks. The original audit omits colour and reports 952. Both counts describe their declared identity rules. A0 classifications agree with the original totals and all four strict case identifiers.

The original separate-reconstruction report preceded the comparison with the main implementation. That comparison is now recorded in [INDEPENDENT_COMPARISON_QA.json](../INDEPENDENT_COMPARISON_QA.json): 144 candidate classifications, 72 block-ranking pairs and 432 group count/score payloads agree. [INDEPENDENT_RESULTS.json](INDEPENDENT_RESULTS.json) retains the reconstruction's exact outputs and execution metadata.

This is internal validation by a separate implementation. It is not external replication, a proof of software correctness or evidence of independent biological samples. The analysis remains exploratory because the original Wine outcomes were known before its plan was fixed.

## Execution

From `wine_sensitivity/`, run:

```sh
python independent/reconstruct_independent.py
```

Use `--source PATH` to select another directory containing the exact retained inputs. The default is the sibling `inputs/` directory. Outputs are written to `independent/`. No network access or third-party package is required. For inspection without changing retained outputs, use the [directory-level verifier](../README_REPLAY_EN.md#reproduce-the-analysis).
