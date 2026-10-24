"""Link evidence to a case (which resources belong to the deletion subject).

Two kinds of links are used, strongest first:

1. **Identifier links.**  An observation inside the case's evidence window
   ``[requested_at, audit_at]`` carries one of the subject's identifiers
   (current/historical email, phone, email hash or stable ``user_id``), a data
   catalog row links the resource to the subject, or an already-linked record
   points at another resource (``source_resource_id``).

2. **Workflow-timing links.**  Records that no longer show any identifier
   (a deleted profile that now returns 404, an analytics profile that was
   already anonymized) can only be tied to the request through the deletion
   worker that processed it.  The worker acts on a request's resources in a
   short window around ``reported_at``.  Candidates in that window are
   accepted only after removing resources that evidence ties to someone else
   and resources that another concurrent request needs more.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .evidence import Observation, all_observations, catalog_links, resource_info
from .identity import Subject, key_owners, resolve_identity
from .loader import DATASET, parse_timestamp, read_csv

# When the deletion worker touches a request's records, relative to the
# request's reported_at (hours).  Measured on identifier-linked records of all
# 550 requests: the primary profile is deleted 0.73-1.25 h before the report;
# records that end up compliant are treated in a tight batch just before it
# (tombstone/legal -0.48, support -0.37, flows -0.25..-0.12, backups -0.13..-0.05).
# A few hand-written requests log the worker within minutes of the report.
CORE_WINDOW_HOURS = {
    "USER_PROFILE": (-1.3, -0.7),
    "ANALYTICS_PROFILE": (-0.55, -0.4),
    "ACCOUNT_TOMBSTONE": (-0.55, -0.4),
    "LEGAL_HOLD_RECORD": (-0.55, -0.4),
    "SUPPORT_MESSAGE": (-0.42, -0.3),
    "DATA_FLOW": (-0.3, -0.1),
    "BACKUP_ARCHIVE": (-0.16, 0.0),
}
FALLBACK_WINDOW_HOURS = (-0.2, 0.2)
WORKER_EVENTS = {"DELETE_RECORD", "ANONYMIZE_RECORD", "REDACT_RECORD", "DISABLE_DATA_FLOW",
                 "BLOCK_RESTORE", "RETAIN_RECORD"}


@dataclass
class CaseContext:
    case_id: str
    email: str
    requested_at: datetime
    reported_at: datetime
    audit_at: datetime
    reported_status: str
    subject: Optional[Subject]
    strong: Set[str] = field(default_factory=set)    # resource ids linked by identifiers
    weak: Set[str] = field(default_factory=set)      # resource ids linked by workflow timing
    notes: List[str] = field(default_factory=list)
    has_problems: bool = False                       # identifier-linked records violate policy

    @property
    def resources(self) -> Set[str]:
        return self.strong | self.weak

    def in_window(self, t: datetime) -> bool:
        return self.requested_at <= t <= self.audit_at


def _type_of(resource_id: str) -> str:
    return resource_info(resource_id)[1] or resource_id.rsplit("_", 1)[0]


@lru_cache(maxsize=1)
def _obs_by_resource() -> Dict[str, Tuple[Observation, ...]]:
    idx: Dict[str, List[Observation]] = defaultdict(list)
    for o in all_observations():
        idx[o.resource_id].append(o)
    return {k: tuple(v) for k, v in idx.items()}


@lru_cache(maxsize=1)
def _worker_rows() -> Tuple[Tuple[datetime, str, str], ...]:
    rows = []
    for r in read_csv(DATASET / "system_activity.csv"):
        if r.get("source_system") != "deletion_worker" or r.get("event_type") not in WORKER_EVENTS:
            continue
        rows.append((parse_timestamp(r["event_time"]), r["resource_id"], r["activity_id"]))
    return tuple(sorted(rows))


@lru_cache(maxsize=1)
def _worker_results() -> Dict[str, str]:
    """resource_id -> reported_result of the worker's DELETE_RECORD on a profile."""
    out = {}
    for r in read_csv(DATASET / "system_activity.csv"):
        if r.get("source_system") == "deletion_worker" and r.get("event_type") == "DELETE_RECORD":
            out[r["resource_id"]] = r.get("reported_result", "")
    return out


