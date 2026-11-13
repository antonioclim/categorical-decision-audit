"""Build, check and score blinded DL21 handoff challenges in separate processes."""

import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import random
from statistics import median
import sys

import cryptography
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SEED = 20261110
ENDPOINTS = ("set", "prefix")
STATUSES = ("invariant", "changed")
CONTEXT_FIELDS = ("case_id", "case_sha256", "endpoint", "status")
CASES_SHA = "20cc22dcc68041622b507078d449ceb39b9bfcab2fdc727d31bab3fbcdca732b"
CHECKER_SHA = "b5abb2327344b5ece449ae3e1685c0899e3312952bfd5d3926c7104f8e43509a"
ORACLE_CODE_SHA = "a2df730ce5825c6ae1185f19888eaf403d872c10dd65e58d81e15b047ecbd243"
ARCHIVE_SHA = "1a2856bbab32c4ae59e52f3f094367397d8f3512dbf64d7a8d84f0cf5ae5dc08"
ARMS = (
    "bare", "bare_resolve", "bound", "bound_resolve",
    "signed_bound", "signed_bound_resolve", "evidence",
)
FAULTS = (
    "clean", "case_swap_same", "endpoint_swap_same", "endpoint_swap_different",
    "transport_wrong_verdict", "issuer_wrong_verdict", "evidence_only",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def read(path):
    return json.loads(path.read_bytes())


def frozen(archive):
    path = archive / "intake/frozen/cases.json"
    cases_bytes = path.read_bytes()
    require(digest(cases_bytes) == CASES_SHA, "Frozen input digest differs")
    for name, expected in [("check_proof.py", CHECKER_SHA), ("adjudicate_dl21.py", ORACLE_CODE_SHA)]:
        require(digest((archive / name).read_bytes()) == expected, f"Frozen source differs: {name}")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(archive.resolve()))
    from adjudicate_dl21 import outcomes
    from check_proof import verify

    cases = json.loads(cases_bytes)
    require(len(cases) == len({c["id"] for c in cases}) == 90, "Unexpected frozen cohort")
    return cases, outcomes, verify


def exhaust(cases, outcomes):
    worlds = {
        case["id"]: [(values, *outcomes(case, values))
                     for values in product(range(4), repeat=len(case["unknown"]))]
        for case in cases
    }
    require(sum(map(len, worlds.values())) == 3681, "Unexpected completion count")
    statuses = {
        (case["id"], endpoint): "changed" if any(outcome[endpoint] for _, outcome, _ in worlds[case["id"]])
        else "invariant"
        for case in cases for endpoint in ENDPOINTS
    }
    return worlds, statuses


def exact_originals(archive, cases, truth):
    benchmark = archive / "benchmark_dl21"
    measured = read(benchmark / "benchmark.json")
    records, hashes = {}, []
    for index, case in enumerate(cases):
        for offset, endpoint in enumerate(ENDPOINTS):
            key = (case["id"], endpoint)
            row = measured[index * 2 + offset]
            path = benchmark / "proofs" / f"{index:03d}_{endpoint}.json"
            raw = path.read_bytes()
            record = json.loads(raw)
            expected = row["arms"]["proof"]["repetitions"][0]["certificate_sha256"]
            require(digest(raw) == expected, f"Proof bytes differ: {path}")
            require((row["case_id"], row["endpoint"]) == key, f"Benchmark request differs: {key}")
            require(row["arms"]["incidence_exact"]["status"] == truth[key] == record["status"],
                    f"Independent exact verdict disagrees: {key}")
            require(record["case_sha256"] == digest(wire(case)), f"Frozen case digest differs: {key}")
            records[key] = record
            hashes.append(digest(raw))
    require(digest("".join(hashes).encode()) == ARCHIVE_SHA, "Archive manifest differs")
    return records


def signed_payload(record, signer, signature=None):
    bound = {field: record[field] for field in CONTEXT_FIELDS}
    return {
        "bare": record["status"], "bound": bound, "evidence": record,
        "signature": signature if signature is not None else signer.sign(wire(bound)).hex(),
    }


def wrong_verdict(record, case):
    context = {field: record[field] for field in CONTEXT_FIELDS}
    if record["status"] == "changed":
        return context | {"status": "invariant", "trees": [{"subset": [0]} for _ in range(12)]}
    return context | {"status": "changed", "witness": dict.fromkeys(case["unknown"], 0)}


