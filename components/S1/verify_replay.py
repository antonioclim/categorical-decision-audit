"""Check deterministic replay summaries without comparing machine-specific times."""

import json
from pathlib import Path
import sys

results = Path(sys.argv[1])
expected = json.loads(Path("expected_checks.json").read_text())


def load(relative):
    return json.loads((results / relative).read_text())


for cohort, summary in expected["selection"].items():
    assert load(f"{cohort}.json")["summary"] == summary, cohort
for cohort, summary in expected["portable"].items():
    observed = load(f"{cohort}_portable/summary.json")["groups"]["all"]
    for key, value in summary.items():
        assert observed[key] == value, (cohort, key, observed[key], value)
for cohort, summary in expected["sat"].items():
    observed = load(f"sat_{cohort}/results.json")["summary"]
    for key, value in summary.items():
        assert observed[key] == value, (cohort, key, observed[key], value)
observed = load("dl22_direct.json")["summary"]
for key, value in expected["direct_dl22"].items():
    assert observed[key] == value, (key, observed[key], value)
mutations = load("dl21_mutations.json")
for key, value in expected["mutations"].items():
    assert mutations[key] == value, (key, mutations[key], value)
assert load("handoff/summary.json") == expected["handoff"]
print("Deterministic replay summaries match the manuscript evidence.")
