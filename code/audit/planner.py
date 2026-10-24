"""Planner (Part C9): turn resource states into status + ordered steps."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .linker import CaseContext
from .ordering import order_steps
from .policy import target_state
from .state import ResourceState, resource_state

# problem -> (finding op, finding state, remediation op, remediation state)
PROBLEM_STEPS = {
    "REMAINING": ("REPORT_REMAINING_RECORD", "PRESENT", "DELETE_RECORD", "ABSENT"),
    "EXPOSED_REDACT": ("REPORT_EXPOSED_PII", "PRESENT", "REDACT_RECORD", "REDACTED"),
    "EXPOSED_ANONYMIZE": ("REPORT_EXPOSED_PII", "PRESENT", "ANONYMIZE_RECORD", "ANONYMIZED"),
    "ACTIVE_FLOW": ("REPORT_ACTIVE_DATA_FLOW", "ACTIVE", "DISABLE_DATA_FLOW", "DISABLED"),
    "RESTORE_RISK": ("REPORT_RESTORE_RISK", "ACTIVE", "BLOCK_RESTORE", "BLOCKED"),
}
VERIFY_OP = {
    "ABSENT": "VERIFY_RECORD_ABSENT",
    "PRESENT": "VERIFY_RECORD_PRESENT",
    "REDACTED": "VERIFY_RECORD_REDACTED",
    "ANONYMIZED": "VERIFY_RECORD_ANONYMIZED",
    "DISABLED": "VERIFY_DATA_FLOW_DISABLED",
    "BLOCKED": "VERIFY_RESTORE_BLOCKED",
}


@dataclass
class Decision:
    resource: ResourceState
    target: Optional[str]          # required final state
    problem: Optional[str] = None  # key of PROBLEM_STEPS, or None if compliant
    verify_state: Optional[str] = None
    proven: bool = False           # current compliant state backed by evidence


def decide(rs: ResourceState) -> Optional[Decision]:
    target = target_state(rs.category)
    if target is None:
        return None
    d = Decision(resource=rs, target=target, verify_state=target)
    known = rs.evidence_id != ""
    if target == "DISABLED":
        if rs.active:
            d.problem = "ACTIVE_FLOW"
        d.proven = known and rs.active is False
    elif target == "BLOCKED":
        if rs.active:
            d.problem = "RESTORE_RISK"
        d.proven = known and rs.active is False
    elif target == "ABSENT":
        if rs.present:
            d.problem = "REMAINING"
        d.proven = known and rs.present is False
    elif target == "REDACTED":
        if rs.present and rs.exposed:
            d.problem = "EXPOSED_REDACT"
        elif rs.present is False:
            d.verify_state = "ABSENT"
        d.proven = known and not (rs.present and rs.exposed)
    elif target == "ANONYMIZED":
        if rs.present and (rs.linkable or rs.exposed):
            d.problem = "EXPOSED_ANONYMIZE"
        elif rs.present is False:
            d.verify_state = "ABSENT"
        d.proven = known and not (rs.present and (rs.linkable or rs.exposed))
    elif target == "PRESENT":
        d.proven = known and rs.present is True
        if rs.present is False:
            return None  # a retained record that is gone cannot be verified present
    return d


def has_problems(ctx: CaseContext) -> bool:
    """Do the identifier-linked records alone already violate policy?"""
    for rid in ctx.strong:
        d = decide(resource_state(ctx, rid))
        if d and d.problem:
            return True
    return False


def plan(ctx: CaseContext, deletion_requested: bool) -> Tuple[str, List[Dict], List[Decision]]:
    if not deletion_requested:
        return "NOT_APPLICABLE", [], []
    decisions = [d for d in (decide(resource_state(ctx, rid)) for rid in sorted(ctx.resources)) if d]
    problems = [d for d in decisions if d.problem]
    steps: List[Dict] = []
    if problems:
        for d in problems:
            f_op, f_state, r_op, r_state = PROBLEM_STEPS[d.problem]
            rs = d.resource
            steps.append(_step("FINDING", rs, f_op, f_state, rs.evidence_id))
            steps.append(_step("REMEDIATION", rs, r_op, r_state, ""))
        for d in decisions:
            state = d.verify_state if not d.problem else d.target
            steps.append(_step("VERIFICATION", d.resource, VERIFY_OP[state], state, ""))
        return "INCOMPLETE", order_steps(steps), decisions
    for d in decisions:
        if d.proven:
            steps.append(_step("VERIFICATION", d.resource, VERIFY_OP[d.verify_state],
                               d.verify_state, d.resource.evidence_id))
    return "COMPLETE", order_steps(steps), decisions


def _step(phase: str, rs: ResourceState, op: str, state: str, evidence_id: str) -> Dict:
    return {"phase": phase, "system_id": rs.system_id, "resource_id": rs.resource_id,
            "operation": op, "state": state, "evidence_id": evidence_id}