# The workflow's reported_status is the deletion worker's result for the
# primary profile (175 of 176 identifier-linked profiles agree), so a timing
# candidate must carry the result that matches the request's claim.
STATUS_TO_WORKER_RESULT = {"COMPLETE": "SUCCESS", "PARTIALLY_COMPLETE": "PARTIAL",
                           "NOT_STARTED": "FAILED"}


def strong_links(ctx: CaseContext) -> Set[str]:
    if ctx.subject is None:
        return set()
    keys = ctx.subject.keys
    linked: Set[str] = set()
    for o in all_observations():
        if ctx.in_window(o.available_at) and o.keys & keys:
            linked.add(o.resource_id)
    for link in catalog_links():
        if ctx.in_window(link.at) and link.keys & keys:
            linked.add(link.resource_id)
    # follow pointers from linked records (e.g. search document -> source account)
    by_res = _obs_by_resource()
    for rid in list(linked):
        for o in by_res.get(rid, ()):
            if ctx.in_window(o.available_at):
                linked |= set(o.refs)
    return linked


def owners_before(resource_id: str, at: datetime) -> Set[str]:
    """Users that evidence available by ``at`` ties to this resource."""
    users: Set[str] = set()
    for o in _obs_by_resource().get(resource_id, ()):
        if o.available_at > at:
            continue
        for k in o.keys:
            users |= key_owners(k)
    for link in catalog_links():
        if link.resource_id == resource_id and link.at <= at:
            for k in link.keys:
                users |= key_owners(k)
    return users


# Every deletion-worker run has its own clock phase.  Measured against the
# run's profile delete, the run's other actions land 9-11 s (before
# reported_at) or 20-22 s (after it) past a 30-second boundary.  All 307
# requests with two or more identifier-linked worker actions stay within 2 s
# of a single phase, so a candidate whose phase disagrees with the request's
# known phase cannot belong to that run.
PHASE_PERIOD = 30.0
PHASE_TOLERANCE = 2.0
PHASE_SPAN = timedelta(hours=4)


def event_phase(t: datetime, resource_id: str, reported_at: datetime) -> float:
    if _type_of(resource_id) == "USER_PROFILE":
        shift = 0.0
    else:
        shift = 10.0 if t < reported_at else 21.0
    return (t.timestamp() - shift) % PHASE_PERIOD


def phase_distance(a: float, b: float) -> float:
    d = abs(a - b) % PHASE_PERIOD
    return min(d, PHASE_PERIOD - d)


def run_phase(ctx: CaseContext, resources: Set[str]) -> Optional[float]:
    """Clock phase of the worker run that processed this request, from the
    worker actions on records already linked to it (None if unknown/unclear)."""
    phases = [event_phase(t, rid, ctx.reported_at) for t, rid, _ in _worker_rows()
              if rid in resources and abs(t - ctx.reported_at) <= PHASE_SPAN]
    if not phases:
        return None
    ref = phases[0]
    if any(phase_distance(ref, p) > PHASE_TOLERANCE for p in phases):
        return None
    return ref


