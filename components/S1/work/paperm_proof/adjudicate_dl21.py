"""Direct Cartesian adjudication for all eligible DL21 inputs (at most five unknowns)."""

import argparse
from collections import Counter
from hashlib import sha256
from itertools import product
import json
from pathlib import Path


def outcomes(case, values):
    grades = case["known"] | dict(zip(case["unknown"], values))
    runs = sorted(case["runs"])
    labels = {name: [grades[p] for p in case["runs"][name]] for name in runs}
    scores = [
        {name: sum(g >= 2 for g in group) for name, group in labels.items()},
        {name: sum(group) for name, group in labels.items()},
    ]
    ordered = [sorted(runs, key=lambda name: (-totals[name], name)) for totals in scores]
    set_changed = ordered[0][3] != ordered[1][3]
    prefix_changed = ordered[0][:3] != ordered[1][:3]
    gaps = [[totals[x] - totals[y] for x, y in zip(order, order[1:])]
            for order, totals in zip(ordered, scores)]
    return {
        "set": set_changed, "prefix": prefix_changed,
        "strict_set": set_changed and all(gap[2] > 0 for gap in gaps),
        "strict_prefix": prefix_changed and all(min(gap) > 0 for gap in gaps),
        "order_only": prefix_changed and not set_changed,
    }, scores


def run(args):
    source = args.cases.read_bytes()
    assert sha256(source).hexdigest() == args.cases_sha256
    cases = json.loads(source)
    restored = json.loads(args.masked_truth.read_text())
    case_lookup = {case["id"]: case for case in cases}
    evidence = {}
    total = 0
    masked_checks = 0
    for case in cases:
        unknown = case["unknown"]
        assert len(unknown) <= 5
        counts = Counter()
        for grades in product(range(4), repeat=len(unknown)):
            row, _ = outcomes(case, grades)
            counts.update({key: int(value) for key, value in row.items()})
        total += 4 ** len(unknown)
        if case["stratum"] == "masked":
            labels = restored[case["id"]]
            base = case_lookup[f'observed:{case["qid"]}']
            assert outcomes(case, [labels[p] for p in unknown]) == outcomes(base, ())
            masked_checks += 1
        evidence[case["id"]] = {
            "stratum": case["stratum"], "qid": case["qid"], "worlds": 4 ** len(unknown),
            "changing_worlds": counts,
            "endpoints": {key: {"status": "changed" if count else "invariant"}
                          for key, count in counts.items()},
        }
    assert masked_checks == len(restored)
    args.output.write_text(json.dumps({"cases": len(cases), "worlds": total, "masked_checks": masked_checks,
                                       "by_case": evidence}, indent=2, sort_keys=True) + "\n")
    print(f"{len(cases)} cases, {total} worlds, {masked_checks} matched original masks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cases", "masked_truth", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--cases-sha256", required=True)
    run(parser.parse_args())
