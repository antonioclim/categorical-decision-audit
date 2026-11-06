#!/usr/bin/env python3
"""Recalculate the explicitly scoped checks from the candidate evidence."""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import io
from itertools import product
import json
from pathlib import Path
from statistics import median
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
NATIVE = "native_dss_adapter"
WRAPPER = "competent_shared_kernel_bundle"
SEMANTICS = ("ordered_prefix", "selected_set")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def integrity():
    for line in (HERE / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        require(digest((HERE / name).read_bytes()) == expected, f"Candidate digest mismatch: {name}")


def allocations(mass, states):
    if len(states) == 1:
        yield {states[0]: mass}
        return
    for amount in range(mass + 1):
        for remainder in allocations(mass - amount, states[1:]):
            yield {states[0]: amount, **remainder}


def feasible(model, world):
    pools = model["unresolved_pools"]
    if set(world) != {p["name"] for p in pools}:
        return False
    for pool in pools:
        values = world[pool["name"]]
        if (set(values) != set(pool["allowed_states"])
            or any(type(n) is not int or n < 0 for n in values.values())
            or sum(values.values()) != pool["mass"]):
            return False
    flat = {f"{p}::{s}": amount for p, row in world.items() for s, amount in row.items()}
    for constraint in model["constraints"]:
        total = sum(Fraction(x) * flat[k] for k, x in constraint["coefficients"].items())
        rhs = Fraction(constraint["rhs"])
        if not {"=": total == rhs, "<=": total <= rhs, ">=": total >= rhs}[constraint["sense"]]:
            return False
    return True


def worlds(model):
    pools = model["unresolved_pools"]
    pools_worlds = [allocations(p["mass"], p["allowed_states"]) for p in pools]
    for candidate in product(*pools_worlds):
        world = {p["name"]: row for p, row in zip(pools, candidate)}
        if feasible(model, world):
            yield world


def scores(model, world):
    counts = {g: dict(row) for g, row in model["fixed_counts"].items()}
    for pool in model["unresolved_pools"]:
        target = counts[pool["group"]]
        for state, amount in world[pool["name"]].items():
            target[state] += amount
    return [
        {
            g: sum(Fraction(d["weights"][s]) * n for s, n in row.items()) / sum(row.values())
            for g, row in counts.items()
        }
        for d in model["definitions"]
    ]


def prefix(values, tie_break, direction, k):
    sign = 1 if direction == "lowest" else -1
    return tuple(sorted(tie_break, key=lambda g: sign * values[g])[:k])


def rule_outputs(values, rule, semantics):
    if rule["kind"] == "threshold":
        cutoff = Fraction(rule["threshold"])
        below = rule["direction"] == "below"
        return frozenset(g for g, value in values.items() if (value < cutoff) == below)
    result = prefix(values, rule["tie_break"], rule["direction"], rule["k"])
    return result if semantics == "ordered_prefix" else frozenset(result)


def any_disagreement(model, world, semantics):
    computed = scores(model, world)
    return any(len({rule_outputs(values, rule, semantics) for values in computed}) > 1
               for rule in model["rules"])


def model_action(model, semantics):
    """Recheck only the four finite fixture structures in the B1 case register."""
    mode = model["reference_mode"]
    if mode == "complete_small_enumeration":
        candidates = list(worlds(model))
        if not candidates:
            return "UNRESOLVED"
        return "NONEQUIVALENT" if any(any_disagreement(model, w, semantics) for w in candidates) else "EQUIVALENT"

    world = model["known_world"]
    require(feasible(model, world), f"{model['case_id']} archived world is infeasible")
    if mode == "identity_plus_nonempty_witness":
        definitions = model["definitions"]
        require(all(row["weights"] == definitions[0]["weights"] for row in definitions),
                "Unsupported identity structure")
        return "EQUIVALENT"
    if mode == "independent_existential_witness":
        require(any_disagreement(model, world, semantics), "Expected separating assignment")
        return "NONEQUIVALENT"

    require(mode == "unique_world_from_independent_equalities", f"Unsupported reference mode: {mode}")
    fixed = set()
    for constraint in model["constraints"]:
        coefficients = constraint["coefficients"]
        require(constraint["sense"] == "=" and len(coefficients) == 1, "Unsupported unique-world constraint")
        field, coefficient = next(iter(coefficients.items()))
        require(Fraction(coefficient) != 0, "Zero coefficient cannot fix a variable")
        fixed.add(field)
    for pool in model["unresolved_pools"]:
        states = pool["allowed_states"]
        require(len(states) == 2 and any(f"{pool['name']}::{state}" in fixed for state in states),
                "Unique-world route needs an independent fixed coordinate in each two-state pool")
    return "NONEQUIVALENT" if any_disagreement(model, world, semantics) else "EQUIVALENT"


def check_b1():
    cases = read_json("b1_synthetic_models.json")
    require(len(cases) == len({case["case_id"] for case in cases}) == 48, "B1 case register mismatch")
    calculated = {(case["case_id"], s): model_action(case, s) for case in cases for s in SEMANTICS}
    raw = (DATA / "b1_run_projection.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in raw]
    require({r["index"] for r in rows} == set(range(800)) and len(rows) == 800, "B1 run index mismatch")
    require(Counter(r["mode"] for r in rows) == {"primary": 576, "timing": 192, "memory": 16, "warmup": 16},
            "B1 execution counts differ")
    require(all(r["completed"] and not r["objective_contradictions"] for r in rows), "B1 errors or contradictions present")
    primary = [r for r in rows if r["mode"] == "primary"]
    grouped = defaultdict(list)
    for row in primary:
        grouped[row["case_id"], row["semantics"], row["budget"]].append(row)
        actual = row["action_actual"]
        require(actual == row["action_expected"] == calculated[row["case_id"], row["semantics"]],
                "B1 action certificate disagrees with the recalculated fixture")
        require(row["status"] == "PASS_OR_ABSTAIN" and row["action_correct"]
                and row["conclusive"] == (actual != "UNRESOLVED") and not row["false_reassurance"]
                and not row["false_escalation"] and not row["invalid_witnesses"],
                "B1 primary adjudication flags differ")
    require(len(grouped) == 288 and all({r["arm"] for r in g} == {NATIVE, WRAPPER} and len(g) == 2
                                      for g in grouped.values()), "B1 pair grid mismatch")
    ancillary = Counter()
    for row in primary:
        for expected, actual, n in row["ancillary"]:
            ancillary[expected, actual] += n
    unknown = sum(n for (expected, _), n in ancillary.items() if expected == "UNKNOWN")
    supported = sum(ancillary.values()) - unknown
    abstentions = ancillary["EQUIVALENT", "UNRESOLVED"]
    require((supported, unknown, abstentions) == (15372, 180, 344), "B1 ancillary totals differ")
    require(not any(n for (e, a), n in ancillary.items() if e not in {a, "UNKNOWN"} and a != "UNRESOLVED"),
            "B1 contradictory ancillary adjudication")
    for arm in (NATIVE, WRAPPER):
        arm_rows = [r for r in primary if r["arm"] == arm]
        require(Counter(r["action_actual"] for r in arm_rows) ==
                {"NONEQUIVALENT": 216, "EQUIVALENT": 36, "UNRESOLVED": 36}, "B1 arm coverage mismatch")
        require(sum(r["witness_checks"] for r in arm_rows) == 2427, "B1 witness count differs")
    timed = defaultdict(list)
    for row in rows:
        if row["mode"] == "timing":
            timed[row["case_id"], row["semantics"], row["arm"]].append(row["elapsed_ns"])
    require(len(timed) == 64 and all(len(v) == 3 for v in timed.values()), "B1 timed repeats mismatch")
    pairs = [(median(values), median(timed[case, semantics, WRAPPER]))
             for (case, semantics, arm), values in timed.items() if arm == NATIVE]
    excess = median(a - b for a, b in pairs) / 10**6
    ratio = median(a / b for a, b in pairs)
    require(excess == 8.142806 and round(ratio, 6) == 5.400227, "B1 paired timing mismatch")
    memory = {arm: median(r["python_allocation_peak_bytes"] for r in rows
                          if r["mode"] == "memory" and r["arm"] == arm) for arm in (NATIVE, WRAPPER)}
    require(memory == {NATIVE: 225182, WRAPPER: 23541}, "B1 traced peaks mismatch")
    control = read_json("b1_positive_control.json")
    require(control["valid"] and control["allocated_bytes"] == 1048576
            and control["observed_peak_bytes"] == 1048633, "B1 instrument control mismatch")
    return {"independent_fixture_action_checks": len(calculated), "matched_pairs": len(grouped),
            "median_paired_excess_ms": excess, "median_paired_ratio": ratio,
            "ancillary_supported": supported, "ancillary_unknown": unknown, "ancillary_abstentions": abstentions}


def check_historical():
    data = read_json("historical_outcomes.json")
    pair = []
    for mode, counts in (("ordered_prefix", (158, 182)), ("selected_set", (164, 176))):
        rows = data[mode]
        require(len(rows) == len({(r["case_id"], r["target"]) for r in rows}) == 1480, "Replay grid mismatch")
        require(sum(r["reference_available"] for r in rows) == 1420, "Replay reference denominator differs")
        require(all(r["audit_returned"] and (not r["reference_available"] or
                    (r["reference_match"] and r["certificate"] == r["reference_certificate"])) for r in rows),
                "Replay outcome contradicts its available reference")
        outcome = {r["case_id"]: r["certificate"] for r in rows if r["target"] == "action"}
        require(Counter(outcome.values()) == dict(zip(
            ("ACTION_EQUIVALENT_FOR_DECLARED_RULE_FAMILY", "ACTION_NONEQUIVALENT_FOR_DECLARED_RULE_FAMILY", "UNRESOLVED"),
            (*counts, 30))), "Replay action outcome totals differ")
        pair.append(outcome)
    require(pair[0].keys() == pair[1].keys() and sum(pair[0][k] != pair[1][k] for k in pair[0]) == 6,
            "Replay convention-change total differs")
    traces = data["order_only_traces"]
    require(Counter(row["location"] for row in traces) == {"top_level": 7, "pair_rule": 32},
            "Replay order-only trace counts differ")
    require(data["changed_rule_count"] == 32 and len({r["case_id"] for r in traces}) == 20
            and len({r["case_id"] for r in traces if r["whole_case_still_nonequivalent"]}) == 14,
            "Replay rule or case reconciliation differs")

    case = read_json("worked_case_0145.json")
    tie = case["tie_break"]
    candidates = list(worlds(case))
    same_set, same_prefix = 0, 0
    for world in candidates:
        left, right = (prefix(s, tie, "highest", 2) for s in scores(case, world))
        same_set += set(left) == set(right)
        same_prefix += left == right
    require((len(candidates), same_set, same_prefix) == (150, 150, 132), "0145 finite enumeration differs")
    witness = case["witness"]
    require(feasible(case, witness), "0145 witness is infeasible")
    left, right = scores(case, witness)
    require([[str(values[g]) for g in tie] for values in (left, right)] ==
            [["85/96", "51/52", "97/100"], ["19/48", "27/52", "11/20"]], "0145 witness score vectors differ")
    require((prefix(left, tie, "highest", 2), prefix(right, tie, "highest", 2)) ==
            (("g2", "g3"), ("g3", "g2")), "0145 highest-first prefixes differ")
    require((set(prefix(left, tie, "lowest", 2)), set(prefix(right, tie, "lowest", 2))) ==
            ({"g1", "g3"}, {"g1", "g2"}), "0145 lowest-first witness differs")
    return {"historical_requests": 2960, "reference_available_per_convention": 1420,
            "worked_case_worlds": len(candidates), "same_set": same_set, "same_prefix": same_prefix}


def matrix_totals(matrix, trigger):
    total = sum(map(sum, matrix))
    changed = sum(n for i, row in enumerate(matrix) for j, n in enumerate(row) if i != j)
    action_changed = sum(n for i, row in enumerate(matrix) for j, n in enumerate(row) if (i < trigger) != (j < trigger))
    return total, changed, action_changed


def verify_epa(source=None):
    archived = read_json("epa_aggregates.json")
    params = archived["parameters"]
    trigger = params["reporting_trigger_min_category_code"]
    expected = archived["transition_matrix"]
    total, changed, action_changed = matrix_totals(expected, trigger)
    require((total, changed, action_changed) == (63237, 10212, 0) and str(Fraction(changed, total)) == "3404/21079",
            "EPA matrix totals differ")
    require(expected[0][1] == 10202 and expected[3][4] == 10, "EPA transition cells differ")
    old = params["old_upper_tenths"]
    new = params["new_upper_tenths"]
    require(old[trigger - 1] == new[trigger - 1] == 354, "EPA common threshold differs")
    bounds = {0, *(b + d for b in old + new for d in (-1, 0, 1))}
    require(len(bounds) == archived["boundary_check_count"] == 25, "EPA boundary count differs")
    result = {"eligible": total, "category_changed": changed, "trigger_changed": action_changed,
              "input_snapshot_rechecked": False}
    if source is None:
        return result
    require(digest(source.read_bytes()) == archived["source"]["sha256"], "EPA input digest differs")
    seen = 0
    included = {}
    exclusions = Counter()
    duplicates = 0
    inclusion = params["inclusion"]
    unit = params["unit_fields"]
    with ZipFile(source) as z, z.open("daily_88101_2023.csv") as member:
        for row in csv.DictReader(io.TextIOWrapper(member, encoding="utf-8")):
            seen += 1
            fixed = ("Parameter Code", "Sample Duration", "Pollutant Standard", "Units of Measure")
            mismatch = next((field for field in fixed if row[field] != inclusion[field]), None)
            if mismatch is not None:
                exclusions[mismatch] += 1
                continue
            if (row["Event Type"] not in inclusion["Event Type"]
                    or not "2023-01-01" <= row["Date Local"] <= "2023-12-31"):
                exclusions["Event Type or Date Local"] += 1
                continue
            try:
                valid = Fraction(row["Observation Percent"]) >= inclusion["Observation Percent_min"]
                value = Fraction(row["Arithmetic Mean"])
            except (ValueError, ZeroDivisionError):
                exclusions["Invalid numeric observation"] += 1
                continue
            if not valid or value < inclusion["Arithmetic Mean_min"] or row["Method Code"] in inclusion["excluded_methods"]:
                exclusions["Coverage, concentration or method"] += 1
                continue
            key = tuple(row[k] for k in unit)
            if key in included:
                require(included[key] == value, "EPA duplicate observations have different means")
                duplicates += 1
            included[key] = value
    matrix = [[0] * 6 for _ in range(6)]
    for value in included.values():
        tenths = int(10 * value)
        a, b = bisect_left(old, tenths), bisect_left(new, tenths)
        require((a >= trigger) == (b >= trigger) == (tenths >= 355), "EPA trigger invariant differs")
        require((a != b) == (91 <= tenths <= 120 or 1255 <= tenths <= 1504 or 2255 <= tenths <= 2504),
                "EPA category crossing differs")
        matrix[a][b] += 1
    require(matrix == expected and seen == archived["source_rows"] and exclusions == archived["sequential_exclusions"]
            and duplicates == archived["collapsed_identical_duplicates"]
            and len({key[:-1] for key in included}) == archived["distinct_monitor_method_series"],
            "EPA recomputation differs from archived results")
    result["input_snapshot_rechecked"] = True
    result["source_rows"] = seen
    return result


def epss_source(directory, entry):
    data = (directory / entry["path"]).read_bytes()
    git_hash = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    require(digest(data) == entry["sha256"] and git_hash == entry["git_blob_sha1"]
            and len(data) == entry["size_bytes"], f"EPSS source digest differs for {entry['path']}")
    return json.loads(data, parse_float=Fraction)


def transition_counts(reference, candidate):
    removed, added = len(reference - candidate), len(candidate - reference)
    return {"old_count": len(reference), "new_count": len(candidate), "removed": removed, "added": added,
            "changed": added + removed}


def compare_epss_table(snapshot, records):
    require(len(records) == len({r["cve"] for r in records}) == snapshot["n"] == 4996,
            "EPSS snapshot count differs")
    old = Fraction(snapshot["old_cutoff"])
    reference = {r["cve"] for r in records if r["v4"] >= old}
    minimum = min(r["v5"] for r in records if r["cve"] in reference)
    maximum = max(r["v5"] for r in records if r["cve"] not in reference)
    require(maximum > minimum and snapshot["interval"] is None and len(reference) == 363, "EPSS order obstruction differs")
    scores = {r["cve"]: int(r["v5"] * 100000) for r in records}
    require(all(Fraction(scores[r["cve"]], 100000) == r["v5"] for r in records), "EPSS export precision differs")
    by_grid = {}
    for name, grid_denominator in (("percentage_point", 100), ("tenth_percentage_point", 1000)):
        values = {}
        for i in range(grid_denominator + 1):
            t = Fraction(i, grid_denominator)
            selected = {cve for cve, score in scores.items() if score >= i * (100000 // grid_denominator)}
            values[t] = transition_counts(reference, selected)
        minimum_change = min(values, key=lambda t: (values[t]["changed"], abs(t - old), t))
        minimum_size = min(values, key=lambda t: (abs(values[t]["new_count"] - len(reference)), abs(t - old), t))
        by_grid[name] = (values, {"inherited": old, "minimax_membership": minimum_change, "nominal_queue_size": minimum_size})
    for row in snapshot["table"]:
        values, choices = by_grid[row["grid"]]
        cutoff = choices[row["selector"]]
        require(Fraction(row["cutoff"]) == cutoff and all(row[k] == n for k, n in values[cutoff].items()),
                f"EPSS cutoff row differs for {row['grid']}/{row['selector']}")
    witness = {r["cve"]: (r["v4"], r["v5"]) for r in records}
    require(witness["CVE-2008-5053"] == (Fraction("0.01166"), Fraction("0.46998"))
            and witness["CVE-2010-10015"] == (Fraction("0.25352"), Fraction("0.00485")),
            "EPSS two-CVE witness differs")


def revision_trajectories(sources, version, dates):
    records = {}
    require(sources[f"revisions/{version}/meta.json"]["dates"] == dates, "EPSS correction date index differs")
    for name in ("diverging", "top_risers_v5", "top_fallers_v5"):
        for row in sources[f"revisions/{version}/{name}.json"]:
            key = row["cve"]
            values = list(zip(row["v4_scores"], row["v5_scores"], strict=True))
            require(len(values) == len(dates), "EPSS correction trajectory length differs")
            require(key not in records or records[key] == values, "Conflicting EPSS correction trajectories")
            records[key] = values
    return records


def verify_epss(directory=None):
    archive = read_json("epss_aggregate_readout.json")
    snapshot = archive["snapshot"]
    for row in snapshot["table"]:
        require(row["removed"] + row["added"] == row["changed"]
                and row["old_count"] + row["added"] - row["removed"] == row["new_count"],
                "Archived EPSS arithmetic differs")
    result = {"snapshot_cves": snapshot["n"], "score_exports_rechecked": False}
    if directory is None:
        return result
    sources = {item["path"]: epss_source(directory, item) for item in read_json("upstream_inputs.json")["epss"]}
    meta = sources["scatter_metadata.json"]
    require(meta["score_date"] == snapshot["date"] and (meta["v4_model"], meta["v5_model"]) ==
            ("v2025.03.14", "v2026.05.12"), "EPSS model IDs or date differ")
    compare_epss_table(snapshot, sources["scatter.json"])
    correction = archive["correction"]
    dates = list(correction["dates"])
    pre, post = (revision_trajectories(sources, version, dates) for version in ("pre", "post"))
    common = pre.keys() & post.keys()
    require(len(common) == correction["n_common"] == 14, "EPSS correction intersection differs")
    changes = {}
    old_cutoff, candidate_cutoff = (Fraction(correction[k]) for k in ("old_cutoff", "candidate_cutoff"))
    for i, day in enumerate(dates):
        old_diff = {cve for cve in common if pre[cve][i][0] != post[cve][i][0]}
        new_diff = {cve for cve in common if pre[cve][i][1] != post[cve][i][1]}
        record = correction["dates"][day]
        require((len(old_diff), len(new_diff)) == (record["v4_scores_changed"], record["beta_scores_changed"]),
                "EPSS changed score counts differ")
        reference = {cve for cve in common if pre[cve][i][0] >= old_cutoff}
        actual = []
        for version, panel in (("pre", pre), ("corrected", post)):
            selected = {cve for cve in common if panel[cve][i][1] >= candidate_cutoff}
            actual.append(transition_counts(reference, selected)["changed"])
            lower = max(panel[cve][i][1] for cve in common - reference)
            upper = min(panel[cve][i][1] for cve in reference)
            interval = record[f"continuous_interval_{version}"]
            if interval is None:
                require(lower >= upper, "EPSS correction interval should be empty")
            else:
                require(lower == Fraction(interval["lower"]) and upper == Fraction(interval["upper"])
                        and not interval["lower_closed"], "EPSS correction interval differs")
        changes[day] = actual
    require(all(changes[day] == [0, 1] for day in ("2026-05-24", "2026-05-25", "2026-05-26")),
            "EPSS correction headline differs")
    result.update(score_exports_rechecked=True, correction_intersection=len(common), correction_change_counts=changes)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epa-zip", type=Path, help="Locally obtained exact AirData snapshot ZIP")
    parser.add_argument("--epss-data", type=Path, help="Locally obtained export tree from upstream_inputs.json")
    args = parser.parse_args()
    integrity()
    result = {"candidate_integrity": "verified", "b1": check_b1(), "historical": check_historical(),
              "epa": verify_epa(args.epa_zip), "epss": verify_epss(args.epss_data)}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
