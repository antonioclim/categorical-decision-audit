#!/usr/bin/env python3
"""Select a prespecified DL22 slate by judgement presence and incidence only."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
CASTORINI = "https://raw.githubusercontent.com/castorini/rank_llm_data/5051b8d7225d257ce0f892e1069a2e5ac45d8496"
UGA = "https://raw.githubusercontent.com/galuscakova/trec-dl-2022/2d1b63de930ed5098e8309e6e3fafbc2f4de5198"
RERANK = "https://raw.githubusercontent.com/ChuanMeng/reranker-as-judge/4b60970db4ca842fe97a3f43963821272fa36439/output/rq3/runs/runs.bm25-1000--reranker.dl22-passage"
QRELS = ("qrels22.txt", "https://trec.nist.gov/data/deep/2022.qrels.pass.withDupes.txt")
RUNS = {
    "BM25": ("dl22_bm25.txt", f"{CASTORINI}/retrieve_results/BM25/trec_results_dl22_top100.txt"),
    "COLBERT_UGA": ("candidates/uga_colbert.txt", f"{UGA}/test/colbert-test.txt"),
    "MONOT5_3B_BM25": ("candidates/rj_dl22_monot5-3b-msmarco.txt", f"{RERANK}/run.bm25-1000--monot5-3b-msmarco.dl22-passage.txt"),
    "RANK1_14B_BM25": ("candidates/rj_dl22_rank1-14b.txt", f"{RERANK}/run.bm25-1000--rank1-14b.dl22-passage.txt"),
    "RANKLLAMA_13B_BM25": ("candidates/rj_dl22_rankllama-v1-13b-lora-passage.txt", f"{RERANK}/run.bm25-1000--rankllama-v1-13b-lora-passage.dl22-passage.txt"),
    "SPLADE_PP_ED": ("dl22_splade.txt", f"{CASTORINI}/retrieve_results/SPLADE_P_P_ENSEMBLE_DISTIL/trec_results_dl22_top100.txt"),
}
SLATES = {
    "A": ("BM25", "COLBERT_UGA", "MONOT5_3B_BM25", "SPLADE_PP_ED"),
    "B": ("COLBERT_UGA", "MONOT5_3B_BM25", "RANKLLAMA_13B_BM25", "SPLADE_PP_ED"),
    "C": ("MONOT5_3B_BM25", "RANK1_14B_BM25", "RANKLLAMA_13B_BM25", "SPLADE_PP_ED"),
}
OLD_QRELS = {
    "DL19": "paperm_revision/holdout/inputs/2019qrels-pass.txt",
    "DL20": "ipm/literature/dl20_qrels.txt",
    "DL21": "paperm_proof/intake/frozen/source_inputs/2021.qrels.pass.final.txt",
}
DEPTH = 10
MIN_SHARED = 10
PASSAGE = re.compile(r"msmarco_passage_\d+_\d+")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(entry):
    filename, url = entry
    path = HERE / filename
    return {"file": filename, "url": url, "sha256": digest(path), "bytes": path.stat().st_size}


def read_qrels(path):
    results = defaultdict(dict)
    lines = 0
    exact_duplicates = 0
    for line in path.read_text(encoding="ascii").splitlines():
        qid, _iteration, pid, grade = line.split()
        if not qid.isdecimal() or not PASSAGE.fullmatch(pid) or grade not in "0123" or len(grade) != 1:
            raise ValueError(f"Invalid qrel: {line!r}")
        existing = results[qid].get(pid)
        grade = int(grade)
        lines += 1
        if existing is not None:
            if existing != grade:
                raise ValueError(f"Conflicting qrel at {qid}/{pid}")
            exact_duplicates += 1
        results[qid][pid] = grade
    return results, lines, exact_duplicates


def read_run(path, judged_queries):
    ranked = defaultdict(list)
    all_qids = set()
    for line in path.read_text(encoding="ascii").splitlines():
        qid, sentinel, pid, rank, _score, _tag = line.split()
        if not qid.isdecimal() or sentinel != "Q0" or not PASSAGE.fullmatch(pid):
            raise ValueError(f"Invalid run row: {line!r}")
        all_qids.add(qid)
        rank = int(rank)
        if qid in judged_queries and rank <= DEPTH:
            ranked[qid].append((rank, pid))
    usable = {}
    rejected = {}
    for qid, pairs in ranked.items():
        pairs.sort()
        ranks, pids = map(list, zip(*pairs))
        if ranks != list(range(1, DEPTH + 1)) or len(set(pids)) != DEPTH:
            rejected[qid] = {"ranks": ranks, "distinct_pids": len(set(pids))}
        else:
            usable[qid] = pids
    return usable, {"source_query_count": len(all_qids), "eligible_judged_queries": len(usable),
                    "absent_judged_queries": sorted(judged_queries - ranked.keys(), key=int),
                    "ineligible_judged_queries": rejected}


def inspect_slate(names, runs, qrels):
    common = set.intersection(*(set(runs[name]) for name in names))
    counts = Counter()
    shared_mult = Counter()
    missing_hist = Counter()
    cases = []
    for qid in sorted(common, key=int):
        listings = {name: runs[name][qid] for name in sorted(names)}
        incidence = Counter(pid for pids in listings.values() for pid in pids)
        unknown = sorted(pid for pid in incidence if pid not in qrels[qid])
        known = {pid: qrels[qid][pid] for pid in sorted(incidence.keys() - set(unknown))}
        stratum = "natural" if unknown else "observed"
        cases.append({"id": f"{stratum}:{qid}", "stratum": stratum, "qid": qid,
                      "runs": listings, "known": known, "unknown": unknown})
        counts[stratum] += 1
        counts["four_distinct_top10_sets"] += len({frozenset(pids) for pids in listings.values()}) == 4
        counts["natural_shared_queries"] += any(incidence[pid] >= 2 for pid in unknown)
        counts["natural_shared_effective_queries"] += any(2 <= incidence[pid] <= 3 for pid in unknown)
        shared_mult.update(incidence[pid] for pid in unknown)
        missing_hist[len(unknown)] += 1
    return cases, {"runs": names, "query_count": len(cases), "counts": counts,
                   "unjudged_pairs_by_multiplicity": shared_mult, "missing_count_histogram": missing_hist,
                   "coverage_complete": common == qrels.keys(),
                   "excluded_judged_queries": sorted(qrels.keys() - common, key=int)}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    qrels, qrels_lines, duplicates = read_qrels(HERE / QRELS[0])
    overlap = {}
    for name, filename in OLD_QRELS.items():
        old = WORK / filename
        qids = {line.split()[0] for line in old.read_text(encoding="ascii").splitlines()}
        common = qids & qrels.keys()
        if common:
            raise ValueError(f"Overlapping qids {name}: {common}")
        overlap[name] = {"old_qrels_sha256": digest(old), "old_judged_queries": len(qids), "overlap": 0}
    materialized = {}
    run_coverage = {}
    for name, (filename, _url) in RUNS.items():
        if (HERE / filename).is_file():
            materialized[name], run_coverage[name] = read_run(HERE / filename, set(qrels))
    all_structure = {}
    chosen = None
    for tag, names in SLATES.items():
        absent = sorted(set(names) - materialized.keys())
        if absent:
            all_structure[tag] = {"unavailable_runs": absent}
            break
        cases, structure = inspect_slate(names, materialized, qrels)
        all_structure[tag] = structure
        if structure["coverage_complete"] and structure["counts"]["natural_shared_effective_queries"] >= MIN_SHARED:
            chosen = tag
            break
    receipt = {
        "cohort": "TREC DL22 Passage Ranking",
        "selection_rule": "First complete-coverage slate in A,B,C with >=10 queries having an originally unjudged PID in exactly 2 or 3 top-10 lists",
        "selection_information": "Source lineage, rank and judgement presence; no score or outcome comparisons",
        "tie_rule": "Run ID lexicographically ascending after descending integer score",
        "rank_source": "Explicit source rank, exactly 1..10; source score ignored",
        "depth": DEPTH,
        "k": 3,
        "weights": {"binary": [0, 0, 1, 1], "graded": [0, 1, 2, 3]},
        "qrels": source(QRELS) | {"lines": qrels_lines, "exact_duplicate_rows": duplicates, "judged_queries": len(qrels)},
        "old_query_id_overlap": overlap,
        "prespecified_slates": SLATES,
        "candidate_structure": all_structure,
        "run_coverage": run_coverage,
        "sources": {name: source(RUNS[name]) for name in materialized},
        "chosen": chosen,
    }
    if chosen is not None:
        path = HERE / "cases.json"
        write(path, cases)
        receipt["cases"] = {"file": path.name, "sha256": digest(path), "count": len(cases)}
    write(HERE / "structural_freeze.json", receipt)
    print(json.dumps({"chosen": chosen, "cases": receipt.get("cases"), "candidate_structure": all_structure}, indent=2))


if __name__ == "__main__":
    main()
