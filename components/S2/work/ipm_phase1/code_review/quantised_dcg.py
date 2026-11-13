"""Bounded exact audit of a declared, quantised logarithmic-discount metric.

The integer scores are exact for this metric. They are not real-valued DCG
or nDCG. No certificate for the original flat-score checker is produced.
Four named runs, ten distinct passages per run and top-three endpoints match
the current study. Lexically earlier run names win equal integer scores.
"""

from __future__ import annotations

import argparse
import hashlib
from itertools import product
import json
from pathlib import Path

SCALE = 1_000_000
METRIC = "quantised_log_discount_floor_gain_v1"
MAX_COMPLETIONS = 65_536
PROFILES = {"binary": (0, 0, 1, 1), "graded": (0, 1, 2, 3)}
# Indexed by rank minus one and gain, not by relevance grade. Every nonzero
# entry k is certified in test_quantised_dcg.py using the integer inequality
# (rank+1)**k <= 2**(SCALE*gain) < (rank+1)**(k+1).
GAIN_TABLE = (
    (0, 1_000_000, 2_000_000, 3_000_000),
    (0, 630_929, 1_261_859, 1_892_789),
    (0, 500_000, 1_000_000, 1_500_000),
    (0, 430_676, 861_353, 1_292_029),
    (0, 386_852, 773_705, 1_160_558),
    (0, 356_207, 712_414, 1_068_621),
    (0, 333_333, 666_666, 1_000_000),
    (0, 315_464, 630_929, 946_394),
    (0, 301_029, 602_059, 903_089),
    (0, 289_064, 578_129, 867_194),
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def name(value):
    return type(value) is str and bool(value)


def grade(value):
    return type(value) is int and 0 <= value <= 3


def validate_case(case):
    """Validate exactly the supported schema while retaining the rank order."""
    if type(case) is not dict or not name(case.get("id")):
        raise ValueError("A case needs a nonempty string id")
    runs, known, unknown = case.get("runs"), case.get("known"), case.get("unknown")
    if type(runs) is not dict or len(runs) != 4 or not all(map(name, runs)):
        raise ValueError("Exactly four named runs are required")
    for values in runs.values():
        if (type(values) is not list or len(values) != 10
                or not all(map(name, values)) or len(set(values)) != 10):
            raise ValueError("Each run must contain ten distinct nonempty passage ids")
    if type(known) is not dict or not all(name(p) and grade(g) for p, g in known.items()):
        raise ValueError("Known grades must be integers in 0..3, excluding booleans")
    if (type(unknown) is not list or not all(map(name, unknown))
            or len(set(unknown)) != len(unknown) or set(unknown).intersection(known)):
        raise ValueError("Unknown passages must be distinct and disjoint from known passages")
    union = set().union(*map(set, runs.values()))
    if set(unknown).union(known) != union:
        raise ValueError("Known and unknown ids must partition the run union exactly")
    return tuple(sorted(runs)), tuple(sorted(unknown))


def weight(profile, relevance_grade, rank):
    if profile not in PROFILES:
        raise ValueError("Profile must be binary or graded")
    if not grade(relevance_grade) or type(rank) is not int or not 1 <= rank <= 10:
        raise ValueError("Invalid grade or rank")
    return GAIN_TABLE[rank - 1][PROFILES[profile][relevance_grade]]


def _scores(case, names, completion, profile):
    labels = case["known"] | completion
    return tuple(sum(weight(profile, labels[p], rank)
                     for rank, p in enumerate(case["runs"][run], 1)) for run in names)


def _outcome(scores):
    prefix = tuple(sorted(range(4), key=lambda i: (-scores[i], i))[:3])
    return {"set": tuple(sorted(prefix)), "prefix": prefix}


def evaluate(case, completion, profile):
    names, unknown = validate_case(case)
    if (type(completion) is not dict or set(completion) != set(unknown)
            or not all(map(grade, completion.values()))):
        raise ValueError("A completion must assign every unknown exactly once")
    if profile not in PROFILES:
        raise ValueError("Profile must be binary or graded")
    scores = _scores(case, names, completion, profile)
    return {"run_names": names, "scores": scores, **_outcome(scores)}


def pair_row(case, profile, left, right):
    """Return c,h such that c+sum(h[p][g[p]]) >= 0 iff left precedes right.

    This retains the unequal rank coefficients of a shared passage. It is a
    constructor for future proof integration, not a certificate verifier.
    """
    names, unknown = validate_case(case)
    if (profile not in PROFILES or left not in names or right not in names or left == right):
        raise ValueError("Invalid profile or ordered run pair")
    ranks = {run: {p: r for r, p in enumerate(case["runs"][run], 1)}
             for run in (left, right)}

    def effect(p, g):
        return ((weight(profile, g, ranks[left][p]) if p in ranks[left] else 0)
                - (weight(profile, g, ranks[right][p]) if p in ranks[right] else 0))

    constant = sum(effect(p, g) for p, g in case["known"].items()) - int(left > right)
    terms = {p: tuple(effect(p, g) for g in range(4)) for p in unknown}
    return constant, terms


def scenarios(case, endpoint):
    """Twelve orientations valid for four runs and top three only.

    Prefix orientations cover possible discrepancies and can overlap. They
    must not be described as a disjoint partition of completion space.
    """
    names, _ = validate_case(case)
    if endpoint not in {"set", "prefix"}:
        raise ValueError("Endpoint must be set or prefix")
    result = []
    for a in names:
        for b in names:
            if a == b:
                continue
            if endpoint == "prefix":
                specs = (("binary", a, b), ("graded", b, a))
            else:
                specs = tuple(("binary", i, a) for i in names if i != a)
                specs += tuple(("graded", i, b) for i in names if i != b)
            result.append(tuple(pair_row(case, *spec) for spec in specs))
    return result


def audit(case, *, max_completions=MAX_COMPLETIONS):
    """Exhaust both profile outputs or return unresolved before enumeration.

    The explicit hard cap prevents accidental 4**40 work. An unresolved
    request has no invariance verdict and no complete marginal-set claim.
    """
    names, unknown = validate_case(case)
    if (type(max_completions) is not int or not 1 <= max_completions <= MAX_COMPLETIONS):
        raise ValueError(f"Budget must be an integer in 1..{MAX_COMPLETIONS}")
    size = 4 ** len(unknown)
    header = {
        "case_id": case["id"], "case_sha256": hashlib.sha256(canonical(case)).hexdigest(),
        "metric": METRIC, "scale": SCALE,
        "gain_table_sha256": hashlib.sha256(canonical(GAIN_TABLE)).hexdigest(),
        "tie_rule": "ascending lexical run name", "run_names": names,
        "unknown_count": len(unknown), "domain_size": size,
        "max_completions": max_completions,
    }
    if size > max_completions:
        return header | {"status": "unresolved", "reason": "completion_budget",
                         "completions_checked": 0}
    endpoint_results = {e: {"disagreement_count": 0, "first_witness": None}
                        for e in ("set", "prefix")}
    marginals = {(p, e): set() for p in PROFILES for e in endpoint_results}
    for values in product(range(4), repeat=len(unknown)):
        completion = dict(zip(unknown, values))
        outcomes = {p: _outcome(_scores(case, names, completion, p)) for p in PROFILES}
        for endpoint, result in endpoint_results.items():
            for profile in PROFILES:
                marginals[profile, endpoint].add(outcomes[profile][endpoint])
            differs = outcomes["binary"][endpoint] != outcomes["graded"][endpoint]
            result["disagreement_count"] += int(differs)
            if differs and result["first_witness"] is None:
                result["first_witness"] = completion
            if all(v == 0 for v in values):
                result["all_zero_disagrees"] = differs
            if all(v == 3 for v in values):
                result["all_three_disagrees"] = differs
    for endpoint, result in endpoint_results.items():
        result["status"] = "changed" if result["disagreement_count"] else "invariant"
        result["equal_marginal_sets"] = (marginals["binary", endpoint] == marginals["graded", endpoint])
        result["marginal_sets"] = {p: sorted(marginals[p, endpoint]) for p in PROFILES}
    return header | {"status": "complete", "completions_checked": size, "endpoints": endpoint_results}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON constant {value}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_json", type=Path)
    parser.add_argument("--max-completions", type=int, default=MAX_COMPLETIONS)
    args = parser.parse_args()
    try:
        if args.case_json.stat().st_size > 1_048_576:
            raise ValueError("Case file exceeds one MiB")
        case = json.loads(args.case_json.read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        result = audit(case, max_completions=args.max_completions)
    except (ValueError, OSError, RecursionError) as exc:
        parser.exit(2, f"Invalid input: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result["status"] == "complete" else 3


if __name__ == "__main__":
    raise SystemExit(main())
