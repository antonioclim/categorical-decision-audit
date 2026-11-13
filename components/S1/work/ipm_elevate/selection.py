"""Exact paired shortlist outcomes from compressed shared-grade contributions."""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from functools import lru_cache
from hashlib import sha256
from itertools import product
import json
from math import prod
from pathlib import Path

LIMIT = 2_000_000
KEYS = tuple(f"{k}_{endpoint}" for k in (1, 2, 3) for endpoint in ("set", "prefix"))
PRIMARY = ("3_set", "3_prefix")


@lru_cache(maxsize=41)
def group_sums(size):
    states = {(0, 0): (1, ())}
    for _ in range(size):
        updated = {}
        for (binary, graded), (count, witness) in states.items():
            for grade in range(4):
                key = (binary + (grade >= 2), graded + grade)
                prior = updated.get(key)
                updated[key] = ((prior[0] + count, prior[1]) if prior else (count, (*witness, grade)))
        states = updated
    assert sum(count for count, _ in states.values()) == 4 ** size
    return tuple((b, g, count, witness) for (b, g), (count, witness) in sorted(states.items()))


def exact_totals(runs, grades):
    return [[sum((grades[p] >= 2) if arm == 0 else grades[p] for p in run)
             for run in runs] for arm in range(2)]


def worlds(runs, known, unknown):
    # Unassigned grades contribute zero to the starting score.
    base = exact_totals(runs, dict.fromkeys(set.union(*runs), 0) | known)
    groups = defaultdict(list)
    for passage in sorted(unknown):
        members = tuple(i for i, run in enumerate(runs) if passage in run)
        assert members
        groups[members].append(passage)
    active = [(members, passages, group_sums(len(passages)))
              for members, passages in sorted(groups.items()) if len(members) < 4]
    neutral = groups.get(tuple(range(4)), [])
    count = prod(len(states) for _, _, states in active)
    if count > LIMIT:
        return count, None

    def generate():
        for row in product(*(states for _, _, states in active)):
            totals = [arm.copy() for arm in base]
            multiplicity = 4 ** len(neutral)
            for (members, _, _), (binary, graded, weight, _) in zip(active, row):
                for i in members:
                    totals[0][i] += binary
                    totals[1][i] += graded
                multiplicity *= weight
            yield totals, multiplicity, row

    return count, (generate(), active, neutral)


def describe(totals):
    orders = tuple(tuple(sorted(range(4), key=lambda i: (-scores[i], i))) for scores in totals)
    gaps = tuple(tuple(scores[a] - scores[b] for a, b in zip(order, order[1:]))
                 for scores, order in zip(totals, orders))
    rows = {}
    for k in (1, 2, 3):
        left, right = orders[0][:k], orders[1][:k]
        cuts = gaps[0][k - 1] > 0 and gaps[1][k - 1] > 0
        within = all(gap > 0 for arm in gaps for gap in arm[:k])
        rows[f"{k}_set"] = (tuple(sorted(left)), tuple(sorted(right)), cuts)
        rows[f"{k}_prefix"] = (left, right, within)
    return rows


def representative(row, active, neutral):
    grades = dict.fromkeys(neutral, 0)
    for (_, passages, _), (_, _, _, assignment) in zip(active, row):
        grades.update(zip(passages, assignment))
    return grades


def pivotality(runs, known, unknown, shared, outcomes):
    mixed = tuple(key for key in PRIMARY
                  if outcomes[key]["common_agreement"] and outcomes[key]["common_change"])
    verdicts = {}
    for p, members in shared.items():
        if len(members) == 4 or not mixed:
            verdicts[p] = dict.fromkeys(PRIMARY, False)
            continue
        _, data = worlds(runs, known, [item for item in unknown if item != p])
        if data is None:
            verdicts[p] = dict.fromkeys(PRIMARY, None)
            continue
        states, active, neutral = data
        found = {}
        for totals, _, row in states:
            flags = {key: [] for key in mixed}
            for grade in range(4):
                adjusted = [scores.copy() for scores in totals]
                for i in members:
                    adjusted[0][i] += grade >= 2
                    adjusted[1][i] += grade
                described = describe(adjusted)
                for key in mixed:
                    a, b, _ = described[key]
                    flags[key].append(a != b)
            for key, values in flags.items():
                if key not in found and any(values) and not all(values):
                    other_grades = representative(row, active, neutral)
                    replay = []
                    for grade in range(4):
                        a, b, _ = describe(exact_totals(runs, known | other_grades | {p: grade}))[key]
                        replay.append(a != b)
                    assert replay == values
                    found[key] = {"other_grades": other_grades, "change_by_grade_0_to_3": values}
            if len(found) == len(mixed):
                break
        verdicts[p] = {key: found.get(key, False) for key in PRIMARY}
    return verdicts


