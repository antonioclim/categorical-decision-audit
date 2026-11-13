"""Standard-library verifier for Paper M's finite split-cover certificates.

The caller supplies the trusted case and requested endpoint. The checker
reconstructs every change scenario and its integer inequalities. It uses no
producer, oracle, optimiser or native solver.
"""

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


RUN_COUNT = 4
DEPTH = 10
TOP_K = 3
GRADES = (0, 1, 2, 3)
WEIGHTS = ((0, 0, 1, 1), (0, 1, 2, 3))
ENDPOINTS = ("set", "prefix")
SCENARIOS = tuple((a, b) for a in range(RUN_COUNT) for b in range(RUN_COUNT) if a != b)
NODE_CAP = 4096
RECORD_BYTES_CAP = 1_048_576
CASE_FILE_BYTES_CAP = 16_777_216
COMMON_FIELDS = {"case_sha256", "case_id", "endpoint", "status"}


class InvalidProof(ValueError):
    """A failure to establish the supplied claim."""


@dataclass
class Counts:
    nodes: int = 0
    leaves: int = 0
    splits: int = 0
    max_depth: int = 0
    rows_in_leaves: int = 0
    scenarios: int = 0


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidProof(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _reject_constant(text):
    raise InvalidProof(f"invalid_json_constant:{text}")


def _bounded_int(text):
    if len(text) > 128:
        raise InvalidProof("json_integer_digit_budget_exceeded")
    return int(text)


def _finite_float(text):
    number = float(text)
    if not math.isfinite(number):
        raise InvalidProof("invalid_json_nonfinite_float")
    return number


def parse_json(value, *, max_bytes=RECORD_BYTES_CAP):
    """Parse UTF-8 JSON, rejecting duplicate object keys and nonfinite literals."""
    try:
        raw = value.encode("utf-8") if isinstance(value, str) else value
        if not isinstance(raw, bytes):
            raise InvalidProof("expected_json_bytes_or_string")
        if len(raw) > max_bytes:
            raise InvalidProof("json_byte_budget_exceeded")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant, parse_int=_bounded_int, parse_float=_finite_float)
    except InvalidProof:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidProof("invalid_utf8_json_or_excessive_nesting") from exc


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def case_sha256(case):
    return hashlib.sha256(canonical_bytes(case)).hexdigest()


def _is_name(value):
    return type(value) is str and bool(value)


def _is_grade(value):
    return type(value) is int and value in GRADES


def _prepare(case):
    if type(case) is not dict or not _is_name(case.get("id")):
        raise InvalidProof("invalid_case_id")
    runs, known, unknown = case.get("runs"), case.get("known"), case.get("unknown")
    if type(runs) is not dict or len(runs) != RUN_COUNT or not all(_is_name(name) for name in runs):
        raise InvalidProof("invalid_run_set")
    for docs in runs.values():
        if type(docs) is not list or len(docs) != DEPTH or not all(_is_name(doc) for doc in docs):
            raise InvalidProof("invalid_run_documents_or_depth")
        if len(set(docs)) != DEPTH:
            raise InvalidProof("duplicate_passage_in_run")
    if type(known) is not dict or not all(_is_name(doc) and _is_grade(grade) for doc, grade in known.items()):
        raise InvalidProof("invalid_known_grades")
    if type(unknown) is not list or not all(_is_name(doc) for doc in unknown):
        raise InvalidProof("invalid_unknown_passages")
    missing = set(unknown)
    if len(missing) != len(unknown) or missing.intersection(known):
        raise InvalidProof("known_unknown_overlap_or_duplicate")
    ordered = tuple(frozenset(runs[name]) for name in sorted(runs))
    if missing.union(known) != frozenset().union(*ordered):
        raise InvalidProof("known_unknown_do_not_partition_case")
    # Grade 0 for every missing passage is feasible. There are no extra
    # constraints in this schema, so universal checks have a nonempty domain.
    return ordered, known, missing


