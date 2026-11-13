#!/usr/bin/env python3
"""Independent exact QF_LIA comparator for the frozen four-run DL20 pilot.

One integer grade represents each unknown passage in a case, including across
runs. Z3 searches for an existential difference. A concrete SAT assignment is
checked independently using Python integers. A UNSAT status uses Z3's exact
integer decision procedure and is not an exported, independently checked proof.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter_ns
from typing import Any

RUN_IDS = tuple(sorted((
    "BM25", "BM25_RM3", "D_BERT_KD_TASB", "SPLADE_P_P_ENSEMBLE_DISTIL",
)))
ENDPOINTS = ("set", "prefix", "strict_set", "strict_prefix")
GRADES = frozenset(range(4))
WEIGHTS = {"binary": (0, 0, 1, 1), "graded": (0, 1, 2, 3)}
TOP_K = 3
DEPTH = 10
MAX_TIMEOUT_MS = 10_000


class Z3Session:
    """Small binding to the native Z3 SMT-LIB interpreter."""

    def __init__(self, timeout_ms: int) -> None:
        library_name = ctypes.util.find_library("z3") or "libz3.so.4"
        self.lib = ctypes.CDLL(library_name)
        pointer = ctypes.c_void_p
        self.error_handler_type = ctypes.CFUNCTYPE(None, pointer, ctypes.c_int)
        self._bind("Z3_mk_config", pointer)
        self._bind("Z3_del_config", None, pointer)
        self._bind("Z3_mk_context_rc", pointer, pointer)
        self._bind("Z3_del_context", None, pointer)
        self._bind("Z3_set_error_handler", None, pointer, self.error_handler_type)
        self._bind("Z3_eval_smtlib2_string", ctypes.c_char_p, pointer, ctypes.c_char_p)
        self._bind("Z3_get_full_version", ctypes.c_char_p)
        config = self.lib.Z3_mk_config()
        try:
            self.context = self.lib.Z3_mk_context_rc(config)
        finally:
            self.lib.Z3_del_config(config)
        if not self.context:
            raise RuntimeError("Z3 context creation failed")
        self.error_codes: list[int] = []
        self.error_handler = self.error_handler_type(
            lambda context, code: self.error_codes.append(code)
        )
        self.lib.Z3_set_error_handler(self.context, self.error_handler)
        self.version = self.lib.Z3_get_full_version().decode("ascii")
        self.timeout_ms = timeout_ms
        try:
            self.eval(
                f"(set-option :produce-models true)\n"
                f"(set-option :timeout {timeout_ms})\n(set-logic QF_LIA)"
            )
        except Exception:
            self.lib.Z3_del_context(self.context)
            raise

    def _bind(self, name: str, result: Any, *arguments: Any) -> None:
        function = getattr(self.lib, name)
        function.restype = result
        function.argtypes = list(arguments)

    def eval(self, script: str) -> str:
        self.error_codes.clear()
        value = self.lib.Z3_eval_smtlib2_string(self.context, script.encode("ascii"))
        response = "" if value is None else value.decode("utf-8").strip()
        if self.error_codes or "(error " in response:
            raise RuntimeError(f"Z3 SMT-LIB error {self.error_codes}: {response}")
        return response

    def __enter__(self) -> Z3Session:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.lib.Z3_del_context(self.context)


def validate_case(case: Any) -> None:
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    identity, qid, stratum = (case.get(name) for name in ("id", "qid", "stratum"))
    if stratum not in ("observed", "natural", "masked") or not isinstance(qid, str) or not qid:
        raise ValueError(f"invalid case metadata: {identity!r}")
    if identity != f"{stratum}:{qid}":
        raise ValueError(f"case id does not match stratum and qid: {identity!r}")
    runs, known, unknown = (case.get(name) for name in ("runs", "known", "unknown"))
    if not isinstance(runs, dict) or set(runs) != set(RUN_IDS):
        raise ValueError(f"{identity}: expected the four frozen run IDs")
    universe: set[str] = set()
    for run_id in RUN_IDS:
        passages = runs[run_id]
        if (
            not isinstance(passages, list) or len(passages) != DEPTH
            or any(not isinstance(p, str) or not p for p in passages)
            or len(set(passages)) != DEPTH
        ):
            raise ValueError(f"{identity}: {run_id} must have ten distinct passage IDs")
        universe.update(passages)
    if not isinstance(known, dict) or any(
        not isinstance(p, str) or type(g) is not int or g not in GRADES
        for p, g in known.items()
    ):
        raise ValueError(f"{identity}: known grades must be integer grades in 0..3")
    if not isinstance(unknown, list) or any(not isinstance(p, str) or not p for p in unknown):
        raise ValueError(f"{identity}: unknown passages must be a list of IDs")
    unknown_set = set(unknown)
    if len(unknown_set) != len(unknown) or unknown_set.intersection(known):
        raise ValueError(f"{identity}: duplicated or both known and unknown passage")
    if unknown_set.union(known) != universe:
        raise ValueError(f"{identity}: known and unknown IDs must partition the run universe")
    if stratum == "observed" and unknown:
        raise ValueError(f"{identity}: observed case has unknown grades")


def smt_sum(terms: list[str]) -> str:
    return "0" if not terms else "(+ " + " ".join(terms) + ")"


def disjunction(terms: list[str]) -> str:
    return "(or " + " ".join(terms) + ")"


def encode_case(case: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Define scores, ranks and four exact change predicates."""
    known = case["known"]
    grade_vars = {p: f"g{i}" for i, p in enumerate(sorted(case["unknown"]))}
    clauses: list[str] = []
    for grade in grade_vars.values():
        clauses.extend((
            f"(declare-const {grade} Int)",
            f"(assert (and (<= 0 {grade}) (<= {grade} 3)))",
        ))
    for profile, weights in WEIGHTS.items():
        for i, run_id in enumerate(RUN_IDS):
            terms: list[str] = []
            for passage in case["runs"][run_id]:
                if passage in known:
                    terms.append(str(weights[known[passage]]))
                else:
                    grade = grade_vars[passage]
                    terms.append(grade if profile == "graded" else f"(ite (>= {grade} 2) 1 0)")
            clauses.append(f"(define-fun s_{profile}_{i} () Int {smt_sum(terms)})")
        for i in range(len(RUN_IDS)):
            beats_i: list[str] = []
            for j in range(len(RUN_IDS)):
                if i != j:
                    # j wins a tie iff its lexically ordered ID precedes i's.
                    relation = ">=" if j < i else ">"
                    beats_i.append(f"(ite ({relation} s_{profile}_{j} s_{profile}_{i}) 1 0)")
            clauses.extend((
                f"(define-fun r_{profile}_{i} () Int (+ 1 {smt_sum(beats_i)}))",
                f"(define-fun m_{profile}_{i} () Bool (<= r_{profile}_{i} {TOP_K}))",
            ))
        cutoff_ties: list[str] = []
        all_ties: list[str] = []
        for i in range(len(RUN_IDS)):
            for j in range(i + 1, len(RUN_IDS)):
                same_total = f"(= s_{profile}_{i} s_{profile}_{j})"
                different_membership = f"(distinct m_{profile}_{i} m_{profile}_{j})"
                cutoff_ties.append(f"(and {different_membership} {same_total})")
                all_ties.append(same_total)
        clauses.extend((
            f"(define-fun no_cutoff_tie_{profile} () Bool (not {disjunction(cutoff_ties)}))",
            f"(define-fun no_tie_{profile} () Bool (not {disjunction(all_ties)}))",
        ))
    set_change = [f"(distinct m_binary_{i} m_graded_{i})" for i in range(len(RUN_IDS))]
    prefix_change = [
        f"(and (or m_binary_{i} m_graded_{i}) (distinct r_binary_{i} r_graded_{i}))"
        for i in range(len(RUN_IDS))
    ]
    clauses.extend((
        f"(define-fun change_set () Bool {disjunction(set_change)})",
        f"(define-fun change_prefix () Bool {disjunction(prefix_change)})",
        "(define-fun change_strict_set () Bool (and change_set no_cutoff_tie_binary no_cutoff_tie_graded))",
        "(define-fun change_strict_prefix () Bool (and change_prefix no_tie_binary no_tie_graded))",
    ))
    return "\n".join(clauses), grade_vars


