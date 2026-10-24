"""Step ordering (Part C9).

Phases run FINDING -> REMEDIATION -> VERIFICATION.  Inside a phase, steps
follow the operation order of the contract table, then ``system_id`` and
``resource_id`` ascending.  The remediation order already puts
DISABLE_DATA_FLOW and BLOCK_RESTORE before any record change, so no process
can recreate data while it is being removed.
"""
from __future__ import annotations

from typing import Dict, List

PHASE_RANK = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
OPERATION_ORDER = [
    "REPORT_REMAINING_RECORD", "REPORT_EXPOSED_PII", "REPORT_ACTIVE_DATA_FLOW", "REPORT_RESTORE_RISK",
    "DISABLE_DATA_FLOW", "BLOCK_RESTORE", "DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD",
    "VERIFY_RECORD_ABSENT", "VERIFY_RECORD_PRESENT", "VERIFY_RECORD_REDACTED",
    "VERIFY_RECORD_ANONYMIZED", "VERIFY_DATA_FLOW_DISABLED", "VERIFY_RESTORE_BLOCKED",
]
OPERATION_RANK = {op: i for i, op in enumerate(OPERATION_ORDER)}
FIELD_ORDER = ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]


def order_steps(steps: List[Dict]) -> List[Dict]:
    unique = {}
    for s in steps:
        key = (s["phase"], s["operation"], s["system_id"], s["resource_id"])
        unique.setdefault(key, s)
    ordered = sorted(unique.values(), key=lambda s: (
        PHASE_RANK[s["phase"]], OPERATION_RANK[s["operation"]], s["system_id"], s["resource_id"]))
    out = []
    for i, s in enumerate(ordered, start=1):
        step = dict(s)
        step["step_no"] = i
        out.append({k: step[k] for k in FIELD_ORDER})
    return out
