# Principal results

## Constructed cases and historical projections

The retained B1 models support 96 case-by-semantics action references. The 800 retained runs include 576 primary runs forming 288 matched pairs. The projections preserve completion status, primary outcomes, timings, allocation summaries and ancillary counts. The historical ledger retains 2,960 successor requests; the included checker recounts those retained records. Worked case 0145 is reconstructed by enumerating all 150 feasible worlds. These checks have the projection-level scope described in [Verification](VERIFICATION.md).

## Car Evaluation comparison

The source-excluded evaluation retains 128 cases, 1,024 offered claims and 6,144 observations. At the primary cap of 128, the contract checker reaches **997 correct conclusions**, compared with **1,000** for the same-information comparator. Their abstention totals are 27 and 24. Both accept the same 107 valid claims. No invalid acceptance or false rejection was observed.

At cap 512 both are complete. None of the retained quotas/caps gives the contract checker a conclusive-yield gain. The primary comparative-benefit criterion is therefore not met. All 24 arm/endpoint reports and their claim identities are included.

Among the 89 common-capacity top-k cases, 31 change membership and six change only order. The good/very-good shares reuse the encoded labels and provide descriptive composition, rather than independent outcome yield. The UCI source is model-derived and fully observed; cases overlap and the ordinal spacing is stipulated.

See [h11/results/heldout/](../h11/results/heldout/) for the case bank, observations, summaries and selection compositions.

## Original Wine Quality transfer

The locally specified candidate universe contains 36 comparisons from 18 deterministic partitions, each used with top-2 and top-3. All candidates are eligible and retained.

| Classification | Comparisons |
| --- | ---: |
| Identical ordered selection | 24 |
| Membership change | 7 |
| Order-only change | 5 |
| Strict order-only subset, without selected-score or boundary ties | 4 |

The four strict cases come from three underlying blocks. Across 108 case-target combinations, 19 membership/priority cells show a mismatch and 53 preserve the required output. The 36 capacity controls are preserved by construction.

The source contains 6,497 reported physicochemical and sensory records. Research-defined codings, groups and hypothetical selection rules are applied to those records. The codings represent different estimands. Disjoint row identifiers do not identify independent wines: under the original content-only key, 952 duplicate groups cross partitions and involve 2,090 rows.

See the [Wine source and scope](../wine/transfer/SOURCE_AND_SCOPE_EN.md) and [complete candidate ledger](../wine/transfer/ALL_CANDIDATES.json).

## Exploratory duplicate-content sensitivity

This analysis was planned after the original outcomes and duplicate audit were known. Each arm retains all 36 comparisons.

| Arm | Source rows | Identical order | Membership change | Order-only change | Strict subset |
| --- | ---: | ---: | ---: | ---: | ---: |
| A0: all rows, original blocks | 6,497 | 24 | 7 | 5 | 4 |
| A1: first occurrences, original blocks | 5,320 | 22 | 10 | 4 | 4 |
| A2: all rows, content-hash blocks | 6,497 | 19 | 10 | 7 | 7 |
| A3: unique contents, content-hash blocks | 5,320 | 17 | 10 | 9 | 9 |

Only W01-K2 and W11-K2 of the four original strict cases remain strict in A1. W03-K2 becomes identical order; W11-K3 changes membership. The equal strict-case totals in A0 and A1 do not mean that all four original examples persist.

The A2/A3 blocks contain different cohorts from the original blocks. Their content key includes source colour and the full row, including quality, so partitioning is not outcome-blind. With colour included, the source has 5,320 unique contents and 951 cross-block duplicate groups involving 2,087 rows. The original content-only key gives 5,318 unique contents and 952 groups involving 2,090 rows. Both definitions are reconciled in the retained evidence.

Deduplication changes observational weighting. It neither identifies independent physical samples nor establishes source errors. The arms and their reused top-k rules are dependent constructions. See the [complete sensitivity report](../wine_sensitivity/WINE_SENSITIVITY_REPORT.md), [candidate ledger](../wine_sensitivity/CANDIDATE_LEDGER.csv) and [exact results](../wine_sensitivity/SENSITIVITY_RESULTS.json).
