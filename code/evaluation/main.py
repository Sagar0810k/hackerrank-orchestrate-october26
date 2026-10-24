"""Evaluation script for Ghost Data Still Exists (Part C3).

Runs the pipeline on the public sample requests and compares the result with
``dataset/sample_output.csv`` (the only answer key participants have).

Metrics
-------
* status accuracy      - deletion_status equal
* step precision/recall/F1 - a predicted step is correct when an expected step
  of the same case has identical phase, system_id, resource_id, operation,
  state and evidence_id (step_no ignored, multiset matching)
* field accuracy       - position-aligned comparison of each field over the
  expected steps (step i vs step i)
* sequence accuracy    - the whole ordered steps_json array is identical

Usage:
    python code/evaluation/main.py                 # samples
    python code/evaluation/main.py --show-diff     # plus per-case missing/extra steps
    python code/evaluation/main.py --predictions output_sample.csv   # score an existing file
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))
DATASET = REPO_ROOT / "dataset"
SAMPLE_REQUESTS = DATASET / "sample_deletion_requests.csv"
SAMPLE_OUTPUT = DATASET / "sample_output.csv"

FIELDS = ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]
Result = Dict[str, Tuple[str, List[Dict[str, Any]]]]


def load_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_answers(path: Path) -> Result:
    out: Result = {}
    for row in load_csv(path):
        try:
            steps = json.loads(row.get("steps_json") or "[]")
        except json.JSONDecodeError:
            steps = []
        out[row["case_id"]] = (row["deletion_status"], steps if isinstance(steps, list) else [])
    return out


def step_key(step: Dict[str, Any]) -> Tuple:
    return tuple(step.get(f) for f in FIELDS)


def compare_case(exp: Tuple[str, List[Dict]], pred: Tuple[str, List[Dict]]) -> Dict[str, Any]:
    e_status, e_steps = exp
    p_status, p_steps = pred
    e_cnt, p_cnt = Counter(map(step_key, e_steps)), Counter(map(step_key, p_steps))
    tp = sum((e_cnt & p_cnt).values())
    field_ok = {f: 0 for f in FIELDS}
    for i, e in enumerate(e_steps):
        p = p_steps[i] if i < len(p_steps) else {}
        for f in FIELDS:
            field_ok[f] += int(p.get(f) == e.get(f))
    return {
        "status_ok": e_status == p_status,
        "exp_status": e_status, "pred_status": p_status,
        "tp": tp, "n_exp": len(e_steps), "n_pred": len(p_steps),
        "field_ok": field_ok,
        "sequence_ok": [step_key(s) for s in e_steps] == [step_key(s) for s in p_steps]
        and [s.get("step_no") for s in p_steps] == list(range(1, len(p_steps) + 1)),
        "missing": sorted((e_cnt - p_cnt).elements()),
        "extra": sorted((p_cnt - e_cnt).elements()),
    }


def evaluate(pred: Result, exp: Result) -> Dict[str, Any]:
    per_case = {}
    for cid in exp:
        per_case[cid] = compare_case(exp[cid], pred.get(cid, ("MISSING", [])))
    n = len(per_case)
    tp = sum(c["tp"] for c in per_case.values())
    n_exp = sum(c["n_exp"] for c in per_case.values())
    n_pred = sum(c["n_pred"] for c in per_case.values())
    prec = tp / n_pred if n_pred else 0.0
    rec = tp / n_exp if n_exp else 0.0
    by_status: Dict[str, List[int]] = {}
    for c in per_case.values():
        by_status.setdefault(c["exp_status"], [0, 0])
        by_status[c["exp_status"]][0] += int(c["status_ok"])
        by_status[c["exp_status"]][1] += 1
    return {
        "cases": n,
        "status_correct": sum(c["status_ok"] for c in per_case.values()),
        "status_by_expected": by_status,
        "step_tp": tp, "step_expected": n_exp, "step_predicted": n_pred,
        "step_precision": prec, "step_recall": rec,
        "step_f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
        "field_accuracy": {f: (sum(c["field_ok"][f] for c in per_case.values()) / n_exp if n_exp else 0.0)
                           for f in FIELDS},
        "sequence_correct": sum(c["sequence_ok"] for c in per_case.values()),
        "per_case": per_case,
    }


def report(m: Dict[str, Any], show_diff: bool = False) -> str:
    lines = [
        f"cases: {m['cases']}",
        f"status accuracy: {m['status_correct']}/{m['cases']} = {m['status_correct'] / m['cases']:.2%}",
        "status by expected label: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(m["status_by_expected"].items())),
        f"step precision: {m['step_tp']}/{m['step_predicted']} = {m['step_precision']:.2%}",
        f"step recall:    {m['step_tp']}/{m['step_expected']} = {m['step_recall']:.2%}",
        f"step F1:        {m['step_f1']:.2%}",
        f"sequence accuracy: {m['sequence_correct']}/{m['cases']} = {m['sequence_correct'] / m['cases']:.2%}",
        "field accuracy (position-aligned over expected steps):",
    ]
    lines += [f"  {f:12s} {v:.2%}" for f, v in m["field_accuracy"].items()]
    wrong = {cid: c for cid, c in m["per_case"].items() if not (c["status_ok"] and c["sequence_ok"])}
    lines.append(f"cases not exactly right: {len(wrong)}")
    for cid, c in wrong.items():
        lines.append(f"  {cid}: status {c['pred_status']} (exp {c['exp_status']}), "
                     f"{c['tp']}/{c['n_exp']} expected steps found, {c['n_pred'] - c['tp']} extra")
        if show_diff:
            for s in c["missing"]:
                lines.append(f"      - missing {s}")
            for s in c["extra"]:
                lines.append(f"      + extra   {s}")
    return "\n".join(lines)


def custom_suite() -> Tuple[List[Dict[str, str]], Result, Dict[str, str]]:
    """Requests, expected answers and purposes of the participant-made cases."""
    from evaluation.custom_cases import CUSTOM_CASES
    samples = load_answers(SAMPLE_OUTPUT)
    requests, expected, purposes = [], {}, {}
    for case in CUSTOM_CASES:
        requests.append({"case_id": case["case_id"], **case["request"]})
        purposes[case["case_id"]] = case["purpose"]
        if "expected_from_sample" in case:
            expected[case["case_id"]] = samples[case["expected_from_sample"]]
        else:
            exp = case["expected"]
            steps = [dict(zip(["phase", "system_id", "resource_id", "operation", "state", "evidence_id"], s),
                          step_no=i) for i, s in enumerate(exp["steps"], start=1)]
            expected[case["case_id"]] = (exp["deletion_status"], steps)
    return requests, expected, purposes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", help="score an existing predictions CSV instead of running the pipeline")
    ap.add_argument("--requests", default=str(SAMPLE_REQUESTS))
    ap.add_argument("--answers", default=str(SAMPLE_OUTPUT))
    ap.add_argument("--custom", action="store_true", help="run the participant-made custom cases")
    ap.add_argument("--show-diff", action="store_true")
    ap.add_argument("--json", help="write metrics JSON here")
    args = ap.parse_args(argv)

    if args.custom:
        import main as pipeline
        requests, expected, purposes = custom_suite()
        predictions = pipeline.run_pipeline(requests)
        metrics = evaluate(predictions, expected)
        for cid, c in metrics["per_case"].items():
            ok = "PASS" if c["status_ok"] and c["sequence_ok"] else "FAIL"
            print(f"{ok} {cid}: {purposes[cid]}")
            print(f"     status {c['pred_status']} (expected {c['exp_status']}), "
                  f"{c['tp']}/{c['n_exp']} expected steps, {c['n_pred'] - c['tp']} extra")
            for s in c["missing"]:
                print(f"       - missing {s}")
            for s in c["extra"]:
                print(f"       + extra   {s}")
        print(report(metrics))
        return 0

    expected = load_answers(Path(args.answers))
    if args.predictions:
        predictions = load_answers(Path(args.predictions))
    else:
        import main as pipeline  # code/main.py
        predictions = pipeline.run_pipeline(load_csv(Path(args.requests)))
    metrics = evaluate(predictions, expected)
    print(report(metrics, args.show_diff))
    if args.json:
        slim = {k: v for k, v in metrics.items() if k != "per_case"}
        Path(args.json).write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
