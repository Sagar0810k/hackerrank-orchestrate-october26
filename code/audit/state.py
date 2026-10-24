"""State at audit_at (Part C7).

For every resource linked to a case, look at all observations of that
resource that were available inside the case window and let the latest one
decide.  Workflow claims never appear here (see evidence.extract_activity).

If no observation of a resource exists in the window, a point-in-time
snapshot that fully covers the resource's collection and does *not* contain
the resource proves it absent ("absence by omission").
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Set, Tuple

from .evidence import COLLECTION_CATEGORY, Observation, all_observations, resource_info
from .linker import CaseContext, _obs_by_resource
from .loader import DATASET, parse_timestamp, read_csv


@dataclass
class ResourceState:
    system_id: str
    resource_id: str
    category: Optional[str]
    present: Optional[bool]
    exposed: Optional[bool]
    linkable: Optional[bool]
    active: Optional[bool]
    evidence_id: str            # evidence proving this state ("" if none)
    observed_at: Optional[object] = None


# ---------------------------------------------------------------------------
# Snapshot coverage, for absence-by-omission
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def snapshot_coverage() -> Tuple[Tuple[str, object, frozenset, frozenset], ...]:
    """(evidence_id, available_at, covered categories, resource ids present)."""
    manifest = {m["file_id"]: m for m in read_csv(DATASET / "evidence_files.csv")}
    by_file: Dict[str, Set[str]] = {}
    cats: Dict[str, Set[str]] = {}
    for o in all_observations():
        if not o.evidence_id.startswith("evidence_"):
            continue
        if not (o.origin.startswith("sql:") or o.origin.startswith("bundle:")):
            continue
        if o.origin.endswith("operational_record_history"):
            continue
        by_file.setdefault(o.evidence_id, set()).add(o.resource_id)
        if o.category:
            cats.setdefault(o.evidence_id, set()).add(o.category)
    out = []
    for eid, rids in by_file.items():
        out.append((eid, parse_timestamp(manifest[eid]["captured_at"]),
                    frozenset(cats.get(eid, ())), frozenset(rids)))
    # bundles may declare an empty collection snapshot (zero records)
    for eid, m in manifest.items():
        if not m["file_path"].endswith(".json"):
            continue
        data = json.loads((DATASET / m["file_path"]).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "snapshots" not in data:
            continue
        empty = {COLLECTION_CATEGORY.get(s.get("collection"))
                 for s in data["snapshots"] if not s.get("records")}
        empty.discard(None)
        if empty:
            out.append((eid, parse_timestamp(m["captured_at"]), frozenset(empty), frozenset()))
    return tuple(out)


def omission_proof(ctx: CaseContext, resource_id: str, category: Optional[str]) -> Optional[str]:
    """Latest in-window snapshot covering ``category`` that lacks the resource."""
    best = None
    for eid, at, cats, rids in snapshot_coverage():
        if not ctx.in_window(at) or category not in cats or resource_id in rids:
            continue
        # a snapshot that does hold the resource later would override this
        if best is None or at > best[1]:
            best = (eid, at)
    return best[0] if best else None


# ---------------------------------------------------------------------------
def _rank(o: Observation) -> Tuple:
    # later observation wins; ties -> evidence available later, then evidence id
    return (o.observed_at, o.available_at, o.evidence_id)


def resource_state(ctx: CaseContext, resource_id: str) -> ResourceState:
    obs = [o for o in _obs_by_resource().get(resource_id, ())
           if ctx.in_window(o.available_at) and o.observed_at <= ctx.audit_at]
    system, category = resource_info(resource_id)
    if obs:
        # category from the most specific observation (explicit record types win)
        cats = [o.category for o in obs if o.category]
        if cats:
            # a typed observation (e.g. SECONDARY_IDENTIFIER, SUPPORT_ATTACHMENT)
            # overrides the generic prefix category
            special = [c for c in cats if c != category]
            category = special[-1] if special else cats[-1]
        last = max(obs, key=_rank)
        # copies observed at the same instant (primary vs replica, two exports
        # of one snapshot): any copy that still holds the data keeps it alive
        same = [o for o in obs if o.observed_at == last.observed_at]

        def any_true(attr):
            vals = [getattr(o, attr) for o in same if getattr(o, attr) is not None]
            return any(vals) if vals else None

        worst = max(same, key=lambda o: (bool(o.present), bool(o.exposed or o.linkable),
                                         bool(o.active), o.available_at, o.evidence_id))
        return ResourceState(
            system_id=last.system_id, resource_id=resource_id, category=category,
            present=any_true("present"), exposed=any_true("exposed"),
            linkable=any_true("linkable"), active=any_true("active"),
            evidence_id=worst.evidence_id, observed_at=last.observed_at)
    eid = omission_proof(ctx, resource_id, category)
    if eid:
        return ResourceState(system_id=system or "unknown", resource_id=resource_id,
                             category=category, present=False, exposed=False, linkable=False,
                             active=None, evidence_id=eid)
    return ResourceState(system_id=system or "unknown", resource_id=resource_id,
                         category=category, present=None, exposed=None, linkable=None,
                         active=None, evidence_id="")
