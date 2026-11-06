# Verification

## Requirements and entry point

Python 3.11 or later is required. The scripts use only the standard library; the main verification route needs no downloads or installed packages.

From the extracted package directory, run:

```sh
python verify_all.py
```

On systems where Python is installed as `python3`, use that command instead. The checker first validates [MANIFEST.json](../MANIFEST.json), including file membership and SHA-256 digests. It then runs the four routes below in a disposable copy. Inputs and retained outputs remain unchanged. The manifest checks integrity against the supplied inventory; it is not an independent signature or timestamp.

| Route | Checks performed |
| --- | --- |
| Retained projections, `verify.py` | Recalculates 96 B1 case-by-semantics action references, checks 288 matched pairs within the 800 retained runs, recounts 2,960 retained historical outcomes, enumerates the 150 worlds of worked case 0145 and checks EPA/EPSS aggregate arithmetic. |
| Car Evaluation, `h11/verify_h11.py` | Reconstructs 128 case tables from the included CSV with SQLite and exact Fraction arithmetic; checks 1,024 claims, 6,144 observations and 24 arm/endpoint reports and identity lists. |
| Original Wine transfer, `wine/scripts/verify_transfer_bank.py` | Reconstructs all 36 cases, 432 exact score checks and 108 target-specific answers; checks source/protocol/partition bindings and duplicate counts; rejects 16 altered-input probes. |
| Exploratory Wine sensitivity, `wine_sensitivity/verify_sensitivity.py` | Reconstructs four arms with 36 candidates each, compares 144 classifications, 72 block-ranking pairs and 432 group count/score payloads, each with two scores, and reproduces the retained main result byte for byte. |

The 432 group payloads in the sensitivity route and the 432 score checks in the original Wine route have different denominators.

## Retained projections

The B1 action references are recalculated from the supplied synthetic models. Ancillary outcomes and witness counts are recounted from projected adjudication fields. Historical agreement outside worked case 0145 is checked against retained reference flags and values. The package omits the original historical engine, full historical inputs and individual adjudication payloads.

Runtime and allocation statistics are recalculated from recorded values. This does not measure fresh execution costs. Reproduction of the original implementation, budgeted H11 checkers and their original tests requires their separate implementation archive.

## Optional EPA and EPSS source-level checks

The default route checks retained aggregates. It does not download the original EPA or EPSS source exports. Their exact URLs, expected paths and byte digests are recorded in [upstream_inputs.json](../data/upstream_inputs.json). With the specified files available locally, the original checker accepts:

```sh
python verify.py --epa-zip /path/to/daily_88101_2023.zip --epss-data /path/to/epss-exports
```

The EPA route reconstructs eligibility, the category-transition matrix and the AQI-above-100 trigger. The EPSS route reconstructs the 8 June snapshot's two grids at the 10% reference threshold and the 14-CVE correction check at the 50% reference threshold, and checks retained trend-export digests. The full panel diagnostics and original 24- and 20-grid cross-checks remain in the study archive.

The secondary exports are from [EPSS-Compare](https://github.com/jgamblin/EPSS-Compare). The [FIRST EPSS Special Interest Group](https://www.first.org/epss/faq) maintains EPSS and Empirical Security generates the scores.

## Historical freezes and current documents

The H11 [freeze record](../h11/study/FREEZE.json) identifies 41 original files. Five included frozen JSON files can still be checked byte for byte. The 34 excluded implementation and vendor files and two original text documents are enumerated in [PROJECTION_MANIFEST.json](../h11/PROJECTION_MANIFEST.json). The current Markdown protocol and implementation specification are presentation revisions with their own hashes; the checker reports them separately. They are not represented as the original frozen bytes. The original freeze and acquisition receipt remain unchanged.

The Wine computational protocols, plans, acquisition receipts and their historical hashes remain unchanged. They document local chronology, rather than public preregistration or an independently certified timestamp. Historical execution receipts identify the scripts used at the time; [REVISION_PROVENANCE.json](../REVISION_PROVENANCE.json) identifies the scripts revised in this distribution. A fresh run does not overwrite the historical receipts.

## Scope of assurance

The separate reconstructions use different aggregation and ranking implementations within the project. Their agreement is internal validation. It does not establish formal software correctness, external institutional replication, human efficacy or organisational benefit. The main results and adverse comparisons are retained in full.
