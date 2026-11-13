"""Independent exact top-three oracle for the four-run holdout.

Use direct enumeration on small domains. In larger domains, group unknown
passages by incidence, enumerate reachable integer total pairs per group and
prune only when pairwise bounds rule out a change in every remaining world.
No production adapter or SMT implementation is imported.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


GRADES = (0, 1, 2, 3)
RUN_COUNT = 4
DEPTH = 10
TOP_K = 3
DIRECT_UNKNOWN_LIMIT = 5
BRANCH_NODE_CAP = 20_000
ENDPOINTS = ("set", "prefix", "strict_set", "strict_prefix")
ENDPOINT_BITS = {name: 1 << index for index, name in enumerate(ENDPOINTS)}
ALL_ENDPOINTS = sum(ENDPOINT_BITS.values())


@dataclass(frozen=True)
class Case:
    run_ids: tuple[str, ...]
    runs: tuple[tuple[str, ...], ...]
    known: dict[str, int]
    unknown: tuple[str, ...]


@dataclass(frozen=True)
class Bucket:
    incidence: tuple[int, ...]
    passages: tuple[str, ...]
    options: tuple[tuple[int, int, tuple[int, ...]], ...]


@dataclass(frozen=True)
class Node:
    depth: int
    binary: tuple[int, ...]
    graded: tuple[int, ...]
    samples: tuple[tuple[int, ...], ...]
    possible: int


def _prepare(record: dict) -> Case:
    run_ids = tuple(sorted(record["runs"]))
    runs = tuple(tuple(record["runs"][name]) for name in run_ids)
    if len(runs) != RUN_COUNT:
        raise ValueError("expected four runs")
    if any(len(run) != DEPTH or len(set(run)) != DEPTH for run in runs):
        raise ValueError("each run must contain ten distinct passages")
    known = record["known"]
    unknown = tuple(sorted(record["unknown"]))
    if any(type(grade) is not int or grade not in GRADES for grade in known.values()):
        raise ValueError("known grades must be integers from 0 through 3")
    if len(set(unknown)) != len(unknown) or set(known) & set(unknown):
        raise ValueError("known and unknown passages must be disjoint and unique")
    if set(known) | set(unknown) != set(itertools.chain.from_iterable(runs)):
        raise ValueError("known and unknown passages must partition the run union")
    return Case(run_ids, runs, dict(known), unknown)


def _direct_totals(case: Case, completion: dict[str, int]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    grades = case.known | completion
    binary = tuple(sum(grades[passage] >= 2 for passage in run) for run in case.runs)
    graded = tuple(sum(grades[passage] for passage in run) for run in case.runs)
    return binary, graded


def _orders_and_gaps(binary: tuple[int, ...], graded: tuple[int, ...]) -> tuple:
    orders = tuple(tuple(sorted(range(RUN_COUNT), key=lambda index: (-scores[index], index))) for scores in (binary, graded))
    gaps = tuple(
        tuple(scores[left] - scores[right] for left, right in zip(order, order[1:]))
        for scores, order in zip((binary, graded), orders)
    )
    return orders, gaps


def _changed_endpoints(binary: tuple[int, ...], graded: tuple[int, ...]) -> int:
    orders, gaps = _orders_and_gaps(binary, graded)
    set_changes = orders[0][-1] != orders[1][-1]
    prefix_changes = orders[0] != orders[1]
    strict_cutoff = all(arm_gaps[-1] > 0 for arm_gaps in gaps)
    strict_order = all(gap > 0 for arm_gaps in gaps for gap in arm_gaps)
    return sum(
        ENDPOINT_BITS[name]
        for name, changes in zip(ENDPOINTS, (set_changes, prefix_changes, set_changes and strict_cutoff, prefix_changes and strict_order))
        if changes
    )


def _validate(case: Case, endpoint: str, completion: dict[str, int]) -> dict:
    if not isinstance(completion, dict) or set(completion) != set(case.unknown):
        return {"accepted": False, "reason": "completion must assign exactly the unknown passages"}
    if any(type(grade) is not int or grade not in GRADES for grade in completion.values()):
        return {"accepted": False, "reason": "completion grades must be integers from 0 through 3"}
    binary, graded = _direct_totals(case, completion)
    orders, gaps = _orders_and_gaps(binary, graded)
    accepted = bool(_changed_endpoints(binary, graded) & ENDPOINT_BITS[endpoint])
    return {
        "accepted": accepted,
        "reason": None if accepted else "completion does not change this endpoint",
        "binary_totals": dict(zip(case.run_ids, binary)),
        "graded_totals": dict(zip(case.run_ids, graded)),
        "binary_prefix": [case.run_ids[index] for index in orders[0][:TOP_K]],
        "graded_prefix": [case.run_ids[index] for index in orders[1][:TOP_K]],
        "binary_gaps": list(gaps[0]),
        "graded_gaps": list(gaps[1]),
    }


def validate_witness(record: dict, endpoint: str, completion: dict[str, int]) -> dict:
    """Check an endpoint witness by independently scoring raw run membership."""
    if endpoint not in ENDPOINT_BITS:
        raise ValueError(f"unknown endpoint: {endpoint}")
    return _validate(_prepare(record), endpoint, completion)


def _reachable_options(size: int) -> tuple[tuple[int, int, tuple[int, ...]], ...]:
    representatives = {(0, 0): ()}
    for _ in range(size):
        following = {}
        for (binary, graded), sample in representatives.items():
            for grade in GRADES:
                following.setdefault((binary + int(grade >= 2), graded + grade), sample + (grade,))
        representatives = following
    options = [(binary, graded, sample) for (binary, graded), sample in representatives.items()]
    # Try extreme totals first. All reachable totals remain in the search.
    options.sort(key=lambda item: (min(item[0], size - item[0]) + min(item[1], 3 * size - item[1]), item[:2]))
    return tuple(options)


def _buckets(case: Case) -> tuple[tuple[Bucket, ...], tuple[str, ...]]:
    patterns: dict[tuple[int, ...], list[str]] = defaultdict(list)
    run_members = tuple(set(run) for run in case.runs)
    for passage in case.unknown:
        incidence = tuple(index for index, members in enumerate(run_members) if passage in members)
        patterns[incidence].append(passage)
    # A passage in all four runs adds an identical total to each score and
    # leaves every order and tie unchanged. Witnesses assign it grade zero.
    neutral = tuple(patterns.pop(tuple(range(RUN_COUNT)), ()))
    order = sorted(patterns, key=lambda key: (-len(patterns[key]) * len(key) * (RUN_COUNT - len(key)), key))
    buckets = tuple(Bucket(key, tuple(patterns[key]), _reachable_options(len(patterns[key]))) for key in order)
    return buckets, neutral


def _remaining_pair_bounds(buckets: tuple[Bucket, ...]) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """For each depth, exact upper bound on future binary score left−right."""
    bounds = [[0] * RUN_COUNT for _ in range(RUN_COUNT)]
    suffix = [tuple(tuple(row) for row in bounds)]
    for bucket in reversed(buckets):
        for left in bucket.incidence:
            for right in range(RUN_COUNT):
                if right not in bucket.incidence:
                    bounds[left][right] += len(bucket.passages)
        suffix.append(tuple(tuple(row) for row in bounds))
    return tuple(reversed(suffix))


def _requirements() -> tuple:
    records = []
    for position, order in enumerate(itertools.permutations(range(RUN_COUNT))):
        ordinary = []
        strict_order = []
        for i, left in enumerate(order):
            for j in range(i + 1, RUN_COUNT):
                right = order[j]
                ordinary.append((left, right, int(left > right)))
                strict_order.append((left, right, j - i))
        strict_cutoff = tuple((left, order[-1], 1) for left in order[:TOP_K])
        records.append((1 << order[-1], 1 << position, ordinary, strict_cutoff, strict_order))
    return tuple(records)


RANK_REQUIREMENTS = _requirements()


def _possible_profiles(totals: tuple[int, ...], remaining: tuple[tuple[int, ...], ...], scale: int, active: int) -> tuple[int, ...]:
    upper = tuple(
        tuple(totals[left] - totals[right] + scale * remaining[left][right] for right in range(RUN_COUNT))
        for left in range(RUN_COUNT)
    )
    sets = prefixes = strict_sets = strict_prefixes = 0
    for set_bit, prefix_bit, ordinary, strict_cutoff, strict_order in RANK_REQUIREMENTS:
        if any(upper[left][right] < threshold for left, right, threshold in ordinary):
            continue
        sets |= set_bit
        prefixes |= prefix_bit
        if active & ENDPOINT_BITS["strict_set"] and all(upper[left][right] >= threshold for left, right, threshold in strict_cutoff):
            strict_sets |= set_bit
        if active & ENDPOINT_BITS["strict_prefix"] and all(upper[left][right] >= threshold for left, right, threshold in strict_order):
            strict_prefixes |= prefix_bit
    return sets, prefixes, strict_sets, strict_prefixes


def _possibly_changed(node: Node, remaining: tuple[tuple[int, ...], ...], active: int) -> int:
    # Each mask is an overapproximation of the rank profiles in that arm.
    # Two identical singletons cannot differ. Empty strict masks mean no
    # jointly admissible strict endpoint can differ at this node.
    binary = _possible_profiles(node.binary, remaining, 1, active)
    graded = _possible_profiles(node.graded, remaining, 3, active)
    possible = 0
    for index, (left, right) in enumerate(zip(binary, graded)):
        bit = 1 << index
        union = left | right
        if active & bit and left and right and union & (union - 1):
            possible |= bit
    return possible


def _complete(node: Node, buckets: tuple[Bucket, ...], neutral: tuple[str, ...]) -> dict[str, int]:
    result = dict.fromkeys(neutral, 0)
    for bucket, grades in zip(buckets, node.samples):
        result.update(zip(bucket.passages, grades))
    return result


def _record_witnesses(found: dict[str, dict[str, int]], bits: int, completion: dict[str, int]) -> None:
    for name, bit in ENDPOINT_BITS.items():
        if bits & bit:
            found.setdefault(name, completion)


def _search(case: Case, node_cap: int) -> tuple[dict, int, dict]:
    buckets, neutral = _buckets(case)
    bounds = _remaining_pair_bounds(buckets)
    base_binary, base_graded = _direct_totals(case, dict.fromkeys(case.unknown, 0))
    stack = [Node(0, base_binary, base_graded, (), ALL_ENDPOINTS)]
    witnesses = {}
    resolved = 0
    visited = leaves = pruned = pending = 0
    while stack:
        node = stack.pop()
        active = node.possible & ~resolved
        if not active:
            continue
        if visited == node_cap:
            pending = active
            for waiting in stack:
                pending |= waiting.possible & ~resolved
            break
        visited += 1
        if node.depth == len(buckets):
            leaves += 1
            bits = active & _changed_endpoints(node.binary, node.graded)
            if bits:
                _record_witnesses(witnesses, bits, _complete(node, buckets, neutral))
                resolved |= bits
            continue
        possible = _possibly_changed(node, bounds[node.depth], active)
        if not possible:
            pruned += 1
            continue
        bucket = buckets[node.depth]
        for binary_add, graded_add, sample in reversed(bucket.options):
            binary = tuple(value + binary_add * (index in bucket.incidence) for index, value in enumerate(node.binary))
            graded = tuple(value + graded_add * (index in bucket.incidence) for index, value in enumerate(node.graded))
            stack.append(Node(node.depth + 1, binary, graded, node.samples + (sample,), possible))
    statistics = {
        "branch_node_cap": node_cap,
        "branch_nodes_visited": visited,
        "compressed_leaves_evaluated": leaves,
        "branch_nodes_pruned_by_bounds": pruned,
        "cap_reached": bool(pending),
        "neutral_unknown_count": len(neutral),
        "bucket_sizes": [len(bucket.passages) for bucket in buckets],
        "bucket_option_counts": [len(bucket.options) for bucket in buckets],
    }
    return witnesses, pending, statistics


def _direct(case: Case) -> tuple[dict, dict]:
    witnesses = {}
    counts = dict.fromkeys(ENDPOINTS, 0)
    evaluated = 0
    for assignment in itertools.product(GRADES, repeat=len(case.unknown)):
        completion = dict(zip(case.unknown, assignment))
        bits = _changed_endpoints(*_direct_totals(case, completion))
        _record_witnesses(witnesses, bits, completion)
        for name, bit in ENDPOINT_BITS.items():
            counts[name] += bool(bits & bit)
        evaluated += 1
    return witnesses, {"direct_worlds_evaluated": evaluated, "changing_worlds_by_endpoint": counts, "cap_reached": False}


def solve_case(record: dict) -> dict:
    case = _prepare(record)
    if len(case.unknown) <= DIRECT_UNKNOWN_LIMIT:
        method = "direct_exhaustive"
        witnesses, statistics = _direct(case)
        pending = 0
    else:
        method = "compressed_pair_bounds"
        witnesses, pending, statistics = _search(case, BRANCH_NODE_CAP)
    endpoints = {}
    for name, bit in ENDPOINT_BITS.items():
        witness = witnesses.get(name)
        if witness is not None:
            if not _validate(case, name, witness)["accepted"]:
                raise RuntimeError(f"direct witness check failed for {record['id']} {name}")
            status = "changed"
        elif pending & bit:
            status = "unknown"
        else:
            status = "invariant"
        endpoints[name] = {"status": status, "witness": witness}
    return {
        "method": method,
        "unknown_count": len(case.unknown),
        "domain_nonempty": True,
        "possible_world_count": len(GRADES) ** len(case.unknown),
        "unknown_endpoints_due_to_cap": [name for name, bit in ENDPOINT_BITS.items() if pending & bit],
        "statistics": statistics,
        "endpoints": endpoints,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cases-sha256", required=True)
    args = parser.parse_args()
    case_bytes = args.cases.read_bytes()
    if hashlib.sha256(case_bytes).hexdigest() != args.cases_sha256:
        raise ValueError("cases.json digest does not match the frozen digest")
    results = {}
    for record in json.loads(case_bytes):
        case_id = record["id"]
        if case_id in results:
            raise ValueError(f"duplicate case ID: {case_id}")
        results[case_id] = solve_case(record)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
