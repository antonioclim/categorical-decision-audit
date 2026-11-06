"""Review validation, separately coded from the frozen H11 calculation.

Uses raw CSV -> SQLite contingencies -> Fraction rankings. Imports neither
experiment.py nor either verifier. This is within-project validation, not an
external replication or a post-hoc replacement of confirmatory analysis.
"""
import csv
import hashlib
import io
import itertools
import json
import sqlite3
import zipfile
from collections import Counter
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import tempfile

ROOT = Path(__file__).resolve().parent
_TEMP = tempfile.TemporaryDirectory(prefix="paperm_review_qa_")
OUT = Path(_TEMP.name)
DOMAINS = {
    "buying": ("vhigh", "high", "med", "low"),
    "maint": ("vhigh", "high", "med", "low"),
    "doors": ("2", "3", "4", "5more"),
    "persons": ("2", "4", "more"),
    "lug_boot": ("small", "med", "big"),
    "safety": ("low", "med", "high"),
}
CLASSES = ("unacc", "acc", "good", "vgood")
WEIGHTS = {
    "adequate": ("0", "1", "1", "1"),
    "good_or_better": ("0", "0", "1", "1"),
    "ordinal": ("0", "1/3", "2/3", "1"),
}
FAULTS = ("clean", "coherent_false_verdict", "wrong_action", "missing_action",
          "stale_problem", "stale_rule", "stale_profiles", "stale_source")


def read(relative):
    return json.loads((ROOT / relative).read_text())