def first_true_scenario_row(case, endpoint, worlds):
    """Find a single row that cannot be a root refutation using direct scores."""
    run_names = sorted(case["runs"])
    scenarios = [(a, b) for a in run_names for b in run_names if a != b]
    for index, (a, b) in enumerate(scenarios):
        if endpoint == "prefix":
            rows = [(0, a, b), (1, b, a)]
        else:
            rows = [(0, c, a) for c in run_names if c != a]
            rows += [(1, c, b) for c in run_names if c != b]
        for row, (profile, left, right) in enumerate(rows):
            for values, _, scores in worlds:
                totals = scores[profile]
                if (-totals[left], left) < (-totals[right], right):
                    return index, row, values
    raise ValueError(f"No satisfiable single scenario row: {case['id']} {endpoint}")


def corrupt_evidence(record, case, worlds):
    if record["status"] == "changed":
        for values, outcomes, _ in worlds:
            if not outcomes[record["endpoint"]]:
                return record | {"witness": dict(zip(case["unknown"], values))}, {
                    "feasible_nonchanging_witness": dict(zip(case["unknown"], values)),
                }
        return None
    index, row, values = first_true_scenario_row(case, record["endpoint"], worlds)
    corrupt = deepcopy(record)
    corrupt["trees"][index] = {"subset": [row]}
    require(corrupt != record, "Semantic fault must alter the proof")
    return corrupt, {"scenario": index, "row": row, "feasible_row_witness": dict(zip(case["unknown"], values))}


def build(archive, output):
    cases, outcomes, _ = frozen(archive)
    worlds, truth = exhaust(cases, outcomes)
    records = exact_originals(archive, cases, truth)
    qid_by_case = {case["id"]: case["qid"] for case in cases}
    signer = Ed25519PrivateKey.from_private_bytes(sha256(b"Paper M DL21 deterministic test key v1").digest())
    public_key = signer.public_key().public_bytes_raw().hex()
    challenges = []
    for case in cases:
        case_id = case["id"]
        for endpoint in ENDPOINTS:
            key = (case_id, endpoint)
            record = records[key]
            original = signed_payload(record, signer)
            other_endpoint = next(item for item in ENDPOINTS if item != endpoint)
            candidates = [candidate for candidate in records
                          if candidate[1] == endpoint and truth[candidate] == truth[key]
                          and qid_by_case[candidate[0]] != case["qid"]]
            require(candidates, f"No matched donor for {key}")
            donor = min(candidates, key=lambda c: digest(wire([SEED, *key, c[0]])))
            endpoint_record = records[case_id, other_endpoint]
            endpoint_fault = "endpoint_swap_same" if endpoint_record["status"] == truth[key] else "endpoint_swap_different"
            false_record = wrong_verdict(record, case)
            variants = [
                ("clean", original, {}),
                ("case_swap_same", signed_payload(records[donor], signer), {"donor": donor}),
                (endpoint_fault, signed_payload(endpoint_record, signer), {"donor": (case_id, other_endpoint)}),
                ("transport_wrong_verdict", signed_payload(false_record, signer, original["signature"]), {}),
                ("issuer_wrong_verdict", signed_payload(false_record, signer), {}),
            ]
            semantic_fault = corrupt_evidence(record, case, worlds[case_id])
            if semantic_fault is not None:
                altered, details = semantic_fault
                variants.append(("evidence_only", original | {"evidence": altered}, details))
            for fault, payload, details in variants:
                request = {"case_id": case_id, "endpoint": endpoint, **payload}
                label = {"fault": fault, "truth": truth[key], **details}
                challenges.append((request, label))
    random.Random(SEED).shuffle(challenges)
    requests, labels = [], {}
    for number, (request, label) in enumerate(challenges, 1):
        token = f"H{number:04d}"
        requests.append({"trial": token, **request})
        labels[token] = label
    save(output / "requests.json", {"public_key": public_key, "requests": requests})
    save(output / "labels.json", labels)
    save(output / "freeze.json", {
        "cases_sha256": CASES_SHA, "checker_sha256": CHECKER_SHA,
        "adjudicator_sha256": ORACLE_CODE_SHA, "archive_manifest_sha256": ARCHIVE_SHA,
        "benchmark_sha256": digest((archive / "benchmark_dl21/benchmark.json").read_bytes()),
        "protocol_sha256": digest(Path(__file__).with_name("Protocol.md").read_bytes()),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "requests_sha256": digest((output / "requests.json").read_bytes()),
        "labels_sha256": digest((output / "labels.json").read_bytes()),
        "seed": SEED, "cases": len(cases), "endpoints": len(records), "trials": len(requests),
        "cryptography": cryptography.__version__, "python": sys.version,
    })
    print(f"Frozen {len(requests)} challenges for {len(records)} original requests")