def _pair_rows(ordered, known):
    rows = {}
    for profile, weights in enumerate(WEIGHTS):
        for left, right in SCENARIOS:
            left_only = ordered[left].difference(ordered[right])
            right_only = ordered[right].difference(ordered[left])
            constant = 0
            values = {}
            for sign, passages in ((1, left_only), (-1, right_only)):
                for passage in passages:
                    if passage in known:
                        constant += sign * weights[known[passage]]
                    else:
                        values[passage] = tuple(sign * value for value in weights)
            # The lexically earlier run wins equal scores. The later run
            # needs a strictly positive integer score difference.
            rhs = int(left > right)
            rows[profile, left, right] = constant, rhs, values
    return rows


def _scenario_rows(pair_rows, endpoint, a, b):
    if endpoint == "prefix":
        return pair_rows[0, a, b], pair_rows[1, b, a]
    binary = tuple(pair_rows[0, other, a] for other in range(RUN_COUNT) if other != a)
    graded = tuple(pair_rows[1, other, b] for other in range(RUN_COUNT) if other != b)
    return binary + graded


def _combined_rows(rows, subset):
    constant, rhs = 0, 0
    values = {}
    for index in subset:
        row_const, row_rhs, row_values = rows[index]
        constant += row_const
        rhs += row_rhs
        for passage, contribution in row_values.items():
            totals = values.setdefault(passage, [0, 0, 0, 0])
            for grade in GRADES:
                totals[grade] += contribution[grade]
    # Maximisation is per shared unknown, *after* summing all selected rows.
    # This retains coupling even when one row uses the other profile.
    return constant, rhs, [(passage, contribution, max(contribution)) for passage, contribution in values.items()]


def _check_tree(node, rows, missing, assigned, cache, counts):
    counts.nodes += 1
    if counts.nodes > NODE_CAP:
        raise InvalidProof("proof_node_budget_exceeded")
    counts.max_depth = max(counts.max_depth, len(assigned))
    if type(node) is not dict:
        raise InvalidProof("node_must_be_object")
    fields = set(node)
    if fields == {"subset"}:
        subset = node["subset"]
        if (type(subset) is not list or not subset or len(subset) > len(rows)
                or not all(type(index) is int and 0 <= index < len(rows) for index in subset)
                or any(a >= b for a, b in zip(subset, subset[1:]))):
            raise InvalidProof("invalid_leaf_subset")
        key = tuple(subset)
        if key not in cache:
            cache[key] = _combined_rows(rows, subset)
        constant, rhs, terms = cache[key]
        maximum = constant + sum(contribution[assigned[p]] if p in assigned else cap
                                 for p, contribution, cap in terms)
        counts.leaves += 1
        counts.rows_in_leaves += len(subset)
        if maximum >= rhs:
            raise InvalidProof("leaf_does_not_establish_contradiction")
        return
    if fields != {"split", "children"}:
        raise InvalidProof("invalid_node_fields")
    passage, children = node["split"], node["children"]
    if not _is_name(passage) or passage not in missing:
        raise InvalidProof("split_passage_not_unknown")
    if passage in assigned:
        raise InvalidProof("repeated_split_passage_on_path")
    if len(assigned) >= len(missing):
        raise InvalidProof("split_depth_exceeds_unknown_count")
    if type(children) is not list or len(children) != len(GRADES):
        raise InvalidProof("split_must_cover_four_grades")
    counts.splits += 1
    for grade in GRADES:
        assigned[passage] = grade
        _check_tree(children[grade], rows, missing, assigned, cache, counts)
    del assigned[passage]


def _check_witness(witness, ordered, known, missing, endpoint):
    if type(witness) is not dict or set(witness) != missing or not all(_is_grade(grade) for grade in witness.values()):
        raise InvalidProof("witness_does_not_assign_exactly_the_unknown_grades")
    completion = known | witness
    prefixes = []
    for weights in WEIGHTS:
        scores = [sum(weights[completion[passage]] for passage in run) for run in ordered]
        prefixes.append(tuple(sorted(range(RUN_COUNT), key=lambda index: (-scores[index], index))[:TOP_K]))
    first, second = prefixes
    changes = set(first) != set(second) if endpoint == "set" else first != second
    if not changes:
        raise InvalidProof("witness_does_not_change_requested_endpoint")


