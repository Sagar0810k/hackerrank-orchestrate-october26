"""Output validator for Ghost Data Still Exists (Part C2).

Checks that output.csv conforms to the contract:
- exact header case_id,deletion_status,steps_json
- one row per request, sorted by case_id, exactly the request case_ids
- deletion_status in {COMPLETE, INCOMPLETE, NOT_APPLICABLE}
- steps_json is a valid JSON list; [] for NOT_APPLICABLE
- step_no starts at 1 and increases by 1
- each step has exactly the 7 keys
- phase order FINDING -> REMEDIATION -> VERIFICATION
- (phase, operation, state) triple in the allowed table
- operation order within a phase follows the canonical table order
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

HEADER = ["case_id", "deletion_status", "steps_json"]
ALLOWED_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}

STEP_KEYS = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}

ALLOWED_TRIPLES = {
    ("FINDING", "REPORT_REMAINING_RECORD", "PRESENT"),
    ("FINDING", "REPORT_EXPOSED_PII", "PRESENT"),
    ("FINDING", "REPORT_ACTIVE_DATA_FLOW", "ACTIVE"),
    ("FINDING", "REPORT_RESTORE_RISK", "ACTIVE"),
    ("REMEDIATION", "DISABLE_DATA_FLOW", "DISABLED"),
    ("REMEDIATION", "BLOCK_RESTORE", "BLOCKED"),
    ("REMEDIATION", "DELETE_RECORD", "ABSENT"),
    ("REMEDIATION", "REDACT_RECORD", "REDACTED"),
    ("REMEDIATION", "ANONYMIZE_RECORD", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT"),
    ("VERIFICATION", "VERIFY_RECORD_PRESENT", "PRESENT"),
    ("VERIFICATION", "VERIFY_RECORD_REDACTED", "REDACTED"),
    ("VERIFICATION", "VERIFY_RECORD_ANONYMIZED", "ANONYMIZED"),
    ("VERIFICATION", "VERIFY_DATA_FLOW_DISABLED", "DISABLED"),
    ("VERIFICATION", "VERIFY_RESTORE_BLOCKED", "BLOCKED"),
}

PHASE_RANK = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
OPERATION_RANK = {
    "REPORT_REMAINING_RECORD": 0,
    "REPORT_EXPOSED_PII": 1,
    "REPORT_ACTIVE_DATA_FLOW": 2,
    "REPORT_RESTORE_RISK": 3,
    "DISABLE_DATA_FLOW": 0,
    "BLOCK_RESTORE": 1,
    "DELETE_RECORD": 2,
    "REDACT_RECORD": 3,
    "ANONYMIZE_RECORD": 4,
    "VERIFY_RECORD_ABSENT": 0,
    "VERIFY_RECORD_PRESENT": 1,
    "VERIFY_RECORD_REDACTED": 2,
    "VERIFY_RECORD_ANONYMIZED": 3,
    "VERIFY_DATA_FLOW_DISABLED": 4,
    "VERIFY_RESTORE_BLOCKED": 5,
}


class ValidationError(Exception):
    pass


def case_sort_key(case_id: str):
    """Natural order (case_99 before case_100), matching deletion_requests.csv."""
    head, _, num = case_id.rpartition("_")
    return (head, int(num)) if num.isdigit() else (case_id, 0)


def validate_output(
    path: Path, expected_case_ids: Optional[List[str]] = None
) -> Tuple[bool, List[str]]:
    """Validate output.csv. Returns (ok, list_of_messages). Never raises."""
    errors: List[str] = []
    path = Path(path)

    def err(msg: str) -> None:
        errors.append(msg)

    # --- read file ---
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != HEADER:
                err(f"header {reader.fieldnames} != expected {HEADER}")
                return False, errors
            rows = list(reader)
    except Exception as e:  # pragma: no cover - file read issues
        return False, [f"unable to read {path}: {e}"]

    # --- structural checks ---
    if expected_case_ids is not None:
        if len(rows) != len(expected_case_ids):
            err(f"expected {len(expected_case_ids)} rows, got {len(rows)}")
        got_ids = [r.get("case_id", "") for r in rows]
        if got_ids != sorted(expected_case_ids, key=case_sort_key):
            err("rows not sorted by case_id or case_id set mismatch")
        if len(set(got_ids)) != len(got_ids):
            err("duplicate case_id present")

    seen_case_ids: set = set()
    for idx, row in enumerate(rows, start=1):
        case_id = row.get("case_id", "")
        if expected_case_ids is not None and case_id in seen_case_ids:
            err(f"row {idx}: duplicate case_id {case_id}")
        seen_case_ids.add(case_id)

        status = row.get("deletion_status", "")
        if status not in ALLOWED_STATUSES:
            err(f"row {idx} ({case_id}): invalid deletion_status {status!r}")

        steps_json = row.get("steps_json", "")
        try:
            steps = json.loads(steps_json)
        except json.JSONDecodeError as e:
            err(f"row {idx} ({case_id}): steps_json invalid JSON: {e}")
            continue

        if not isinstance(steps, list):
            err(f"row {idx} ({case_id}): steps_json is not a list")
            continue

        if status == "NOT_APPLICABLE":
            if steps != []:
                err(f"row {idx} ({case_id}): NOT_APPLICABLE must have steps_json=[]")
            continue

        expected_no = 1
        prev_phase_rank = -1
        prev_op_rank = -1
        for sidx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                err(f"row {idx} ({case_id}): step {sidx} is not an object")
                continue
            if set(step.keys()) != STEP_KEYS:
                err(
                    f"row {idx} ({case_id}): step {sidx} keys "
                    f"{sorted(step.keys())} != {sorted(STEP_KEYS)}"
                )
                continue
            if step.get("step_no") != expected_no:
                err(
                    f"row {idx} ({case_id}): step {sidx} step_no "
                    f"{step.get('step_no')} != {expected_no}"
                )
            expected_no += 1

            phase = step.get("phase")
            operation = step.get("operation")
            state = step.get("state")
            if (phase, operation, state) not in ALLOWED_TRIPLES:
                err(
                    f"row {idx} ({case_id}): step {sidx} triple "
                    f"({phase}, {operation}, {state}) not allowed"
                )

            pr = PHASE_RANK.get(phase, -1)
            or_ = OPERATION_RANK.get(operation, -1)
            if pr < prev_phase_rank:
                err(f"row {idx} ({case_id}): step {sidx} phase {phase} out of order")
            if pr == prev_phase_rank and or_ < prev_op_rank:
                err(
                    f"row {idx} ({case_id}): step {sidx} operation "
                    f"{operation} out of order within phase"
                )
            prev_phase_rank = pr
            prev_op_rank = or_

            evidence_id = step.get("evidence_id", "")
            if phase == "REMEDIATION" and evidence_id != "":
                err(
                    f"row {idx} ({case_id}): step {sidx} REMEDIATION/{operation} "
                    "should have empty evidence_id"
                )

        if status == "COMPLETE":
            if not steps:
                err(f"row {idx} ({case_id}): COMPLETE must have steps")
            has_evidence = any(
                s.get("phase") == "VERIFICATION" and s.get("evidence_id", "") != ""
                for s in steps
            )
            if not has_evidence:
                err(
                    f"row {idx} ({case_id}): COMPLETE needs at least one "
                    "evidenced VERIFICATION step"
                )

    if errors:
        return False, errors
    return True, ["validation passed"]


def validate_output_strict(path: Path, expected_case_ids: List[str]) -> bool:
    ok, msgs = validate_output(path, expected_case_ids)
    for m in msgs:
        print(m)
    return ok


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output.csv")
    ok, msgs = validate_output(target)
    for m in msgs:
        print(m)
    sys.exit(0 if ok else 1)