def evaluate_witness(case: dict[str, Any], witness: dict[str, int]) -> dict[str, Any]:
    """Independently evaluate a concrete witness using integer arithmetic."""
    if set(witness) != set(case["unknown"]) or any(
        type(grade) is not int or grade not in GRADES for grade in witness.values()
    ):
        raise ValueError("witness does not assign exactly the unknown grades in 0..3")
    grades = case["known"] | witness
    totals: dict[str, dict[str, int]] = {}
    order: dict[str, list[str]] = {}
    gaps: dict[str, list[int]] = {}
    for profile, weights in WEIGHTS.items():
        totals[profile] = {
            run_id: sum(weights[grades[p]] for p in case["runs"][run_id])
            for run_id in RUN_IDS
        }
        order[profile] = sorted(RUN_IDS, key=lambda run_id: (-totals[profile][run_id], run_id))
        scores = [totals[profile][run_id] for run_id in order[profile]]
        gaps[profile] = [a - b for a, b in zip(scores, scores[1:])]
    prefix = {profile: items[:TOP_K] for profile, items in order.items()}
    set_changed = set(prefix["binary"]) != set(prefix["graded"])
    prefix_changed = prefix["binary"] != prefix["graded"]
    endpoint_changes = {
        "set": set_changed,
        "prefix": prefix_changed,
        "strict_set": set_changed and all(gap[TOP_K - 1] > 0 for gap in gaps.values()),
        "strict_prefix": prefix_changed and all(all(g > 0 for g in gap) for gap in gaps.values()),
    }
    return {
        "integer_totals": totals,
        "denominators": {"binary": DEPTH, "graded": 3 * DEPTH},
        "ordered_runs": order,
        "prefixes": prefix,
        "adjacent_gaps": gaps,
        "changed_endpoints": endpoint_changes,
        "order_only": prefix_changed and not set_changed,
    }


