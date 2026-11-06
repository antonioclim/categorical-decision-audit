# H11 implementation specification

**Reader edition:** M13-repository-r1

This reader edition formats the development interface and corrects the omitted “Do not” before the prohibition on trusting truth or mutation labels. `PROJECTION_MANIFEST.json` binds this edition separately from the original file identified in the historical freeze.

All Python code uses the standard library. New code provides computational validation and does not change the manuscript's mathematical results.

## Problem object

| Field | Required value |
| --- | --- |
| `id` | Non-empty string |
| `source` | Object with `sha256` containing 64 lowercase hexadecimal characters and a non-empty `label` |
| `states` | `["unacc", "acc", "good", "vgood"]` |
| `groups` | Ordered unique strings, at least two |
| `counts` | `{group: {state: non-negative integer}}`, with positive row totals |
| `profiles` | `adequate`, `good_or_better` and `ordinal`, each mapping every state to a rational string |
| `pair` | Two distinct profile names |
| `rule` | One of the two rule objects below |

```json
{"kind": "top_k", "k": 2, "semantics": "ordered_prefix"}
```

For top-*k*, require an integer satisfying `0 < k < n`. The permitted semantics are `selected_set` and `ordered_prefix`.

```json
{"kind": "threshold", "cutoff": "1/2", "semantics": "selected_set"}
```

All rankings are descending and use exact rational comparisons. Ties use the order in `groups`. Thresholds include equality. A `selected_set` is stored in group order, while an `ordered_prefix` is stored in ranking order. Each group score is its weighted count divided by its row total.

## Claim object

| Field | Required value |
| --- | --- |
| `id` | Non-empty string |
| `case_id` | The problem's `id` |
| `bindings` | `problem_sha256`, `rule_sha256`, `profiles_sha256` and `source_sha256` |
| `verdict` | `EQUIVALENT` or `NONEQUIVALENT` |
| `actions` | Each profile name in `pair` mapped to an ordered array of group names |

The verdict concerns equality of the two supplied complete actions. For sets, canonical storage in group order is compulsory and equality is assessed as sets.

Scientific bindings use SHA-256 of this UTF-8 serialisation:

```python
json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
```

`source_sha256` equals `source.sha256`. `problem_sha256` binds the entire problem; `profiles_sha256` binds `profiles`.

## Verifier interface

Both verifier modules export:

```text
verify(problem, claim, budget) -> dict
```

| Return field | Meaning |
| --- | --- |
| `status` | `ACCEPT`, `REJECT` or `ABSTAIN` |
| `reason` | Stable descriptive token |
| `work_units` | Integer no greater than `budget` |
| `strategy` | Descriptive algorithm name |

Reject malformed schemas, boolean integers, duplicate groups, unsupported fields or rules, impossible or empty data, mismatched bindings and incomplete actions. Weights must be rational strings; JSON floats are not permitted. Claim validation must reject exponent, whitespace and underscore syntax. Both modules apply this ASCII full-match grammar, with the value in `[0, 1]`:

```regex
[+-]?(?:[0-9]+(?:/[0-9]+|\.[0-9]*)?|\.[0-9]+)
```

**Do not trust truth labels or mutation labels.** They are not passed to `verify()`.

A score-term evaluation costs one unit per count-times-weight term, including zero terms. Comparing two rational scores, or a score to a threshold, costs one unit. Budget exhaustion returns `ABSTAIN`. Binding and schema checks are outside this work cap; wall time includes them. Report these separately because work units do not measure complete runtime cost.

## Comparator requirements

The contract verifier directly validates candidate selected actions with exact score and tie comparisons. It may instead sort when that provides a cheaper competent check.

The replay verifier independently implements adaptive replay or candidate validation. It may exploit all supplied candidate evidence, binding checks and early exits. It must not deliberately ignore witnesses or access oracle labels. Neither verifier imports calculation helpers from the other. Hash and validation logic may be independently duplicated.

Both receive identical deep-equivalent problem and claim objects and the same budget. For valid actions, confirm the verdict against exact action equality.

The runner and oracle compute unbounded actions independently of both verifiers. They create expected-validity labels and retain per-claim identities, source composition and results at common claim quotas and budgets.

## Development and evaluation sources

The development source consists of synthetic full factorial rows matching the published schema, with deterministic SHA-256 label assignment. These must not be represented as UCI observations.

The primary source is the UCI Car Evaluation data file, which was excluded from H1 row inspection. Only source metadata and schema were read in H1. The dataset is model-derived and fully observed, not operational ground truth. New temporal EPSS data are not required for H11.

Bohanec, M. (1988). *Car Evaluation* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5JP48. Licence: CC BY 4.0.
