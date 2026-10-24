"""Identity resolution (Part C4).

Maps a request email (current *or* historical) to the stable ``user_id`` and
returns every identifier the subject has used: current snapshot values plus
every old/new value recorded in ``user_audit_log.csv``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

from .loader import DATASET, parse_timestamp, read_csv
from .normalize import name_key, norm_key, phone_key

FIELD_KIND = {"email": "email", "phone": "phone", "email_hash": "email_hash", "name": "name"}


@dataclass
class Subject:
    user_id: str
    keys: Set[str] = field(default_factory=set)        # identifiers used for linking
    names: Set[str] = field(default_factory=set)       # name keys (weak, not used for linking)
    history: List[Tuple[str, str, Optional[str]]] = field(default_factory=list)  # (kind, value, audit_id)


def _key_for(kind: str, value: str) -> Optional[str]:
    if kind == "phone":
        return phone_key(value)
    if kind == "name":
        return name_key(value)
    return norm_key(value)


@lru_cache(maxsize=1)
def _index():
    identities = read_csv(DATASET / "user_identities.csv")
    audit = read_csv(DATASET / "user_audit_log.csv")
    owners: Dict[str, Set[str]] = defaultdict(set)             # key -> user ids
    acquired: Dict[Tuple[str, str], datetime] = {}             # (key, user) -> time it became theirs
    per_user: Dict[str, Subject] = {}
    for row in identities:
        uid = row["user_id"]
        subj = per_user.setdefault(uid, Subject(user_id=uid))
        subj.keys.add(uid.lower())
        for f, kind in FIELD_KIND.items():
            k = _key_for(kind, row.get(f, ""))
            if not k:
                continue
            owners[k].add(uid)
            if kind == "name":
                subj.names.add(k)
            else:
                subj.keys.add(k)
                subj.history.append((kind, row[f], None))
    for row in audit:
        uid = row["user_id"]
        kind = FIELD_KIND.get(row["field_name"])
        if not kind:
            continue
        subj = per_user.setdefault(uid, Subject(user_id=uid))
        subj.keys.add(uid.lower())
        for value, is_new in ((row["old_value"], False), (row["new_value"], True)):
            k = _key_for(kind, value)
            if not k:
                continue
            owners[k].add(uid)
            if is_new:
                acquired[(k, uid)] = parse_timestamp(row["event_time"])
            if kind == "name":
                subj.names.add(k)
            else:
                subj.keys.add(k)
                subj.history.append((kind, value, row["audit_id"]))
    return owners, acquired, per_user


def resolve_identity(email: str, at: Optional[datetime] = None) -> Optional[Subject]:
    """Resolve the subject who owned ``email`` at time ``at``."""
    owners, acquired, per_user = _index()
    key = norm_key(email)
    if key is None:
        return None
    candidates = sorted(owners.get(key, ()))
    if not candidates:
        return None
    if len(candidates) > 1 and at is not None:
        # an address re-used by another person: pick whoever held it at request time
        held = [u for u in candidates if acquired.get((key, u)) is None or acquired[(key, u)] <= at]
        if held:
            candidates = sorted(held, key=lambda u: acquired.get((key, u)) or datetime.min.replace(tzinfo=at.tzinfo))
            candidates = [candidates[-1]]
    uid = candidates[0]
    subj = per_user[uid]
    # drop identifiers that are shared with any other person (cannot attribute safely)
    keys = {k for k in subj.keys if len(owners.get(k, {uid})) <= 1 or k == uid.lower()}
    return Subject(user_id=uid, keys=keys, names=set(subj.names), history=list(subj.history))


def key_owners(key: str) -> Set[str]:
    owners, _, _ = _index()
    return set(owners.get(key, ()))
