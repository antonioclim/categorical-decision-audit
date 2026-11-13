"""Exhaustively cross-check all worlds using chunked vectorised integer evaluation."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np


ENDPOINTS = ("set", "prefix", "strict_set", "strict_prefix")


def scores(case, assignment):
    labels = case["known"] | assignment
    result = {}
    for name, passages in sorted(case["runs"].items()):
        grades = [labels[p] for p in passages]
        result[name] = {"binary_numerator": sum(g >= 2 for g in grades),
                        "graded_numerator": sum(grades)}
    return result


def exhaustive(case, chunk_size):
    runs = [set(passages) for _, passages in sorted(case["runs"].items())]
    unknown = case["unknown"]
    incidence = np.array([[p in run for run in runs] for p in unknown],
                         dtype=np.int16).reshape(len(unknown), 4)
    known = [{p: case["known"][p] for p in run if p in case["known"]} for run in runs]
    base_binary = np.array([sum(g >= 2 for g in group.values()) for group in known], dtype=np.int16)
    base_graded = np.array([sum(group.values()) for group in known], dtype=np.int16)
    shifts = 2 * np.arange(len(unknown), dtype=np.int64)
    total = 4 ** len(unknown)
    counts = Counter()
    for start in range(0, total, chunk_size):
        ids = np.arange(start, min(start + chunk_size, total), dtype=np.int64)
        labels = ((ids[:, None] >> shifts) & 3).astype(np.int16)
        binary = (labels >= 2).astype(np.int16) @ incidence + base_binary
        graded = labels @ incidence + base_graded
        binary_order = np.argsort(-binary, axis=1, kind="stable")
        graded_order = np.argsort(-graded, axis=1, kind="stable")
        binary_gaps = -np.diff(np.take_along_axis(binary, binary_order, axis=1))
        graded_gaps = -np.diff(np.take_along_axis(graded, graded_order, axis=1))
        set_changes = binary_order[:, -1] != graded_order[:, -1]
        prefix_changes = np.any(binary_order[:, :3] != graded_order[:, :3], axis=1)
        strict_cutoff = (binary_gaps[:, -1] > 0) & (graded_gaps[:, -1] > 0)
        strict_order = np.all(binary_gaps > 0, axis=1) & np.all(graded_gaps > 0, axis=1)
        score_changes = np.any(3 * binary != graded, axis=1)
        for name, predicate in {
            "set": set_changes,
            "prefix": prefix_changes,
            "strict_set": set_changes & strict_cutoff,
            "strict_prefix": prefix_changes & strict_order,
            "order_only": prefix_changes & ~set_changes,
            "strict_order_only": prefix_changes & ~set_changes & strict_order,
            "score_only": score_changes & ~prefix_changes,
            "same_scores_and_prefix": ~score_changes & ~prefix_changes,
        }.items():
            counts[name] += int(np.count_nonzero(predicate))
    return {"total_worlds": total, **counts}


def run(args):
    started = perf_counter()
    cases_raw = args.cases.read_bytes()
    if sha256(cases_raw).hexdigest() != args.expect_cases_sha256:
        raise ValueError("Case digest differs from freeze")
    cases = json.loads(cases_raw)
    reference = json.loads(args.oracle.read_text())
    results = {}
    for case in cases:
        case_id = case["id"]
        world_counts = exhaustive(case, args.chunk_size)
        expected = reference[case_id]["world_counts"]
        assert all(expected[name] == count for name, count in world_counts.items()), case_id
        results[case_id] = world_counts
    assert set(results) == set(reference)
    document = {
        "method": "Chunked complete Cartesian traversal; stable integer scoring in NumPy",
        "numpy": np.__version__, "chunk_size": args.chunk_size,
        "cases_verified": len(results), "worlds_checked": sum(r["total_worlds"] for r in results.values()),
        "oracle_mismatches": 0, "elapsed_seconds": perf_counter() - started,
        "per_case": results,
    }
    args.output.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n")
    print({k: v for k, v in document.items() if k != "per_case"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expect-cases-sha256", required=True)
    parser.add_argument("--chunk-size", type=int, default=262144)
    run(parser.parse_args())
