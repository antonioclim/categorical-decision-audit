"""Produce portable no-change proofs for two top-three outputs on shared labels."""

from hashlib import sha256
from itertools import combinations
import json


BINARY = (0, 0, 1, 1)
GRADED = (0, 1, 2, 3)
NODE_LIMIT = 4096


def identity(case, endpoint):
    data = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")
    return {"case_sha256": sha256(data).hexdigest(), "case_id": case["id"], "endpoint": endpoint}


def read_case(case):
    runs = case["runs"]
    known = case["known"]
    unknown = tuple(sorted(case["unknown"]))
    if len(runs) != 4 or any(len(items) != 10 or len(set(items)) != 10 for items in runs.values()):
        raise ValueError("Expected four runs with ten distinct passages each")
    if (len(set(unknown)) != len(unknown) or set(unknown) & known.keys()
            or set(unknown) | known.keys() != set().union(*map(set, runs.values()))):
        raise ValueError("Known and unknown passage IDs must partition the run union")
    if any(type(grade) is not int or not 0 <= grade <= 3 for grade in known.values()):
        raise ValueError("Grades must be integers in 0..3")
    return [set(runs[name]) for name in sorted(runs)], known, unknown


def orientations(endpoint):
    for a in range(4):
        for b in range(4):
            if a == b:
                continue
            if endpoint == "set":
                yield ([(BINARY, i, a) for i in range(4) if i != a]
                       + [(GRADED, i, b) for i in range(4) if i != b])
            else:
                yield [(BINARY, a, b), (GRADED, b, a)]


def row_data(spec, groups, known, unknown):
    rows = []
    for weights, i, j in spec:
        pos = groups[i] - groups[j]
        neg = groups[j] - groups[i]
        fixed = (sum(weights[known[p]] for p in pos if p in known)
                 - sum(weights[known[p]] for p in neg if p in known))
        terms = [weights if p in pos else tuple(-w for w in weights) if p in neg else (0, 0, 0, 0)
                 for p in unknown]
        rows.append((fixed - int(i > j), terms))
    return rows


def bound_data(rows):
    for size in range(1, len(rows) + 1):
        for subset in combinations(range(len(rows)), size):
            margin = sum(rows[i][0] for i in subset)
            variables = list(zip(*(rows[i][1] for i in subset)))
            vectors = [tuple(map(sum, zip(*column))) for column in variables]
            maxima = [max(vector) for vector in vectors]
            yield subset, margin + sum(maxima), vectors, maxima


def changed(groups, labels, endpoint):
    orders = []
    for weights in (BINARY, GRADED):
        scores = [sum(weights[labels[p]] for p in items) for items in groups]
        order = sorted(range(4), key=lambda i: (-scores[i], i))
        orders.append(order[-1] if endpoint == "set" else order[:3])
    return orders[0] != orders[1]


def resolve(rows, unknown, count):
    """Find one world satisfying an orientation, a full obstruction or a budget exit."""
    root_data = []
    for subset, maximum, vectors, maxima in bound_data(rows):
        if maximum < 0:
            if count[0] >= NODE_LIMIT:
                return "unknown", None
            count[0] += 1
            return "invariant", {"subset": list(subset)}
        root_data.append((subset, maximum, vectors, maxima))

    split_order = sorted(range(len(unknown)), key=lambda k: (
        -sum(max(terms[k]) - min(terms[k]) for _, terms in rows), k))
    split_order = [k for k in split_order if any(any(terms[k]) for _, terms in rows)]
    margins = [fixed for fixed, _ in rows]
    assignment = {}

    def descend(depth, bounds, current):
        if count[0] >= NODE_LIMIT:
            return "unknown", None
        count[0] += 1
        for value, (subset, _, _, _) in zip(bounds, root_data):
            if value < 0:
                return "invariant", {"subset": list(subset)}
        if all(value >= 0 for value in current):
            # Every unassigned grade is currently zero (both weight maps vanish at zero).
            return "changed", {p: assignment.get(k, 0) for k, p in enumerate(unknown)}
        if depth == len(split_order):
            raise AssertionError("An infeasible singleton must have a failing individual row")
        k = split_order[depth]
        children = []
        for grade in range(4):
            assignment[k] = grade
            child_bounds = [value + terms[k][grade] - maxima[k]
                            for value, (_, _, terms, maxima) in zip(bounds, root_data)]
            child_current = [value + terms[k][grade] for value, (_, terms) in zip(current, rows)]
            state, payload = descend(depth + 1, child_bounds, child_current)
            if state != "invariant":
                return state, payload
            children.append(payload)
        assignment.pop(k)
        return "invariant", {"split": unknown[k], "children": children}

    return descend(0, [maximum for _, maximum, _, _ in root_data], margins)


def produce(case, endpoint):
    if endpoint not in {"set", "prefix"}:
        raise ValueError("Unknown top-three endpoint")
    groups, known, unknown = read_case(case)
    record = identity(case, endpoint)
    for grade in (0, 3):
        witness = dict.fromkeys(unknown, grade)
        if changed(groups, known | witness, endpoint):
            return record | {"status": "changed", "witness": witness}
    nodes, trees = [0], []
    for spec in orientations(endpoint):
        rows = row_data(spec, groups, known, unknown)
        status, payload = resolve(rows, unknown, nodes)
        if status == "unknown":
            return record | {"status": "unknown", "reason": "node_limit"}
        if status == "changed":
            assert changed(groups, known | payload, endpoint)
            return record | {"status": status, "witness": payload}
        trees.append(payload)
    return record | {"status": "invariant", "trees": trees}