def verify(case, endpoint, record):
    """Reverify the bound claim. For raw JSON, call parse_json first."""
    counts = Counts()
    status = record.get("status") if type(record) is dict else None
    route = "binding"
    try:
        if endpoint not in ENDPOINTS:
            raise InvalidProof("invalid_expected_endpoint")
        ordered, known, missing = _prepare(case)
        if type(record) is not dict:
            raise InvalidProof("record_must_be_object")
        if (record.get("case_id") != case["id"] or record.get("case_sha256") != case_sha256(case)
                or record.get("endpoint") != endpoint):
            raise InvalidProof("case_or_endpoint_binding_mismatch")
        if status == "changed":
            route = "witness"
            if set(record) != COMMON_FIELDS | {"witness"}:
                raise InvalidProof("invalid_changed_record_fields")
            _check_witness(record["witness"], ordered, known, missing, endpoint)
        elif status == "invariant":
            route = "split_cover"
            if set(record) != COMMON_FIELDS | {"trees"}:
                raise InvalidProof("invalid_invariant_record_fields")
            trees = record["trees"]
            if type(trees) is not list or len(trees) != len(SCENARIOS):
                raise InvalidProof("twelve_scenario_trees_required")
            pair_rows = _pair_rows(ordered, known)
            for tree, (a, b) in zip(trees, SCENARIOS):
                rows = _scenario_rows(pair_rows, endpoint, a, b)
                _check_tree(tree, rows, missing, {}, {}, counts)
                counts.scenarios += 1
        elif status == "unknown":
            route = "abstention"
            if set(record) != COMMON_FIELDS | {"reason"} or not _is_name(record["reason"]):
                raise InvalidProof("invalid_unknown_record")
            return {"state": "unresolved", "accepted": False, "status": status,
                    "route": route, "reason": record["reason"]}
        else:
            raise InvalidProof("unknown_claim_status")
        record_bytes = len(canonical_bytes(record))
        if record_bytes > RECORD_BYTES_CAP:
            raise InvalidProof("record_byte_budget_exceeded")
        return {"state": "verified", "accepted": True, "status": status, "route": route,
                "record_bytes": record_bytes, **vars(counts)}
    except InvalidProof as exc:
        return {"state": "rejected", "accepted": False, "status": status, "route": route,
                "reason": str(exc), **vars(counts)}
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return {"state": "rejected", "accepted": False, "status": None, "route": route,
                "reason": "noncanonical_or_malformed_json_values", **vars(counts)}


def _read_bounded(path, limit):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise InvalidProof("file_byte_budget_exceeded")
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="trusted single case or case list")
    parser.add_argument("--cases-sha256", required=True, help="expected byte hash of the trusted case file")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--endpoint", choices=ENDPOINTS, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw_cases = _read_bounded(args.cases, CASE_FILE_BYTES_CAP)
        if hashlib.sha256(raw_cases).hexdigest() != args.cases_sha256:
            raise InvalidProof("trusted_case_file_digest_mismatch")
        cases = parse_json(raw_cases, max_bytes=CASE_FILE_BYTES_CAP)
        if type(cases) is dict:
            cases = [cases]
        if type(cases) is not list or not all(type(case) is dict and _is_name(case.get("id")) for case in cases):
            raise InvalidProof("invalid_case_file_shape")
        by_id = {case["id"]: case for case in cases}
        if len(by_id) != len(cases) or args.case_id not in by_id:
            raise InvalidProof("missing_or_duplicate_case_id")
        record = parse_json(_read_bounded(args.record, RECORD_BYTES_CAP))
        result = verify(by_id[args.case_id], args.endpoint, record)
    except (InvalidProof, OSError) as exc:
        result = {"state": "rejected", "accepted": False, "route": "input", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
