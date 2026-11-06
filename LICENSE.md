# Licence scope

## Files and applicable licences

Copyright (c) 2026 Antonio Clim applies to the author-controlled contributions in this distribution. Third-party authors retain their rights in the identified source materials.

| Material | Applicable terms |
| --- | --- |
| The nine Python verification and reconstruction scripts (`*.py`) included in this package | [BSD 3-Clause](LICENSES/BSD-3-Clause.md) |
| Author-controlled documentation, protocols, annotations, manifests and data records | [Creative Commons Attribution 4.0 International](LICENSES/CC-BY-4.0.md) |
| UCI Car Evaluation and Wine Quality source files and identified source-derived adaptations | CC BY 4.0 with the original dataset attribution |

These are component-specific licences. They do not offer a choice of either licence for every file. The licence documents themselves retain their original legal text.

## Dataset attribution and adaptations

Car Evaluation source files are `h11/data/heldout/car.data` and `h11/data/heldout/car_evaluation.zip`. Source-derived contingency tables, analytical scores and class compositions are retained in `h11/results/heldout/`.

Wine Quality source files are the ZIP, CSVs and source documentation in `wine/transfer/`, with copies in `wine_sensitivity/inputs/`. Identified adaptations include grouped counts, exact scores, partition and record-assignment maps, candidate and answer ledgers, duplicate-key audits and sensitivity results.

The source bytes remain unchanged. Adaptations apply research-defined codings, thresholds, grouping, partitioning, exact scores, claim annotations and exploratory comparisons. Original records have not been silently corrected. No source-author or repository endorsement is implied.

Retain the citations and change descriptions in [SOURCE_ATTRIBUTION.md](SOURCE_ATTRIBUTION.md), [h11/SOURCE_ATTRIBUTION.json](h11/SOURCE_ATTRIBUTION.json) and [wine/transfer/TRANSFER_PROVENANCE.json](wine/transfer/TRANSFER_PROVENANCE.json). The canonical CC BY 4.0 terms are available at <https://creativecommons.org/licenses/by/4.0/>.

## Distribution scope

This licence scope supersedes the restricted editorial terms of the earlier review distributions for the files included here. References to earlier private evaluations, excluded source files or historical archive names identify provenance; they do not restrict reuse of the present author-controlled files under the licences above.

The original evaluated implementation, vendor modules, wheel, full original tests, complete study archives, private reproduction files and participant-study materials are excluded. No rights to those absent materials are granted by this package.