def worker_candidates(ctx: CaseContext) -> Dict[str, Tuple[int, datetime]]:
    """resource_id -> (timing score, action time); score 2 = typical batch slot, 0 = fallback."""
    out: Dict[str, Tuple[int, datetime]] = {}
    for t, rid, _ in _worker_rows():
        rtype = _type_of(rid)
        d = (t - ctx.reported_at).total_seconds() / 3600
        core = CORE_WINDOW_HOURS.get(rtype)
        if core and core[0] <= d <= core[1]:
            score = 2
        elif FALLBACK_WINDOW_HOURS[0] <= d <= FALLBACK_WINDOW_HOURS[1]:
            score = 0
        else:
            continue
        if rtype != "USER_PROFILE":
            # only records whose in-window evidence carries no direct identifier
            # (already anonymized/redacted/disabled) need a timing link
            seen = [o for o in _obs_by_resource().get(rid, ()) if ctx.in_window(o.available_at)]
            if not seen or any(o.keys - {k for k in o.keys if k.startswith("user_")} for o in seen):
                continue
        if rid not in out or score > out[rid][0]:
            out[rid] = (score, t)
    return out


def build_contexts(requests: Iterable[Dict[str, str]], classify=None,
                   non_deletion: Optional[Set[str]] = None) -> Dict[str, CaseContext]:
    """Create contexts for *all* requests together so concurrent requests can
    be disambiguated against each other.

    ``classify(ctx)`` tells whether identifier-linked records already violate
    policy; ``non_deletion`` lists requests that do not authorize deletion
    (the deletion worker never acts for them, so they take no timing links).
    """
    ctxs: Dict[str, CaseContext] = {}
    for r in requests:
        req_at = parse_timestamp(r["requested_at"])
        ctx = CaseContext(
            case_id=r["case_id"], email=r["email"], requested_at=req_at,
            reported_at=parse_timestamp(r["reported_at"]), audit_at=parse_timestamp(r["audit_at"]),
            reported_status=r.get("reported_status", ""),
            subject=resolve_identity(r["email"], req_at))
        ctx.strong = strong_links(ctx)
        ctxs[ctx.case_id] = ctx
    if classify is not None:
        for ctx in ctxs.values():
            ctx.has_problems = bool(classify(ctx))
    _assign_weak_links({cid: c for cid, c in ctxs.items() if cid not in (non_deletion or set())})
    return ctxs


def has_direct_observation(ctx: CaseContext, resource_id: str) -> bool:
    """An explicit in-window observation of the resource (not mere omission)."""
    return any(ctx.in_window(o.available_at) and o.observed_at <= ctx.audit_at
               for o in _obs_by_resource().get(resource_id, ()))


def _edge_weight(ctx: CaseContext, rid: str, time_score: int) -> Optional[int]:
    """How well a timing candidate fits a request (higher is better, None = never).

    weight = timing score (typical batch slot) + evidence fit.
    A request whose identifier-linked records already show violations will be
    INCOMPLETE: its compliant records need no proof and the workflow leaves no
    read-back for them.  A request without violations will be COMPLETE, every
    verification must be backed by evidence, so it prefers candidates that
    have an explicit read-back in its window.
    """
    direct = has_direct_observation(ctx, rid)
    if _type_of(rid) != "USER_PROFILE":
        # already anonymized / redacted / disabled records only appear as proof
        # for requests that are otherwise complete (never in the INCOMPLETE
        # sample answers); another request of the same person can still share
        # them, see _assign_weak_links
        return time_score + 1 if (direct and not ctx.has_problems) else None
    expected = STATUS_TO_WORKER_RESULT.get(ctx.reported_status)
    if expected and _worker_results().get(rid) not in (None, expected):
        # 1 in 176 profiles breaks the rule: usable only if nothing else fits
        return -1
    fits = (not direct) if ctx.has_problems else direct
    return time_score + (1 if fits else 0)


