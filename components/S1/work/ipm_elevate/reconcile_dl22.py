"""Reconcile the DL22 follow-up with an uncompressed direct integer traversal."""

from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "paperm_revision"))
from exhaustive_counts import exhaustive


def read(path):
    return Path(path).read_bytes()


cases_path, results_path, output = sys.argv[1:4]
raw = read(cases_path)
reference = json.loads(read(results_path))
assert sha256(raw).hexdigest() == reference["input_sha256"]
started = perf_counter()
cases = json.loads(raw)
checked = {}
for case in cases:
    observed = exhaustive(case, 262_144)
    expected = reference["by_case"][case["id"]]
    assert expected["status"] == "exact"
    assert observed["total_worlds"] == expected["worlds"]
    for endpoint in ("set", "prefix"):
        target = expected["outcomes"]["3_" + endpoint]
        assert observed.get(endpoint, 0) == target["change_worlds"], (case["id"], endpoint)
        assert observed.get("strict_" + endpoint, 0) == target["strict_change_worlds"], (case["id"], endpoint)
    checked[case["id"]] = observed
summary = {"cases": len(checked), "worlds": sum(v["total_worlds"] for v in checked.values()),
           "matched_primary_and_strict_counts": 4 * len(checked), "numpy": numpy.__version__,
           "wall_seconds": perf_counter() - started}
Path(output).write_text(json.dumps({"summary": summary, "counts": checked}, sort_keys=True, indent=2) + "\n")
print(summary)
