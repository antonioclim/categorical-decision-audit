"""Replay controlled changes to archived, independently accepted certificates."""

import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from check_proof import CASE_FILE_BYTES_CAP, InvalidProof, canonical_bytes, parse_json, verify


ENDPOINTS = ("set", "prefix")
STATUSES = ("changed", "invariant")
LIMIT_PER_GROUP = 3


def digest(raw):
    return sha256(raw).hexdigest()


def inspect(case, endpoint, raw):
    try:
        return verify(case, endpoint, parse_json(raw))
    except InvalidProof as error:
        return {"state": "rejected", "accepted": False, "reason": str(error)}


def first_split(trees):
    # A non-leaf tree starts with a split, so only its root is needed.
    return next((tree for tree in trees if "children" in tree), None)


def split_mutations(case, record):
    incomplete = deepcopy(record)
    del first_split(incomplete["trees"])["children"][-1]
    yield "missing_grade_branch", case, canonical_bytes(incomplete), "split_must_cover_four_grades"

    if case["known"]:
        invalid = deepcopy(record)
        first_split(invalid["trees"])["split"] = min(case["known"])
        yield "split_on_known_grade", case, canonical_bytes(invalid), "split_passage_not_unknown"


def mutations(case, endpoint, record, wire):
    old_hash = record["case_sha256"]
    changed_hash = ("1" if old_hash[0] == "0" else "0") + old_hash[1:]
    yield "case_hash", case, canonical_bytes(record | {"case_sha256": changed_hash}), "case_or_endpoint_binding_mismatch"

    other_endpoint = next(name for name in ENDPOINTS if name != endpoint)
    yield "endpoint", case, canonical_bytes(record | {"endpoint": other_endpoint}), "case_or_endpoint_binding_mismatch"

    if case["known"]:
        known = case["known"].copy()
        first_known = min(known)
        known[first_known] = (known[first_known] + 1) % 4
        yield "trusted_case_known_grade", case | {"known": known}, wire, "case_or_endpoint_binding_mismatch"

    duplicate = b'{"status":"' + record["status"].encode("ascii") + b'",' + wire[1:]
    yield "duplicate_status_key", case, duplicate, "duplicate_json_key:status"

    common = {key: record[key] for key in ("case_sha256", "case_id", "endpoint")}
    if record["status"] == "invariant":
        yield ("missing_scenario", case, canonical_bytes(record | {"trees": record["trees"][:-1]}),
               "twelve_scenario_trees_required")

        alternative = common | {"status": "changed", "witness": dict.fromkeys(case["unknown"], 0)}
        yield "false_changed_with_feasible_grades", case, canonical_bytes(alternative), "witness_does_not_change_requested_endpoint"
    else:
        alternative = common | {"status": "invariant", "trees": [{"subset": [0]} for _ in range(12)]}
        yield "false_invariant_with_complete_shape", case, canonical_bytes(alternative), "leaf_does_not_establish_contradiction"

        witness = record["witness"].copy()
        if witness:
            witness[min(witness)] = 4
        else:
            # A known passage is necessarily outside the witness domain.
            witness[min(case["known"])] = 0
        yield ("invalid_witness_grade_or_domain", case, canonical_bytes(record | {"witness": witness}),
               "witness_does_not_assign_exactly_the_unknown_grades")


def replay(cases_path, benchmark_dir, expected_digest):
    summary_raw = (benchmark_dir / "summary.json").read_bytes()
    summary = json.loads(summary_raw)
    metadata = summary["metadata"]
    cases_raw = cases_path.read_bytes()
    checker_hash = digest(Path(__file__).with_name("check_proof.py").read_bytes())
    if digest(cases_raw) != expected_digest or metadata["cases_sha256"] != expected_digest:
        raise ValueError("case source must match both the frozen digest and completed benchmark")
    if metadata["sources_sha256"]["check_proof.py"] != checker_hash:
        raise ValueError("checker source differs from the benchmark")
    if not metadata["external"]:
        raise ValueError("a completed external benchmark is required")
    cases = parse_json(cases_raw, max_bytes=CASE_FILE_BYTES_CAP)
    rows = json.loads((benchmark_dir / "benchmark.json").read_bytes())
    if len(cases) != metadata["cases"] or len(rows) != len(cases) * len(ENDPOINTS):
        raise ValueError("benchmark does not cover the frozen cases and endpoints")
    counts = Counter()
    records = []
    split_sampled = False
    for index, case in enumerate(cases):
        for offset, endpoint in enumerate(ENDPOINTS):
            row = rows[index * len(ENDPOINTS) + offset]
            if row["case_id"] != case["id"] or row["endpoint"] != endpoint:
                raise ValueError("benchmark request order differs from the frozen cases")
            proof_arm = row["arms"]["proof"]
            original = proof_arm["repetitions"][0]
            status = proof_arm["status"]
            group = (endpoint, status)
            if status not in STATUSES or not original["verifier_accepted"]:
                continue
            group_sample = counts[group] < LIMIT_PER_GROUP
            split_sample = not split_sampled and original["verdict"]["splits"] > 0
            if not group_sample and not split_sample:
                continue
            wire = (benchmark_dir / "proofs" / f"{index:03d}_{endpoint}.json").read_bytes()
            if digest(wire) != original["certificate_sha256"]:
                raise ValueError("archived proof differs from benchmark")
            record = parse_json(wire)
            base = verify(case, endpoint, record)
            if not base["accepted"] or base["status"] != status:
                raise ValueError("archived positive certificate failed verification")
            selected = []
            if group_sample:
                counts[group] += 1
                selected.extend(mutations(case, endpoint, record, wire))
            if split_sample:
                split_sampled = True
                selected.extend(split_mutations(case, record))
            outcomes = []
            for name, trusted_case, altered, expected in selected:
                result = inspect(trusted_case, endpoint, altered)
                outcomes.append({"mutation": name, "expected_reason": expected, "result": result["state"],
                                 "reason": result.get("reason"), "passed": result["state"] == "rejected"
                                 and result.get("reason") == expected})
            records.append({"case_index": index, "endpoint": endpoint, "status": status,
                            "certificate_sha256": digest(wire), "split_count": base["splits"],
                            "group_sample": group_sample, "first_split_sample": split_sample, "mutations": outcomes})
    if not records:
        raise ValueError("no archived positive certificates available")
    checks = [outcome for item in records for outcome in item["mutations"]]
    return {"design": "Post-benchmark controlled mutations. First three verified positives per endpoint/status group in frozen order, and the first verified record with a split for branch checks. The selection and replays do not estimate a real-world error or attack rate.",
            "frozen_cases_sha256": expected_digest, "benchmark_summary_sha256": digest(summary_raw),
            "checker_sha256": checker_hash, "originals_verified": len(records), "mutation_checks": len(checks),
            "mutation_checks_passed": sum(outcome["passed"] for outcome in checks),
            "groups": {f"{endpoint}/{status}": counts[endpoint, status]
                       for endpoint in ENDPOINTS for status in STATUSES},
            "mutation_counts": dict(sorted(Counter(outcome["mutation"] for outcome in checks).items())),
            "records": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("benchmark_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cases-sha256", required=True)
    args = parser.parse_args()
    result = replay(args.cases, args.benchmark_dir, args.cases_sha256)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2))
    return 0 if result["mutation_checks"] == result["mutation_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