def signature_passes(public_key, bound, signature):
    try:
        public_key.verify(bytes.fromhex(signature), wire(bound))
        return True
    except (InvalidSignature, ValueError):
        return False


def check(archive, requests_path, result_path):
    cases, outcomes, verify = frozen(archive)
    _, truth = exhaust(cases, outcomes)
    case_lookup = {case["id"]: case for case in cases}
    data = read(requests_path)
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(data["public_key"]))
    results = []
    for request in data["requests"]:
        key = (request["case_id"], request["endpoint"])
        case_id, endpoint = key
        case = case_lookup[case_id]
        bare, bound = request["bare"], request["bound"]
        bare_ok = bare in STATUSES
        expected = {"case_id": case_id, "case_sha256": digest(wire(case)), "endpoint": endpoint}
        bound_ok = (set(bound) == set(CONTEXT_FIELDS) and bound["status"] in STATUSES
                    and all(bound[k] == v for k, v in expected.items()))
        signature_ok = signature_passes(public_key, bound, request["signature"])
        proof_result = verify(case, endpoint, request["evidence"])
        results.append({
            "trial": request["trial"],
            "accepted": {
                "bare": bare_ok,
                "bare_resolve": bare_ok and bare == truth[key],
                "bound": bound_ok,
                "bound_resolve": bound_ok and bound["status"] == truth[key],
                "signed_bound": bound_ok and signature_ok,
                "signed_bound_resolve": bound_ok and signature_ok and bound["status"] == truth[key],
                "evidence": proof_result["accepted"],
            },
            "evidence_route": proof_result["route"],
            "evidence_reason": proof_result.get("reason"),
            "signature_valid": signature_ok,
            "resolved_status": truth[key],
            "artifact_bytes": {
                "bare": len(wire(bare)), "bound": len(wire(bound)),
                "signed_bound": len(wire({"claim": bound, "signature": request["signature"]})),
                "evidence": len(wire(request["evidence"])),
            },
        })
    save(result_path, {"requests_sha256": digest(requests_path.read_bytes()), "results": results})
    print(f"Checked {len(results)} challenges without reading fault labels")


def score(output):
    freeze = read(output / "freeze.json")
    for name in ("requests", "labels"):
        require(digest((output / f"{name}.json").read_bytes()) == freeze[f"{name}_sha256"],
                f"Frozen {name} digest differs")
    labels = read(output / "labels.json")
    checked = read(output / "blind_results.json")
    require(checked["requests_sha256"] == freeze["requests_sha256"], "Checker ran a different challenge")
    result_by_id = {row["trial"]: row for row in checked["results"]}
    require(len(result_by_id) == len(checked["results"]) == len(labels) and set(result_by_id) == set(labels),
            "Missing, duplicated or unknown trials")
    require(all(result_by_id[token]["resolved_status"] == label["truth"] for token, label in labels.items()),
            "Independent truth recomputation differs")
    table = {}
    for fault in FAULTS:
        rows = [result_by_id[token] for token, label in labels.items() if label["fault"] == fault]
        require(rows, f"No trials for {fault}")
        table[fault] = {
            "trials": len(rows), "rejected": {arm: sum(not row["accepted"][arm] for row in rows) for arm in ARMS},
            "evidence_reasons": dict(Counter(row["evidence_reason"] for row in rows if row["evidence_reason"])),
            "valid_signatures": sum(row["signature_valid"] for row in rows),
        }
    clean = [result_by_id[token] for token, label in labels.items() if label["fault"] == "clean"]
    sizes = {}
    for arm in clean[0]["artifact_bytes"]:
        values = [row["artifact_bytes"][arm] for row in clean]
        sizes[arm] = {"min": min(values), "median": median(values), "max": max(values)}
    summary = {"table": table, "clean_artifact_bytes": sizes, "blind_result_sha256": digest(
        (output / "blind_results.json").read_bytes()),
        "evidence_only_eligible_statuses": dict(Counter(
            label["truth"] for label in labels.values() if label["fault"] == "evidence_only")),
    }
    save(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("stage", choices=("build", "check", "score"))
    args = parser.parse_args()
    if args.stage == "build":
        args.output.mkdir(parents=True)
        build(args.archive, args.output)
    elif args.stage == "check":
        check(args.archive, args.output / "requests.json", args.output / "blind_results.json")
    else:
        score(args.output)


if __name__ == "__main__":
    main()