def read_witness(solver: Z3Session, grade_vars: dict[str, str]) -> dict[str, int]:
    if not grade_vars:
        return {}
    symbols = " ".join(grade_vars.values())
    response = solver.eval(f"(get-value ({symbols}))")
    values = re.findall(r"\((g\d+)\s+([0-3])\)", response)
    by_variable = {symbol: int(grade) for symbol, grade in values}
    if len(values) != len(grade_vars) or set(by_variable) != set(grade_vars.values()):
        raise RuntimeError(f"unexpected Z3 grade model: {response}")
    return {passage: by_variable[symbol] for passage, symbol in grade_vars.items()}


def solve_endpoint(
    case: dict[str, Any], solver: Z3Session, grade_vars: dict[str, str], endpoint: str,
) -> dict[str, Any]:
    started = perf_counter_ns()
    answer = solver.eval(f"(push 1)\n(assert change_{endpoint})\n(check-sat)")
    query_ns = perf_counter_ns() - started
    try:
        result: dict[str, Any] = {
            "status": "unknown", "witness": None, "solver_status": answer,
            "solver_query_ns": query_ns, "solver_timeout_ms": solver.timeout_ms,
        }
        if answer not in ("sat", "unsat", "unknown"):
            raise RuntimeError(f"unexpected Z3 status: {answer}")
        if query_ns > solver.timeout_ms * 1_000_000:
            result["reason"] = "check-sat elapsed beyond cap"
        elif answer == "unknown":
            result["reason"] = solver.eval("(get-info :reason-unknown)")
        elif answer == "unsat":
            result["status"] = "invariant"
            result["reason"] = "exact QF_LIA UNSAT for this endpoint on the nonempty domain"
        else:
            witness = read_witness(solver, grade_vars)
            evidence = evaluate_witness(case, witness)
            if not evidence["changed_endpoints"][endpoint]:
                raise RuntimeError(f"{case['id']}/{endpoint}: model failed exact revalidation")
            result.update(status="changed", witness=witness, witness_evaluation=evidence)
    finally:
        solver.eval("(pop 1)")
    result["elapsed_ns"] = perf_counter_ns() - started
    return result


def compare_case(case: dict[str, Any], timeout_ms: int = MAX_TIMEOUT_MS) -> dict[str, Any]:
    started = perf_counter_ns()
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= MAX_TIMEOUT_MS:
        raise ValueError("solver timeout must be an integer in 1..10000 ms")
    validate_case(case)
    clauses, grade_vars = encode_case(case)
    encoded = perf_counter_ns()
    # All unknowns may be 0. The schema proves that this is a shared feasible
    # completion, even when there are no unknowns and the domain is a singleton.
    nonempty = {passage: 0 for passage in grade_vars}
    evaluate_witness(case, nonempty)
    with Z3Session(timeout_ms) as solver:
        solver.eval(clauses)
        ready = perf_counter_ns()
        endpoints = {
            endpoint: solve_endpoint(case, solver, grade_vars, endpoint)
            for endpoint in ENDPOINTS
        }
        version = solver.version
    ended = perf_counter_ns()
    queries_ns = sum(value["solver_query_ns"] for value in endpoints.values())
    return {
        "qid": case["qid"], "stratum": case["stratum"], "unknown_count": len(grade_vars),
        "domain_nonempty": True, "feasible_completion": nonempty,
        "solver": f"libz3 {version}, QF_LIA",
        "endpoints": endpoints,
        "timing_ns": {
            "validation_and_encoding": encoded - started,
            "solver_setup_and_feasibility_check": ready - encoded,
            "solver_queries_total": queries_ns,
            "non_query_overhead": ended - started - queries_ns,
            "case_total": ended - started,
        },
    }


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON object key: {name!r}")
        result[name] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expect-cases-sha256", required=True)
    parser.add_argument("--timeout-ms", type=int, default=MAX_TIMEOUT_MS)
    args = parser.parse_args()
    raw = args.cases.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != args.expect_cases_sha256.lower():
        raise SystemExit(f"case file SHA-256 mismatch: actual {digest}")
    if args.cases.resolve() == args.output.resolve():
        raise SystemExit("output must be separate from frozen cases")
    if args.output.exists():
        raise SystemExit("output already exists; use a new path")
    cases = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(cases, list) or not cases:
        raise SystemExit("expected a nonempty list of cases")
    for case in cases:
        validate_case(case)
    if len({case["id"] for case in cases}) != len(cases):
        raise SystemExit("duplicate case IDs")
    results = {case["id"]: compare_case(case, args.timeout_ms) for case in cases}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