def _resolve(remaining: Dict[str, Set[str]], taken: Set[str], ctxs: Dict[str, CaseContext],
             times: Dict[str, datetime]) -> Dict[str, str]:
    """Assign resources to requests (one per request): forced choices first,
    then a deterministic maximum matching for genuine ties."""
    assigned: Dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        used = taken | set(assigned.values())
        for rid, cs in sorted(remaining.items()):
            live = cs - used
            if rid not in assigned and len(live) == 1:
                assigned[rid] = next(iter(live))
                used = taken | set(assigned.values())
                changed = True
        for cid in sorted({c for cs in remaining.values() for c in cs} - used):
            opts = [rid for rid, cs in remaining.items() if cid in cs and rid not in assigned]
            if len(opts) == 1:
                assigned[opts[0]] = cid
                used = taken | set(assigned.values())
                changed = True
    used = taken | set(assigned.values())
    left = sorted((r for r in remaining if r not in assigned), key=lambda r: (times.get(r), r))
    match: Dict[str, str] = {}  # case -> resource

    def augment(rid: str, seen: Set[str]) -> bool:
        for cid in sorted(remaining[rid] - used, key=lambda c: (ctxs[c].requested_at, c)):
            if cid in seen:
                continue
            seen.add(cid)
            if cid not in match or augment(match[cid], seen):
                match[cid] = rid
                return True
        return False

    for rid in left:
        augment(rid, set())
    for cid, rid in match.items():
        assigned[rid] = cid
        ctxs[cid].notes.append(f"tie-broken weak link {rid}")
    return assigned


PHASE_MATCH_BONUS = 4


def _assign_weak_links(ctxs: Dict[str, CaseContext]) -> None:
    claimed_strong: Dict[str, Set[str]] = defaultdict(set)
    for cid, ctx in ctxs.items():
        for rid in ctx.strong:
            claimed_strong[rid].add(cid)
    candidates = {cid: worker_candidates(ctx) for cid, ctx in ctxs.items() if ctx.subject}
    times = {rid: t for t, rid, _ in _worker_rows()}

    # profiles first: an assigned profile fixes the run phase of a request that
    # had no identifier-linked worker action, which then guides the other types
    rtypes = sorted({_type_of(r) for cands in candidates.values() for r in cands},
                    key=lambda t: (t != "USER_PROFILE", t))
    for rtype in rtypes:
        phases = {cid: run_phase(ctxs[cid], ctxs[cid].strong | ctxs[cid].weak) for cid in candidates}
        cand: Dict[str, Dict[str, int]] = defaultdict(dict)  # rid -> case -> weight
        for cid, cands in candidates.items():
            ctx = ctxs[cid]
            uid = ctx.subject.user_id
            if any(_type_of(r) == rtype for r in ctx.strong | ctx.weak):
                continue  # one record of a type per request is enough
            for rid, (time_score, t) in cands.items():
                if _type_of(rid) != rtype or rid in ctx.strong:
                    continue
                owners = owners_before(rid, ctx.audit_at)
                if owners and owners != {uid}:
                    continue  # evidence ties it to somebody else
                if claimed_strong.get(rid) and cid not in claimed_strong[rid]:
                    continue  # another request has identifier evidence for it
                w = _edge_weight(ctx, rid, time_score)
                if w is None:
                    continue
                if phases[cid] is not None and time_score > 0:
                    if phase_distance(phases[cid], event_phase(t, rid, ctx.reported_at)) > PHASE_TOLERANCE:
                        continue  # performed by a different worker run
                    w += PHASE_MATCH_BONUS
                cand[rid][cid] = w

        assigned: Dict[str, str] = {}
        for tier in sorted({w for cs in cand.values() for w in cs.values()}, reverse=True):
            remaining = {rid: {c for c, w in cs.items() if w >= tier}
                         for rid, cs in cand.items() if rid not in assigned}
            remaining = {rid: cs for rid, cs in remaining.items() if cs}
            assigned.update(_resolve(remaining, set(assigned.values()), ctxs, times))
        for rid, cid in assigned.items():
            ctxs[cid].weak.add(rid)
            # a record belongs to a person, not to one request: other requests
            # of the same subject whose window holds the same worker action share it
            owner = ctxs[cid].subject.user_id
            for other, cands in candidates.items():
                if other != cid and rid in cands and ctxs[other].subject.user_id == owner:
                    ctxs[other].weak.add(rid)
