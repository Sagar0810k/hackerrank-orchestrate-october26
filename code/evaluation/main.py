"""Evaluation script for Ghost Data Still Exists (Part C3).

Compares predicted output.csv against dataset/sample_output.csv (32-case key).
Prints status, step-level, per-field, exact-sequence accuracy plus per-case
breakdown. Runs even if the pipeline produces nothing yet (score = 0).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET = REPO_ROOT / "dataset"
SAMPLE_REQUESTS = DATASET / "sample_deletion_requests.csv"
SAMPLE_OUTPUT = DATASET / "sample_output.csv"
PREDICTIONS = REPO_ROOT / "output.csv"

STEP_FIELDS = ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]
ALL_STEP_KEYS = ["step_no"] + STEP_FIELDS


def load_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_predictions(path: Path) -> Dict[str, Tuple[str, List[Dict[str, Any]]]]:
    out: Dict[str, Tuple[str, List[Dict[str, Any]]]] = {}
    if not path.exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            case_id = row["case_id"]
            status = row["deletion_status"]
            try:
                steps = json.loads(row.get("steps_json", "[]"))
            except json.JSONDecodeError:
                steps = []
            if not isinstance(steps, list):
                steps = []
            out[case_id] = (status, steps)
    return out


def load_expected(path: Path) -> Dict[str, Tuple[str, List[Dict[str, Any]]]]:
    out: Dict[str, Tuple[str, List[Dict[str, Any]]]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            case_id = row["case_id"]
            status = row["deletion_status"]
            steps = json.loads(row.get("steps_json", "[]"))
            out[case_id] = (status, steps)
    return out


def _step_key(step: Dict[str, Any]) -> Tuple:
    return tuple(step.get(f) for f in ALL_STEP_KEYS)


def compare_case(
    exp_status: str, exp_steps: List[Dict[str, Any]],
    pred_status: str, pred_steps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status_match": exp_status == pred_status,
        "exp_steps": len(exp_steps),
        "pred_steps": len(pred_steps),
        "step_correct": 0,
        "field_correct": {f: 0 for f in STEP_FIELDS},
        "field_total": 0,
        "sequence_exact": False,
        "missing": [],
        "extra": [],
        "order_problems": False,
    }
    n = max(len(exp_steps), len(pred_steps))
    matched = 0
    for i in range(n):
        e = exp_steps[i] if i < len(exp_steps) else None
        p = pred_steps[i] if i < len(pred_steps) else None
        if e is None:
            result["extra"].append(p.get("step_no", i + 1) if p else i + 1)
            continue
        if p is None:
            result["missing"].append(e.get("step_no", i + 1))
            continue
        for f in STEP_FIELDS:
            result["field_total"] += 1
            if p.get(f) == e.get(f):
                result["field_correct"][f] += 1
        if all(p.get(f) == e.get(f) for f in ALL_STEP_KEYS):
            matched += 1
    result["step_correct"] = matched
    if len(exp_steps) == len(pred_steps) and all(
        _step_key(e) == _step_key(p) for e, p in zip(exp_steps, pred_steps)
    ):
        result["sequence_exact"] = True
    exp_keys = sorted(_step_key(s) for s in exp_steps)
    pred_keys = sorted(_step_key(s) for s in pred_steps)
    if exp_keys == pred_keys and not result["sequence_exact"]:
        result["order_problems"] = True
    return result


def evaluate(
    predictions: Dict[str, Tuple[str, List[Dict[str, Any]]]],
    expected: Dict[str, Tuple[str, List[Dict[str, Any]]]],
) -> Dict[str, Any]:
    case_ids = sorted(expected.keys())
    total = len(case_ids)
    status_correct = 0
    step_correct_total = 0
    step_total = 0
    field_correct = {f: 0 for f in STEP_FIELDS}
    field_total = 0
    sequence_exact = 0
    per_case: List[Dict[str, Any]] = []

    for cid in case_ids:
        exp_status, exp_steps = expected[cid]
        pred_status, pred_steps = predictions.get(cid, ("NOT_APPLICABLE", []))
        r = compare_case(exp_status, exp_steps, pred_status, pred_steps)
        r["case_id"] = cid
        r["exp_status"] = exp_status
        r["pred_status"] = pred_status
        if exp_status == pred_status:
            status_correct += 1
        step_correct_total += r["step_correct"]
        step_total += r["exp_steps"]
        for f in STEP_FIELDS:
            field_correct[f] += r["field_correct"][f]
            field_total += r["field_total"]
        if r["sequence_exact"]:
            sequence_exact += 1
        per_case.append(r)

    safe_total = field_total if field_total else 1
    metrics = {
        "total": total,
        "status_correct": status_correct,
        "status_accuracy": status_correct / total if total else 0.0,
        "step_correct": step_correct_total,
        "step_total": step_total,
        "step_accuracy": step_correct_total / step_total if step_total else 0.0,
        "sequence_exact": sequence_exact,
        "sequence_accuracy": sequence_exact / total if total else 0.0,
        "field_correct": field_correct,
        "field_total": safe_total,
        "field_accuracy": {f: (field_correct[f] / safe_total) for f in STEP_FIELDS},
        "per_case": per_case,
    }
    return metrics


def print_report(metrics: Dict[str, Any]) -> None:
    print("=== Ghost Data Still Exists — Sample Evaluation ===")
    print(f"Total sample cases: {metrics['total']}")
    print(f"Status accuracy: {metrics['status_correct']}/{metrics['total']} = {metrics['status_accuracy']:.2%}")
    print(f"Step-level accuracy: {metrics['step_correct']}/{metrics['step_total']} = {metrics['step_accuracy']:.2%}")
    print(f"Exact-sequence accuracy: {metrics['sequence_exact']}/{metrics['total']} = {metrics['sequence_accuracy']:.2%}")
    print("Per-field accuracy:")
    for f in STEP_FIELDS:
        print(f"  {f}: {metrics['field_correct'][f]}/{metrics['field_total']} = {metrics['field_accuracy'][f]:.2%}")
    print()
    print("--- Wrong cases ---")
    wrong = [c for c in metrics["per_case"] if not c["status_match"] or not c["sequence_exact"]]
    for c in wrong:
        problems = []
        if not c["status_match"]:
            problems.append(f"status exp={c['exp_status']} pred={c['pred_status']}")
        if c["missing"]:
            problems.append(f"missing steps {c['missing']}")
        if c["extra"]:
            problems.append(f"extra steps {c['extra']}")
        if c["order_problems"]:
            problems.append("order problem")
        print(f"  {c['case_id']}: " + "; ".join(problems) if problems else f"  {c['case_id']}: OK")
    if not wrong:
        print("  (none)")


def run_pipeline_on_samples() -> Dict[str, Tuple[str, List[Dict[str, Any]]]]:
    try:
        sys.path.insert(0, str(REPO_ROOT / "code"))
        import main  # type: ignore
        if hasattr(main, "run_pipeline"):
            requests = load_csv(SAMPLE_REQUESTS)
            return main.run_pipeline(requests)
    except Exception:
        pass
    return {}


def main() -> None:
    expected = load_expected(SAMPLE_OUTPUT)
    predictions = run_pipeline_on_samples()
    if not predictions:
        predictions = load_predictions(PREDICTIONS)
    metrics = evaluate(predictions, expected)
    print_report(metrics)


if __name__ == "__main__":
    main()


