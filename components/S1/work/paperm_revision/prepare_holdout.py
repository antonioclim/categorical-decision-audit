"""Build the fixed DL19 inputs, without evaluating either relevance definition."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path


def load_lines(path, evidence):
    raw = path.read_bytes()
    if len(raw) != evidence["bytes"] or sha256(raw).hexdigest() != evidence["sha256"]:
        raise ValueError(f"Receipt differs from the manifest: {path.name}")
    return raw.decode("ascii").splitlines()


def prepare(input_dir, output_dir, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    qrels = defaultdict(dict)
    for line in load_lines(input_dir / "2019qrels-pass.txt", manifest["qrels"]):
        query, _, passage, grade = line.split()
        grade = int(grade)
        if passage in qrels[query] or grade not in range(4):
            raise ValueError(f"Invalid judgement: {line}")
        qrels[query][passage] = grade
    assert len(qrels) == 43
    assert sum(map(len, qrels.values())) == 9260

    runs = {}
    for name, evidence in sorted(manifest["runs"].items()):
        ranked = defaultdict(dict)
        for line in load_lines(input_dir / f"{name}.txt", evidence):
            query, _, passage, rank, _, _ = line.split()
            rank = int(rank)
            if rank in ranked[query]:
                raise ValueError(f"Duplicate rank: {line}")
            ranked[query][rank] = passage
        assert set(ranked) == set(qrels)
        runs[name] = {qid: [ranks[i] for i in range(1, 11)] for qid, ranks in ranked.items()}
        assert all(len(set(passages)) == 10 for passages in runs[name].values())

    cases = []
    held_out = {}
    for qid in sorted(qrels, key=int):
        per_run = {name: by_query[qid] for name, by_query in runs.items()}
        occurrence = Counter(passage for passages in per_run.values() for passage in passages)
        known = {passage: qrels[qid][passage] for passage in sorted(occurrence) if passage in qrels[qid]}
        unknown = sorted(occurrence.keys() - known.keys())
        stratum = "natural" if unknown else "observed"
        cases.append(dict(id=f"{stratum}:{qid}", stratum=stratum, qid=qid,
                          runs=per_run, known=known, unknown=unknown))
        if unknown:
            continue
        shared = [p for p, count in occurrence.items() if count >= 2]
        mask = sorted(shared, key=lambda p: sha256(f"DL19-IPM-v1|{qid}|{p}".encode()).hexdigest())[:3]
        mask = sorted(mask)
        case_id = f"masked:{qid}"
        cases.append(dict(id=case_id, stratum="masked", qid=qid, runs=per_run,
                          known={p: g for p, g in known.items() if p not in mask}, unknown=mask))
        held_out[case_id] = {p: known[p] for p in mask}

    strata = Counter(case["stratum"] for case in cases)
    assert dict(strata) == {"observed": 27, "natural": 16, "masked": 27}, strata
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in (("cases.json", cases), ("masked_reference.json", held_out)):
        (output_dir / name).write_text(json.dumps(content, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "strata": dict(strata),
        "unknown_histogram": {stratum: dict(Counter(
            len(case["unknown"]) for case in cases if case["stratum"] == stratum))
            for stratum in strata},
    }, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.input_dir, args.output_dir, args.input_dir / "dl19_input_eligibility.json")
