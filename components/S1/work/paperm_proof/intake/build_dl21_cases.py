#!/usr/bin/env python3
"""Freeze the DL21 proof-test inputs, deriving RRF from retrieval ranks only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin

INTAKE = Path(__file__).resolve().parent
WORK = INTAKE.parents[1]
SOURCE = INTAKE / "dl21_candidates"
COMMIT = "5051b8d7225d257ce0f892e1069a2e5ac45d8496"
ORIGINAL_RUNS = ("BM25", "BM25_RM3", "SPLADE_P_P_ENSEMBLE_DISTIL")
RUNS = tuple(sorted((*ORIGINAL_RUNS, "RRF_60")))
ALIAS_MAP = {name: name for name in ORIGINAL_RUNS} | {"RRF_60": "D_BERT_KD_TASB"}
QRELS = "2021.qrels.pass.final.txt"
SOURCE_PAGE = "nist_dl21.html"
RUN_DEPTH = 100
TEST_DEPTH = 10
RRF_CONSTANT = 60
MASK_LIMIT = 3
MASK_SALT = "DL21-IPM-v1"


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and (href := dict(attrs).get("href")):
            self.hrefs.append(href)


def passage_key(pid: str) -> tuple[int, int, str]:
    matched = re.fullmatch(r"msmarco_passage_(\d+)_(\d+)", pid)
    if not matched:
        raise ValueError(f"invalid MS MARCO v2 passage identifier: {pid!r}")
    shard, offset = matched.groups()
    return int(shard), int(offset), pid


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def description(path: Path) -> dict:
    data = path.read_bytes()
    return {"file": path.name, "bytes": len(data), "sha256": sha256(data).hexdigest()}


def get_sources() -> tuple[dict[str, bytes], dict[str, dict]]:
    raw_receipt = json.loads((INTAKE / "dl21_candidate_receipt.json").read_text())
    if raw_receipt["castorini_commit"] != COMMIT:
        raise ValueError("Castorini commit differs from fixed source")
    inputs: dict[str, bytes] = {}
    receipts: dict[str, dict] = {}
    for name in (SOURCE_PAGE, QRELS, *(f"{run}.txt" for run in ORIGINAL_RUNS)):
        data = (SOURCE / name).read_bytes()
        record = raw_receipt["files"][name]
        if record["http_status"] != 200 or len(data) != record["bytes"] or sha256(data).hexdigest() != record["sha256"]:
            raise ValueError(f"source receipt differs for {name}")
        if name not in (QRELS, SOURCE_PAGE) and f"/{COMMIT}/" not in record["url"]:
            raise ValueError(f"unfrozen run source for {name}")
        inputs[name], receipts[name] = data, record
    page = Links()
    page.feed(inputs[SOURCE_PAGE].decode("utf-8"))
    listed_links = {urljoin(receipts[SOURCE_PAGE]["resolved_url"], href) for href in page.hrefs}
    if receipts[QRELS]["url"] not in listed_links:
        raise ValueError("official NIST page does not link this qrels endpoint")
    return inputs, receipts


def read_qrels(raw: bytes) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = defaultdict(dict)
    for line in raw.decode("ascii").splitlines():
        qid, _, pid, grade = line.split()
        passage_key(pid)
        if not qid.isdecimal() or grade not in {"0", "1", "2", "3"} or pid in results[qid]:
            raise ValueError(f"invalid or duplicate qrel at query {qid!r}")
        results[qid][pid] = int(grade)
    if not results:
        raise ValueError("qrels are empty")
    return results


def read_run(raw: bytes, qids: set[str]) -> dict[str, list[str]]:
    results: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for line in raw.decode("ascii").splitlines():
        qid, _, pid, rank, _ignored_score, _ = line.split()
        passage_key(pid)
        results[qid].append((int(rank), pid))
    if set(results) != qids:
        raise ValueError("run and qrels query identifiers differ")
    ranked = {}
    for qid, pairs in results.items():
        pairs.sort()
        passages = [pid for _, pid in pairs]
        if [rank for rank, _ in pairs] != list(range(1, RUN_DEPTH + 1)) or len(set(passages)) != RUN_DEPTH:
            raise ValueError(f"run does not have unique passages and full ranks at query {qid!r}")
        ranked[qid] = passages
    return ranked


def check_historical_qids(qids: set[str]) -> dict:
    old = {
        "DL19": (
            WORK / "paperm_revision/holdout/inputs/2019qrels-pass.txt",
            WORK / "paperm_revision/holdout/inputs/dl19_input_eligibility.json",
        ),
        "DL20": (
            WORK / "ipm/literature/dl20_qrels.txt",
            WORK / "dl20_pilot/dl20_input_eligibility.json",
        ),
    }
    evidence = {}
    for name, (path, manifest) in old.items():
        expected = json.loads(manifest.read_text())["qrels"]["sha256"]
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != expected:
            raise ValueError(f"{name} reference qrels do not match their receipt")
        old_ids = {line.split()[0] for line in raw.decode("ascii").splitlines()}
        common = qids.intersection(old_ids)
        if common:
            raise ValueError(f"DL21 overlaps judged query IDs with {name}")
        evidence[name] = {"qrels_sha256": expected, "judged_queries": len(old_ids), "overlap": 0}
    return evidence


def rrf(qid: str, base: dict[str, dict[str, list[str]]]) -> list[dict]:
    values: dict[str, Fraction] = defaultdict(Fraction)
    ranks: dict[str, dict[str, int]] = defaultdict(dict)
    for name in ORIGINAL_RUNS:
        for rank, pid in enumerate(base[name][qid], 1):
            values[pid] += Fraction(1, RRF_CONSTANT + rank)
            ranks[pid][name] = rank
    ordered = sorted(values, key=lambda pid: (-values[pid], passage_key(pid)))[:TEST_DEPTH]
    return [
        {"pid": pid, "rank": rank, "rrf_score": [values[pid].numerator, values[pid].denominator], "source_ranks": ranks[pid]}
        for rank, pid in enumerate(ordered, 1)
    ]


def make_cases(qrels: dict[str, dict[str, int]], base: dict[str, dict[str, list[str]]]) -> tuple[list, dict, dict, dict]:
    cases = []
    withheld = {}
    fused_runs = {}
    missing_histogram: Counter = Counter()
    masked_histogram: Counter = Counter()
    missing_multiplicity: Counter = Counter()
    observed_shared_histogram: Counter = Counter()
    counts: Counter = Counter()
    distinct_configurations_in_top10 = 0
    for qid in sorted(qrels, key=int):
        fused = rrf(qid, base)
        fused_runs[qid] = fused
        listings = {name: base[name][qid][:TEST_DEPTH] for name in ORIGINAL_RUNS}
        listings["RRF_60"] = [record["pid"] for record in fused]
        if any(len(pids) != TEST_DEPTH or len(set(pids)) != TEST_DEPTH for pids in listings.values()):
            raise ValueError(f"non-distinct top 10 for query {qid}")
        if len({tuple(pids) for pids in listings.values()}) == len(RUNS):
            distinct_configurations_in_top10 += 1
        incidence = Counter(pid for pids in listings.values() for pid in pids)
        known = {pid: qrels[qid][pid] for pid in incidence if pid in qrels[qid]}
        unknown = sorted(set(incidence).difference(known), key=passage_key)
        missing_histogram[len(unknown)] += 1
        missing_multiplicity.update(incidence[pid] for pid in unknown)
        stratum = "natural" if unknown else "observed"
        cases.append({"id": f"{stratum}:{qid}", "stratum": stratum, "qid": qid, "runs": listings, "known": known, "unknown": unknown})
        counts[stratum] += 1
        if not unknown:
            eligible = [pid for pid, multiplicity in incidence.items() if multiplicity >= 2]
            eligible.sort(key=lambda pid: (sha256(f"{MASK_SALT}|{qid}|{pid}".encode("utf-8")).digest(), passage_key(pid)))
            masked = eligible[:MASK_LIMIT]
            observed_shared_histogram[len(eligible)] += 1
            masked_histogram[len(masked)] += 1
            case_id = f"masked:{qid}"
            cases.append({"id": case_id, "stratum": "masked", "qid": qid, "runs": listings, "known": {pid: grade for pid, grade in known.items() if pid not in masked}, "unknown": masked})
            withheld[case_id] = {pid: known[pid] for pid in masked}
            counts["masked"] += 1
    for index, name in enumerate(RUNS):
        for prior in RUNS[:index]:
            if all(c["runs"][prior] == c["runs"][name] for c in cases):
                raise ValueError(f"duplicated run configurations: {prior} and {name}")
    cases.sort(key=lambda case: (("observed", "natural", "masked").index(case["stratum"]), int(case["qid"])))
    structure = {
        "stratum_counts": dict(counts),
        "natural_unknown_count_histogram_including_complete": dict(sorted(missing_histogram.items())),
        "natural_unknown_query_passage_pairs_by_multiplicity": dict(sorted(missing_multiplicity.items())),
        "masked_unknown_count_histogram": dict(sorted(masked_histogram.items())),
        "complete_queries_shared_judged_candidate_histogram": dict(sorted(observed_shared_histogram.items())),
        "queries_with_four_distinct_ordered_top10s": distinct_configurations_in_top10,
        "each_configuration_distinct_somewhere": True,
    }
    return cases, withheld, fused_runs, structure


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir
    if out.exists():
        raise SystemExit("output directory must be new, to preserve the previous freeze")
    sources, receipts = get_sources()
    qrels = read_qrels(sources[QRELS])
    qids = set(qrels)
    disjointness = check_historical_qids(qids)
    ranks = {name: read_run(sources[f"{name}.txt"], qids) for name in ORIGINAL_RUNS}
    cases, withheld, fused, structure = make_cases(qrels, ranks)
    if sorted(ALIAS_MAP, key=ALIAS_MAP.get) != list(RUNS):
        raise ValueError("legacy aliases do not preserve source identifier order")
    out.mkdir(parents=True)
    raw = out / "source_inputs"
    raw.mkdir()
    for name, data in sources.items():
        (raw / name).write_bytes(data)
    generated = {
        "cases.json": cases,
        "masked_truth_oracle_only.json": withheld,
        "RRF_60_top10.json": fused,
        "run_aliases.json": {"real_to_legacy": ALIAS_MAP, "real_run_order": list(RUNS)},
    }
    for name, data in generated.items():
        (out / name).write_bytes(canonical_bytes(data))
    manifest = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_basis": "structural availability and eligibility before any relevance outcomes",
        "track": "TREC 2021 Deep Learning Track, Passage Ranking, official final graded qrels",
        "repo_commit": COMMIT,
        "inputs": receipts,
        "qrels": {"judged_queries": len(qrels), "judgements": sum(map(len, qrels.values())), "grade_counts": dict(sorted(Counter(grade for block in qrels.values() for grade in block.values()).items()))},
        "base_runs": {name: {"rows": len(ranks[name]) * RUN_DEPTH, "queries": len(ranks[name]), "source_rank_depth": RUN_DEPTH, "all_qrels_qids_have_distinct_top10": True} for name in ORIGINAL_RUNS},
        "rrf_60": {"rank_only": True, "dependent_on": list(ORIGINAL_RUNS), "score": "exact sum 1/(60+source rank) over containing runs", "tie": "ascending numeric shard, then numeric offset, then literal source identifier", "derived_top_depth": TEST_DEPTH, "qrels_used_for_fusion": False},
        "masking": {"salt": MASK_SALT, "selection": "up to 3 shared judged passages per fully judged query, ascending SHA-256 of UTF-8 literal salt|qid|pid", "truth_file": "masked_truth_oracle_only.json", "casewise_processing_required": True},
        "test_depth": TEST_DEPTH,
        "structural_eligibility": structure,
        "disjointness": disjointness,
        "generated": {name: description(out / name) for name in generated},
        "preparation_code": description(Path(__file__)),
        "access": {"nist_and_github_http_200_verified": True, "castorini_run_redistribution_licence": "unknown, no explicit licence in source data repository metadata", "reuse": "reference links and hashes unless permission is verified"},
        "scope": "Constructed cases and rank-only RRF. No relevance scoring, shortlist comparison or solver outcomes evaluated.",
    }
    (out / "freeze.json").write_bytes(canonical_bytes(manifest))
    print(json.dumps({"cases": len(cases), "case_sha256": manifest["generated"]["cases.json"]["sha256"], "structure": structure}, indent=2))


if __name__ == "__main__":
    main()
