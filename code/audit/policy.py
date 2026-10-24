"""Policy (Part C8): what final state each data category must reach.

The required action per category is read from ``deletion_rules.csv`` (never
hard-coded); this module only translates an action into a target state and
knows which categories are processes (data flows, restore paths).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Optional

from .loader import DATASET, read_csv

# target state of a record for each policy action
ACTION_TARGET = {
    "DELETE": "ABSENT",
    "REDACT": "REDACTED",
    "ANONYMIZE": "ANONYMIZED",
    "RETAIN": "PRESENT",
}
FLOW_CATEGORY = "DATA_FLOW"
RESTORE_CATEGORY = "BACKUP_ARCHIVE"


@lru_cache(maxsize=1)
def rules() -> Dict[str, Dict[str, str]]:
    return {r["data_category"]: r for r in read_csv(DATASET / "deletion_rules.csv")}


def required_action(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    rule = rules().get(category)
    return rule["required_action"] if rule else None


def target_state(category: Optional[str]) -> Optional[str]:
    """Final state the policy requires for a record of this category."""
    if category == FLOW_CATEGORY:
        return "DISABLED"
    if category == RESTORE_CATEGORY:
        # the archive itself is retained; its restore access must be blocked
        return "BLOCKED"
    action = required_action(category)
    return ACTION_TARGET.get(action) if action else None
