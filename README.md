# Different Definitions, Same Decision?

## Data and verification

**Antonio Clim** · **Version 1.0.0**

These records accompany *Different Definitions, Same Decision? An Executable Audit for Categorical Decision Support*. They make the reported examples, complete candidate outcomes and selected comparisons available for inspection. The manuscript is distributed separately.

The package contains constructed cases, a common-allocation example, EPA and EPSS summaries, the Car Evaluation comparison and the Wine Quality transfer and sensitivity analyses. Source records, exact scores, unsuccessful comparisons and exclusions are retained.

### Start here

| Purpose | Document |
| --- | --- |
| Execute the included checks and understand their scope | [Verification](docs/VERIFICATION.md) |
| Read the principal results and their denominators | [Results](docs/RESULTS.md) |
| Inspect the Car Evaluation design | [H11 protocol](h11/study/PROTOCOL.md) and [implementation specification](h11/study/IMPLEMENTATION_SPEC.md) |
| Inspect the Wine transfer | [Source and scope](wine/transfer/SOURCE_AND_SCOPE_EN.md) |
| Inspect the exploratory sensitivity | [Replay instructions](wine_sensitivity/README_REPLAY_EN.md) and [report](wine_sensitivity/WINE_SENSITIVITY_REPORT.md) |
| Identify sources and permitted uses | [Source attribution](SOURCE_ATTRIBUTION.md) and [licence scope](LICENSE.md) |
| Identify the changes in this distribution | [Revision history](CHANGELOG.md) |

### Verification

Use Python 3.11 or later. All included checks use the Python standard library and run without network access.

```sh
python verify_all.py
```

The command checks the file manifest, then verifies the retained projections and reconstructs the Car Evaluation and Wine analyses. Generated reports stay in temporary directories. A successful run ends with `1.0.0 verification PASS`.

### Reading the evidence

At the primary Car Evaluation cap, the contract checker resolves 997 of 1,024 claims correctly; the same-information comparator resolves 1,000. The comparison does not establish a conclusive-yield advantage. The original Wine bank retains all 36 candidates, including four strict order-only changes from three blocks. In the exploratory duplicate-content analysis, two of those four original cases remain strict after first-occurrence selection in their original blocks.

These are computational results under specified codings and selection rules. Verification of this package reconstructs the included evidence; it does not execute the separately retained original software or measure organisational or analyst outcomes. See [Verification](docs/VERIFICATION.md) for the exact boundaries.

### Licence and citation

Verification scripts are available under **BSD-3-Clause**. Documentation and author-controlled data records are available under **CC BY 4.0**; the identified UCI sources and adaptations retain their CC BY 4.0 attribution. [LICENSE.md](LICENSE.md) specifies the applicable file scopes.

Use [CITATION.cff](CITATION.cff) for the package identity and cite the original datasets listed in [SOURCE_ATTRIBUTION.md](SOURCE_ATTRIBUTION.md). The archive identifier is [doi:10.5281/zenodo.23971063](https://doi.org/10.5281/zenodo.23971063). Version 1.0.0 identifies this data and verification package, separately from the original evaluated software.
