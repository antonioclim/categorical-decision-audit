"""Independent exact ordered top-3 comparator for four fixed-depth runs.

The ordered prefix determines the full order because it omits one run. A
change therefore exists exactly when at least one pair can reverse its order.
For one pair, the DP retains reachable (binary, graded) integer score margins.
Each unknown passage is a single grade shared across both runs and codings.
"""
from __future__ import annotations

from itertools import combinations
from time import perf_counter_ns
from typing import Any

DEPTH = 10
TOP_K = 3
RUN_COUNT = 4
MAX_TIMEOUT_MS = 10_000
GRADES = (0, 1, 2, 3)
BINARY = (0, 0, 1, 1)
ROUTE = "exact_pair_margin_dp"


def validate_inputs(case: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, int], list[str]]:
    runs, known, unknown = case["runs"], case["known"], case["unknown"]
    if not isinstance(runs, dict) or len(runs) != RUN_COUNT or any(not isinstance(name, str) or not name for name in runs):
        raise ValueError("ordered prefix comparator requires exactly four named runs")
    if any(
        not isinstance(passages, list)
        or len(passages) != DEPTH
        or any(not isinstance(pid, str) or not pid for pid in passages)
        or len(set(passages)) != DEPTH
        for passages in runs.values()
    ):
        raise ValueError("each run must have ten distinct passages")
    if not isinstance(known, dict) or any(
        not isinstance(pid, str) or type(grade) is not int or grade not in GRADES
        for pid, grade in known.items()
    ):
        raise ValueError("known grades must be integer grades in 0..3")
    if not isinstance(unknown, list) or any(not isinstance(pid, str) or not pid for pid in unknown):
        raise ValueError("unknown must list literal passage identifiers")
    unknown_ids = set(unknown)
    if len(unknown_ids) != len(unknown) or unknown_ids.intersection(known):
        raise ValueError("duplicate or both known and unknown passage")
    if set(known).union(unknown_ids) != {pid for passages in runs.values() for pid in passages}:
        raise ValueError("known and unknown grades must partition the passage universe")
    return runs, known, sorted(unknown)


def direct_prefixes(runs: dict[str, list[str]], grades: dict[str, int]) -> tuple[dict, dict]:
    totals = {
        "binary": {name: sum(BINARY[grades[pid]] for pid in ids) for name, ids in runs.items()},
        "graded": {name: sum(grades[pid] for pid in ids) for name, ids in runs.items()},
    }
    prefixes = {
        profile: sorted(runs, key=lambda name: (-scores[name], name))[:TOP_K]
        for profile, scores in totals.items()
    }
    return totals, prefixes


def solve_prefix(case: dict[str, Any], timeout_ms: int = MAX_TIMEOUT_MS) -> dict[str, Any]:
    """Return exact existential prefix status and one independently rechecked witness."""
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= MAX_TIMEOUT_MS:
        raise ValueError("timeout_ms must be an integer in 1..10000")
    started = perf_counter_ns()
    deadline = started + timeout_ms * 1_000_000
    runs, known, unknown = validate_inputs(case)
    passage_sets = {name: set(passages) for name, passages in runs.items()}
    report = {
        "status": "unknown", "witness": None, "route": ROUTE, "domain_nonempty": True,
        "pairs_completed": 0, "max_layer_states": 1, "layer_states_total": 0,
        "timeout_ms": timeout_ms,
    }

    def timed_out() -> dict[str, Any]:
        return dict(report, elapsed_ns=perf_counter_ns() - started, reason="elapsed beyond prefix endpoint cap")

    for left, right in combinations(sorted(runs), 2):
        if perf_counter_ns() >= deadline:
            return timed_out()
        left_only = passage_sets[left].difference(passage_sets[right])
        right_only = passage_sets[right].difference(passage_sets[left])
        known_left = [known[pid] for pid in left_only if pid in known]
        known_right = [known[pid] for pid in right_only if pid in known]
        base = (
            sum(BINARY[grade] for grade in known_left) - sum(BINARY[grade] for grade in known_right),
            sum(known_left) - sum(known_right),
        )
        active = [
            (pid, 1 if pid in left_only else -1)
            for pid in unknown if pid in left_only or pid in right_only
        ]
        states = {base: None}
        layers: list[dict[tuple[int, int], tuple[tuple[int, int], int]]] = []
        for _, sign in active:
            next_states = {}
            for binary_margin, graded_margin in states:
                prior = (binary_margin, graded_margin)
                for grade in GRADES:
                    updated = (binary_margin + sign * BINARY[grade], graded_margin + sign * grade)
                    if updated not in next_states:
                        next_states[updated] = (prior, grade)
            layers.append(next_states)
            states = next_states
            report["max_layer_states"] = max(report["max_layer_states"], len(states))
            report["layer_states_total"] += len(states)
            if perf_counter_ns() >= deadline:
                return timed_out()
        report["pairs_completed"] += 1
        # The left ID is first in lexical order and therefore wins score ties.
        reversed_order = next(
            ((db, dg) for db, dg in states if (db >= 0) != (dg >= 0)), None,
        )
        if reversed_order is None:
            continue
        witness = dict.fromkeys(unknown, 0)
        state = reversed_order
        for (pid, _), layer in zip(reversed(active), reversed(layers)):
            state, witness[pid] = layer[state]
        if state != base:
            raise RuntimeError("witness reconstruction did not reach the pair's base margins")
        totals, prefixes = direct_prefixes(runs, known | witness)
        recovered = tuple(totals[profile][left] - totals[profile][right] for profile in ("binary", "graded"))
        if recovered != reversed_order or prefixes["binary"] == prefixes["graded"]:
            raise RuntimeError("DP witness failed independent integer prefix revalidation")
        if perf_counter_ns() >= deadline:
            return timed_out()
        return dict(
            report, status="changed", witness=witness, elapsed_ns=perf_counter_ns() - started,
            witness_evaluation={
                "integer_totals": totals, "prefixes": prefixes,
                "reversed_pair": [left, right], "pair_margins": list(recovered),
            },
        )
    if perf_counter_ns() >= deadline:
        return timed_out()
    return dict(report, status="invariant", elapsed_ns=perf_counter_ns() - started)