def evaluate(case):
    names = sorted(case["runs"])
    runs = tuple(set(case["runs"][name]) for name in names)
    known, unknown = case["known"], case["unknown"]
    assert len(names) == 4 and all(len(run) == 10 for run in runs)
    assert all(len(case["runs"][name]) == 10 for name in names)
    assert len(set(unknown)) == len(unknown) and not set(unknown) & known.keys()
    assert set(unknown) | known.keys() == set.union(*runs)
    assert all(type(grade) is int and 0 <= grade <= 3 for grade in known.values())
    count, data = worlds(runs, known, unknown)
    incidence = {p: tuple(i for i, run in enumerate(runs) if p in run) for p in unknown}
    shared = {p: members for p, members in incidence.items() if len(members) > 1}
    detail = {"qid": case["qid"], "stratum": case["stratum"], "unknown": len(unknown),
              "shared": len(shared), "shared_incidence": dict(Counter(map(len, shared.values()))),
              "compressed_states": count, "worlds": 4 ** len(unknown)}
    if data is None:
        return detail | {"status": "unresolved"}
    states, active, neutral = data
    change, strict = Counter(), Counter()
    outputs = {key: (set(), set()) for key in KEYS}
    witness = {}
    total = 0
    zero, three = (describe(exact_totals(runs, known | dict.fromkeys(unknown, grade))) for grade in (0, 3))
    for totals, weight, row in states:
        total += weight
        for key, (a, b, strict_cut) in describe(totals).items():
            outputs[key][0].add(a)
            outputs[key][1].add(b)
            if a != b:
                change[key] += weight
                strict[key] += strict_cut * weight
                if key in PRIMARY and key not in witness:
                    witness[key] = representative(row, active, neutral)
    assert total == detail["worlds"]
    outcomes = {}
    for key in KEYS:
        a, b = outputs[key]
        zero_change = zero[key][0] != zero[key][1]
        three_change = three[key][0] != three[key][1]
        any_change = change[key] > 0
        assert not (zero_change or three_change) or any_change
        outcomes[key] = {"common_agreement": change[key] < total, "common_change": any_change,
                         "change_worlds": change[key], "strict_change_worlds": strict[key],
                         "zero_change": zero_change, "three_change": three_change,
                         "marginals_equal": a == b,
                         "separate_change": not (len(a) == len(b) == 1 and a == b),
                         "binary_outputs": len(a), "graded_outputs": len(b)}
        if key in witness:
            replay = describe(exact_totals(runs, known | witness[key]))[key]
            assert replay[0] != replay[1]
            outcomes[key]["witness"] = witness[key]
            outcomes[key]["witness_outputs"] = [[names[i] for i in output] for output in replay[:2]]
    return detail | {"status": "exact", "outcomes": outcomes,
                     "shared_pivotality": pivotality(runs, known, unknown, shared, outcomes)
                     if case["stratum"] == "natural" else {}}


def aggregate(rows):
    by_stratum = defaultdict(list)
    for row in rows.values():
        by_stratum[row["stratum"]].append(row)
    summary = {}
    for stratum, group in sorted(by_stratum.items()):
        exact = [row for row in group if row["status"] == "exact"]
        entry = {"cases": len(group), "exact": len(exact), "worlds_exact": sum(row["worlds"] for row in exact),
                 "shared_pairs": sum(row["shared"] for row in group),
                 "queries_with_shared": sum(row["shared"] > 0 for row in group),
                 "max_compressed_states": max(row["compressed_states"] for row in group)}
        for key in KEYS:
            evaluated = [row["outcomes"][key] for row in exact]
            entry[key] = {
                "change": sum(o["common_change"] for o in evaluated),
                "always_change": sum(not o["common_agreement"] for o in evaluated),
                "strict_change": sum(o["strict_change_worlds"] > 0 for o in evaluated),
                "all_zero_change": sum(o["zero_change"] for o in evaluated),
                "all_zero_misses": sum(o["common_change"] and not o["zero_change"] for o in evaluated),
                "two_point_misses": sum(o["common_change"] and not (o["zero_change"] or o["three_change"])
                                        for o in evaluated),
                "marginal_equality_misses": sum(o["common_change"] and o["marginals_equal"] for o in evaluated),
                "separate_completion_flags_without_common_change": sum(o["separate_change"] and not o["common_change"]
                                                                       for o in evaluated),
            }
            if stratum == "natural" and key in PRIMARY:
                counts = [sum(isinstance(v[key], dict) for v in row["shared_pivotality"].values())
                          for row in exact]
                entry[key]["pivotal_shared_pairs"] = sum(counts)
                entry[key]["queries_with_pivotal_shared"] = sum(count > 0 for count in counts)
                entry[key]["unresolved_shared_pivotality_queries"] = sum(
                    any(v[key] is None for v in row["shared_pivotality"].values()) for row in exact)
        summary[stratum] = entry
    return summary


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    data = args.cases.read_bytes()
    digest = sha256(data).hexdigest()
    if digest != args.sha256:
        raise SystemExit("Case file hash does not match the freeze.")
    cases = json.loads(data)
    assert len({case["id"] for case in cases}) == len(cases)
    rows = {case["id"]: evaluate(case) for case in cases}
    result = {"input_sha256": digest, "state_limit": LIMIT, "summary": aggregate(rows), "by_case": rows}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for stratum, line in result["summary"].items():
        print(stratum, "cases", line["cases"], "exact", line["exact"],
              "shared", line["shared_pairs"], "cap", line["max_compressed_states"],
              "set", line["3_set"], "prefix", line["3_prefix"])


if __name__ == "__main__":
    main()