def canonical_digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main():
    errors = []
    check_count = 0

    def check(condition, message):
        nonlocal check_count
        check_count += 1
        if not condition:
            errors.append(message)

    raw = (ROOT / "data/heldout/car.data").read_bytes()
    receipt = read("data/ACQUISITION_RECEIPT.json")
    raw_hash = hashlib.sha256(raw).hexdigest()
    check(raw_hash == receipt["data_sha256"], "raw source digest mismatch")
    archive_raw = (ROOT / "data/heldout/car_evaluation.zip").read_bytes()
    check(hashlib.sha256(archive_raw).hexdigest() == receipt["archive_sha256"], "archive digest mismatch")
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        check(archive.testzip() is None, "source ZIP CRC failure")
        check(archive.read(receipt["archive_member"]) == raw, "CSV differs from retained archive member")
    freeze = read("study/FREEZE.json")
    freeze_bytes = (ROOT / "study/FREEZE.json").read_bytes()
    freeze_hash = hashlib.sha256(freeze_bytes).hexdigest()
    check(freeze_hash == receipt["freeze_sha256"], "acquisition is not bound to frozen protocol")
    check(freeze_hash == (ROOT / "study/FREEZE.sha256").read_text().split()[0], "freeze digest mismatch")
    projection = read("PROJECTION_MANIFEST.json")
    available_frozen, excluded_frozen = [], []
    for relative, expected in freeze["files"].items():
        candidate = ROOT / relative
        if candidate.is_file():
            available_frozen.append(relative)
            check(hashlib.sha256(candidate.read_bytes()).hexdigest() == expected, "available frozen file changed: " + relative)
        else:
            excluded_frozen.append(relative)
    check(sorted(available_frozen) == projection["included_frozen_files"], "included frozen projection differs")
    check(sorted(excluded_frozen) == projection["excluded_frozen_files"], "excluded frozen projection differs")
    reader_documents = []
    replacements = projection["document_replacements"]
    check(len({r["frozen_path"] for r in replacements}) == len(replacements), "duplicate frozen document replacement")
    check(len({r["current_path"] for r in replacements}) == len(replacements), "duplicate reader document replacement")
    for replacement in replacements:
        original = replacement["frozen_path"]
        document_path = ROOT / replacement["current_path"]
        current = document_path.resolve()
        check(original in excluded_frozen and freeze["files"].get(original) == replacement["frozen_sha256"],
              "reader document historical identity differs: " + original)
        safe_path = ROOT in current.parents and current.is_file() and not document_path.is_symlink()
        check(safe_path, "missing or unsafe reader document: " + replacement["current_path"])
        if safe_path:
            check(hashlib.sha256(current.read_bytes()).hexdigest() == replacement["current_sha256"],
                  "reader document digest differs: " + replacement["current_path"])
        reader_documents.append(replacement["current_path"])
    check(datetime.fromisoformat(freeze["created_utc"]) < datetime.fromisoformat(receipt["retrieved_utc"]),
          "local acquisition chronology not after local freeze")

    rows = list(csv.reader(raw.decode("utf-8").splitlines()))
    check(len(rows) == 1728, "raw row count")
    check(all(len(row) == 7 for row in rows), "raw column count")
    check(all(all(row[i] in domain for i, domain in enumerate(DOMAINS.values())) and row[6] in CLASSES for row in rows),
          "raw category validation")
    expected_configurations = set(itertools.product(*DOMAINS.values()))
    configurations = [tuple(row[:6]) for row in rows]
    check(len(configurations) == len(set(configurations)), "duplicate raw configuration")
    check(set(configurations) == expected_configurations, "incomplete factorial raw configuration coverage")
    class_counts = dict(Counter(row[6] for row in rows))
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE source (buying TEXT, maint TEXT, doors TEXT, persons TEXT, lug_boot TEXT, safety TEXT, class TEXT)")
    connection.executemany("INSERT INTO source VALUES (?,?,?,?,?,?,?)", rows)

    bank = read("results/heldout/case_bank.json")
    selections = read("results/heldout/selection_composition.json")
    observations = read("results/heldout/observations.json")
    summaries = read("results/heldout/summary.json")
    frozen_selection = read("study/CASE_SELECTION.json")
    check([item["claim"]["id"] for item in bank] == frozen_selection["claim_ids_in_order"], "bank identities/order differ from freeze")
    check(canonical_digest(bank) == summaries["bank_sha256"], "bank digest mismatch")
    unique = {}
    for item in bank:
        p = item["problem"]
        if p["id"] in unique:
            check(p == unique[p["id"]], "inconsistent repeated problem: " + p["id"])
        else:
            unique[p["id"]] = p
    check(len(unique) == 128 and len(bank) == 1024, "case/claim counts")
    check(set(unique) == {s["id"] for s in frozen_selection["specifications"]}, "selected case set mismatch")
    actual_actions = {}
    reconstructed_counts = {}
    case_metadata = {}
    for identifier, problem in unique.items():
        context_token, group_token, profile_token, rule_token = identifier.split("__")
        context_feature, context_value = context_token.split("=")
        group_features = group_token.split("-")
        pair = profile_token.split("-")
        check(context_feature in DOMAINS and all(g in DOMAINS for g in group_features), "unsupported case identifier")
        groups = ["|".join(f"{feature}={value}" for feature, value in zip(group_features, values))
                  for values in itertools.product(*(DOMAINS[f] for f in group_features))]
        counts = {g: {s: 0 for s in CLASSES} for g in groups}
        # Identifiers come from a validated fixed whitelist, not arbitrary SQL.
        query = f"SELECT {group_features[0]}, {group_features[1]}, class, COUNT(*) FROM source WHERE {context_feature}=? GROUP BY {group_features[0]}, {group_features[1]}, class"
        for first, second, label, count in connection.execute(query, (context_value,)):
            group = f"{group_features[0]}={first}|{group_features[1]}={second}"
            counts[group][label] = count
        check(problem["groups"] == groups, "declared group/tie order: " + identifier)
        check(problem["counts"] == counts, "raw-to-table disagreement: " + identifier)
        check(problem["states"] == list(CLASSES), "class state order: " + identifier)
        check(problem["profiles"] == {name: dict(zip(CLASSES, values)) for name, values in WEIGHTS.items()}, "profile encoding: " + identifier)
        check(problem["pair"] == pair, "profile pair: " + identifier)
        check(problem["source"]["sha256"] == raw_hash, "source binding in problem: " + identifier)
        if rule_token.startswith("ge"):
            rule = {"kind": "threshold", "cutoff": rule_token[2:].replace("_", "/"), "semantics": "selected_set"}
        else:
            k_token, semantics = rule_token.split("-", 1)
            rule = {"kind": "top_k", "k": int(k_token[1:]), "semantics": semantics}
        check(problem["rule"] == rule, "rule identifier disagreement: " + identifier)
        actions = {}
        for name in pair:
            weight = dict(zip(CLASSES, map(Fraction, WEIGHTS[name])))
            scores = {g: sum((counts[g][s] * weight[s] for s in CLASSES), Fraction()) / sum(counts[g].values()) for g in groups}
            if rule["kind"] == "threshold":
                selected = [g for g in groups if scores[g] >= Fraction(rule["cutoff"])]
            else:
                ranked = sorted(range(len(groups)), key=lambda i: (-scores[groups[i]], i))
                indices = ranked[:rule["k"]]
                selected = [groups[i] for i in (indices if rule["semantics"] == "ordered_prefix" else sorted(indices))]
            actions[name] = selected
        actual_actions[identifier] = actions
        reconstructed_counts[identifier] = counts
        case_metadata[identifier] = {"context": [context_feature, context_value], "grouped_attributes": group_features,
                                     "rule_family": rule["kind"] + ":" + rule["semantics"]}

    truth = {}
    for item in bank:
        p, claim, metadata = item["problem"], item["claim"], item["metadata"]
        identifier = p["id"]
        actions = actual_actions[identifier]
        pair = p["pair"]
        verdict = "EQUIVALENT" if actions[pair[0]] == actions[pair[1]] else "NONEQUIVALENT"
        expected_bindings = {"problem_sha256": canonical_digest(p), "rule_sha256": canonical_digest(p["rule"]),
                             "profiles_sha256": canonical_digest(p["profiles"]), "source_sha256": raw_hash}
        valid = (claim["case_id"] == identifier and claim["bindings"] == expected_bindings
                 and claim["actions"] == actions and claim["verdict"] == verdict)
        math_true = claim["verdict"] == verdict
        fault = claim["id"].split("::")[-1]
        check(fault in FAULTS and fault == metadata["fault"], "fault label disagreement")
        check(valid == metadata["valid_claim"], "claim validity label: " + claim["id"])
        check(math_true == metadata["mathematical_claim_true"], "mathematical truth label: " + claim["id"])
        check(verdict == metadata["true_verdict"], "oracle truth: " + claim["id"])
        for key, expected in case_metadata[identifier].items():
            check(metadata[key] == expected, "case metadata: " + claim["id"])
        truth[claim["id"]] = {"valid": valid, "math_true": math_true, "fault": fault}

    for selection in selections:
        identifier = selection["case_id"]
        problem = unique[identifier]
        actions, counts = actual_actions[identifier], reconstructed_counts[identifier]
        first, second = [actions[p] for p in problem["pair"]]
        check(selection["actions_equal"] == (first == second), "selection action equality")
        check(selection["membership_changes"] == [g for g in problem["groups"] if (g in first) != (g in second)], "selection membership changes")
        expected_prefix = ([{"position": i + 1, "first": a, "second": b}
                            for i, (a, b) in enumerate(itertools.zip_longest(first, second)) if a != b]
                           if problem["rule"]["semantics"] == "ordered_prefix" else [])
        check(selection["ordered_prefix_differences"] == expected_prefix, "selection prefix differences")
        check(selection["same_group_quota"] == (len(first) == len(second)), "selection group quota")
        for profile, action in actions.items():
            class_counts_selected = {s: sum(counts[g][s] for g in action) for s in CLASSES}
            total = sum(class_counts_selected.values())
            expected = {"selected_group_ids": action, "selected_groups": len(action), "represented_rows": total,
                        "class_counts": class_counts_selected,
                        "good_or_better_share": str(Fraction(class_counts_selected["good"] + class_counts_selected["vgood"], total)) if total else None}
            check(selection["profiles"][profile] == expected, "selection source composition: " + identifier)
    check(len(selections) == 128 and len({s["case_id"] for s in selections}) == 128, "selection diagnostic coverage")

    expected_keys = {(identifier, arm, budget) for identifier in truth for arm in ("contract", "adaptive_replay") for budget in (32,128,512)}
    observed_keys = [(r["claim_id"], r["arm"], r["budget"]) for r in observations]
    check(set(observed_keys) == expected_keys and len(observed_keys) == len(expected_keys), "observation coverage/uniqueness")
    order = {item["claim"]["id"]: i for i, item in enumerate(bank)}
    for record in observations:
        actual = truth[record["claim_id"]]
        check(record["order"] == order[record["claim_id"]], "observation order")
        check(record["status"] in ("ACCEPT", "REJECT", "ABSTAIN"), "observation status")
        check(type(record["work_units"]) is int and 0 <= record["work_units"] <= record["budget"], "work cap")
        check(record["valid_claim"] == actual["valid"] and record["mathematical_claim_true"] == actual["math_true"], "observation truth metadata")
        check(record["status"] != "ACCEPT" or actual["valid"], "invalid acceptance: " + record["claim_id"])
        check(record["status"] != "REJECT" or not actual["valid"], "false rejection: " + record["claim_id"])

    def independent_summary(records):
        valid = sum(truth[r["claim_id"]]["valid"] for r in records)
        invalid = len(records) - valid
        result = {"offered": len(records), "valid_offered": valid, "invalid_offered": invalid}
        for status, label in (("ACCEPT","accepted"),("REJECT","rejected"),("ABSTAIN","abstained")):
            ids = [r["claim_id"] for r in records if r["status"] == status]
            result[label], result[label+"_ids"] = len(ids), ids
        result["correct_accept"] = sum(r["status"] == "ACCEPT" and truth[r["claim_id"]]["valid"] for r in records)
        result["correct_reject"] = sum(r["status"] == "REJECT" and not truth[r["claim_id"]]["valid"] for r in records)
        result["false_accept"] = result["accepted"] - result["correct_accept"]
        result["false_reject"] = result["rejected"] - result["correct_reject"]
        result["mathematical_false_accept"] = sum(r["status"] == "ACCEPT" and not truth[r["claim_id"]]["math_true"] for r in records)
        result["correct_conclusive_yield"] = str(Fraction(result["correct_accept"] + result["correct_reject"],len(records))) if records else None
        result["valid_acceptance_yield"] = str(Fraction(result["correct_accept"],valid)) if valid else None
        result["false_accept_rate_among_invalid"] = str(Fraction(result["false_accept"],invalid)) if invalid else None
        result["work_units"] = sum(r["work_units"] for r in records)
        result["elapsed_ns"] = sum(r["elapsed_ns"] for r in records)
        return result

    def check_summary(actual, records, label):
        for field, expected in independent_summary(records).items():
            check(actual[field] == expected, "summary " + label + ": " + field)

    for endpoint in summaries["summaries"]:
        quota, budget = endpoint["quota"], endpoint["budget"]
        for arm, report in endpoint["arms"].items():
            records = [r for r in observations if r["arm"] == arm and r["budget"] == budget and r["order"] < quota]
            label = f"{arm}/{budget}/{quota}"
            check_summary(report, records, label)
            for fault, stratum in report["by_fault"].items():
                check_summary(stratum, [r for r in records if truth[r["claim_id"]]["fault"] == fault], label+"/"+fault)
            core = [r for r in records if truth[r["claim_id"]]["fault"] in ("clean","coherent_false_verdict","wrong_action")]
            check_summary(report["core_claim_subset"], core, label+"/core")
            for family, report_stratum in report["by_rule_family"].items():
                check_summary(report_stratum, [r for r in records if case_metadata[r["case_id"]]["rule_family"] == family], label+"/rule/"+family)
            for feature, report_stratum in report["by_context_feature"].items():
                check_summary(report_stratum, [r for r in records if case_metadata[r["case_id"]]["context"][0] == feature], label+"/context/"+feature)
            for family, report_stratum in report["by_grouped_feature_pair"].items():
                check_summary(report_stratum, [r for r in records if "|".join(case_metadata[r["case_id"]]["grouped_attributes"]) == family], label+"/groups/"+family)
        for status in ("accepted","rejected","abstained"):
            contract_ids = set(endpoint["arms"]["contract"][status+"_ids"])
            replay_ids = set(endpoint["arms"]["adaptive_replay"][status+"_ids"])
            composition = endpoint["between_arm_composition"]
            check(composition[status+"_contract_only_ids"] == sorted(contract_ids-replay_ids), "between-arm contract composition")
            check(composition[status+"_replay_only_ids"] == sorted(replay_ids-contract_ids), "between-arm replay composition")

    primary = next(s for s in summaries["summaries"] if s["quota"] == 1024 and s["budget"] == 128)
    result = {"status": "PASS" if not errors else "FAIL", "checks": check_count,
              "errors": errors, "raw_source_sha256": raw_hash, "raw_rows": len(rows),
              "raw_class_counts": class_counts, "cases_reconstructed_from_raw_sql": len(unique),
              "claims_independently_labelled": len(bank), "observations_checked": len(observations),
              "arm_endpoint_reports_checked": len(summaries["summaries"])*2,
              "frozen_files_checked": len(available_frozen), "frozen_files_excluded": sorted(excluded_frozen),
              "frozen_file_manifest_total": len(freeze["files"]), "freeze_sha256": freeze_hash,
              "reader_documents_checked": reader_documents,
              "reader_document_scope": "Current presentation editions are hash-checked separately; original frozen document bytes are excluded from this distribution.",
              "primary": {arm:{k:v[k] for k in ("accepted","rejected","abstained","correct_conclusive_yield","false_accept","false_reject")}
                          for arm,v in primary["arms"].items()},
              "scope": "Raw CSV/SQLite/Fraction reconstruction of retained study results; available frozen files and current reader documents are checked separately, with all excluded frozen files listed",
              "limitations": ["not external institutional replication", "does not verify operational effectiveness or independent outcome yield",
                              "does not formally verify the algorithm or mathematical proofs", "local timestamps are not external preregistration"]}
    OUT.mkdir(exist_ok=True)
    (OUT/"INDEPENDENT_VALIDATION.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
