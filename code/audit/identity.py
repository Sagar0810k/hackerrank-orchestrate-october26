"""Identity resolution: reconstruct current and historical identifiers for a request email."""
from __future__ import annotations

from typing import Optional, Dict, List, Any


def _norm(v: Any) -> str:
    return (v or "").strip().lower()


def resolve_identity(
    email: str,
    identities: List[Dict[str, str]],
    audit_log: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """Resolve a request email to a user_id and the full identifier set.

    Algorithm (C4):
      1. match request email (lowercase, stripped) against user_identities.email
      2. if not found, search user_audit_log old_value/new_value for the email
      3. collect every email/phone/email_hash/name for that user_id from the
         snapshot plus every old/new value for those fields in the audit log
      4. safety: an old email now owned by a different user_id is not followed
    """
    target = _norm(email)
    user_id: Optional[str] = None

    # Step 1: current snapshot match.
    for row in identities:
        if _norm(row.get("email")) == target:
            user_id = row["user_id"]
            break

    # Step 2: audit log match on old/new values.
    if user_id is None:
        candidates: List[str] = []
        for row in audit_log:
            if _norm(row.get("old_value")) == target or _norm(row.get("new_value")) == target:
                candidates.append(row["user_id"])
        seen = set()
        uniq: List[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        # Safety: if this email is the current email of a different user, do not
        # follow it to that other user's data.
        current_owners = {_norm(r.get("email")): r["user_id"] for r in identities}
        if target in current_owners:
            owner = current_owners[target]
            uniq = [c for c in uniq if c == owner]
        if len(uniq) == 1:
            user_id = uniq[0]
        elif len(uniq) > 1:
            user_id = uniq[0]

    if user_id is None:
        return None

    # Step 3: collect identifiers for the resolved user_id.
    identifiers: List[Dict[str, Any]] = []

    # Current snapshot row for this user.
    for row in identities:
        if row.get("user_id") == user_id:
            for field in ("email", "phone", "email_hash", "name"):
                val = row.get(field)
                if val:
                    identifiers.append({
                        "type": field,
                        "value": val,
                        "valid_from": None,
                        "valid_until": row.get("updated_at"),
                    })
            break

    # Audit-log history for this user.
    for row in audit_log:
        if row.get("user_id") != user_id:
            continue
        field = row.get("field_name")
        et = row.get("event_time")
        old_val = row.get("old_value")
        new_val = row.get("new_value")
        if old_val:
            identifiers.append({
                "type": field,
                "value": old_val,
                "valid_from": None,
                "valid_until": et,
            })
        if new_val:
            identifiers.append({
                "type": field,
                "value": new_val,
                "valid_from": et,
                "valid_until": None,
            })

    return {"user_id": user_id, "identifiers": identifiers}


def identifier_values(resolved: Dict[str, Any]) -> List[str]:
    """Return all identifier string values for searching evidence."""
    return [ident["value"] for ident in resolved.get("identifiers", [])]


def emails(resolved: Dict[str, Any]) -> List[str]:
    return [i["value"] for i in resolved.get("identifiers", []) if i["type"] == "email"]


def phones(resolved: Dict[str, Any]) -> List[str]:
    return [i["value"] for i in resolved.get("identifiers", []) if i["type"] == "phone"]


def email_hashes(resolved: Dict[str, Any]) -> List[str]:
    return [i["value"] for i in resolved.get("identifiers", []) if i["type"] == "email_hash"]


def names(resolved: Dict[str, Any]) -> List[str]:
    return [i["value"] for i in resolved.get("identifiers", []) if i["type"] == "name"]
